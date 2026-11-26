"""Module 1: AI IPO Note Generator (layout only; logic is in ipodesk/)."""
from __future__ import annotations

import datetime as dt
import html
import math

import pandas as pd
import streamlit as st

from ipodesk.config import PROJECT_ROOT, disclaimer
from ipodesk.exports import to_docx, to_pdf
from ipodesk.extraction import TASKS, run_all, sample_fake_reply
from ipodesk.formatting import crore, indian_group, inr, nice_date, pct, times
from ipodesk.grounding import GroundingResult, summary
from ipodesk.llm import LLMClient, LLMConfig, has_api_key, load_llm_config
from ipodesk.note import (NoteDraft, UseRow, build_draft, compliance_issues, evaluate, export_blockers,
                          grounding_index, open_queries, query_text)
from ipodesk.calendar import timeline
from ipodesk.pdf_extract import extract_document, file_hash
from ipodesk.sample_data import make_sample_rhp_pdf
from ipodesk.schemas import IssueInputs, PeerPE, YearFinancials
from ipodesk.sections import find_sections, set_manual_range
from ui_common import (apply_theme, cleared, disclaimer_footer, facts, flag_rows, flag_summary, lead, md, query, reref, steps, tally, tick,
                       wp_header, xref)

apply_theme()
ss = st.session_state
STEP_LABELS = ["Source", "Sections", "AI extraction", "Review", "Sign-off"]
head = st.container()  # filled last, once we know the company and the current step
has_results = bool(ss.get("results"))
review_area = st.container()  # the review leads once extraction has run
setup = (st.expander("Source, sections and AI extraction (done: open to change)", expanded=False)
         if has_results else st.container())


def _none(x: object) -> float | None:
    """Turn NaN / blank cells from data editors into None."""
    if x is None or (isinstance(x, float) and math.isnan(x)) or x == "":
        return None
    return float(x)  # type: ignore[arg-type]


def _num(x: float | None) -> str:
    """RHP-style number: Indian grouping, 2 decimals, negatives in brackets."""
    if x is None:
        return "-"
    text = indian_group(abs(x), 2)
    return f"({text})" if x < 0 else text


def _mark(g: GroundingResult | None, qmap: dict[int, str], done: bool = False) -> str:
    """The mark for one figure: tick, re-reference ring, numbered query, or a query the reviewer has cleared."""
    if g is None:
        return ""
    if g.status == "ok":
        return tick()
    if g.status == "page corrected":
        return reref()
    label = qmap.get(id(g), "Q")
    return cleared(label) if done else query(label)


def _ref_page(g: GroundingResult | None) -> int | None:
    """Page to cite: where the number was actually found, else the page the AI cited."""
    if g is None:
        return None
    return g.found_on[0] if g.found_on else g.cited_page


def render_head(company: str, current: int, pages: int | None, digest: str | None, reviewed: str = "") -> None:
    """Fill the working-paper header and step strip at the top of the page."""
    with head:
        wp_header(company or "New IPO note",
                  "Every figure is ticked to its RHP page before a reviewer signs off. Facts only, never advice.",
                  [f"W/P REF N-{digest[:6].upper()}" if digest else "W/P REF -",
                   f"SOURCE RHP · {pages} PP" if pages else "SOURCE NOT LOADED",
                   f"PREPARED {dt.date.today():%d %b %Y}".upper(), *([reviewed] if reviewed else [])])
        steps(STEP_LABELS, current)


with setup:
    # ---------------------------------------------------------------------------- Source document
    with st.container(key="sheet-source"):
        st.markdown("## Source document and issue details")
        source = st.radio("RHP source", ["Upload an RHP PDF", "Use the sample RHP (fictional company)"], horizontal=True,
                          label_visibility="collapsed")
        pdf_bytes: bytes | None = None
        if source.startswith("Upload"):
            up = st.file_uploader("RHP PDF. Download it from SEBI's website: Filings → Public Issues.", type=["pdf"])
            if up is not None:
                pdf_bytes = up.getvalue()
        else:
            sample_path = PROJECT_ROOT / "data" / "sample" / "sample_rhp.pdf"
            if not sample_path.exists():
                make_sample_rhp_pdf(sample_path)
            pdf_bytes = sample_path.read_bytes()
        is_sample = source.startswith("Use")

        c1, c2, c3, c4, c5 = st.columns(5)
        band_low = c1.number_input("Price band low (₹)", min_value=0.0, value=300.0 if is_sample else None, step=1.0)
        band_high = c2.number_input("Price band high (₹)", min_value=0.0, value=315.0 if is_sample else None, step=1.0)
        lot = c3.number_input("Lot size (shares)", min_value=0, value=47 if is_sample else None, step=1)
        open_d = c4.date_input("Issue opens", value=dt.date(2026, 11, 30) if is_sample else None, format="DD/MM/YYYY")
        close_d = c5.date_input("Issue closes", value=dt.date(2026, 12, 2) if is_sample else None, format="DD/MM/YYYY")
        st.caption("Price band, lot size and dates are usually announced after the RHP is filed, so they are entered here.")
        if band_low and band_high and band_low > band_high:
            st.error("The low end of the price band is above the high end. Swap the two values.")
    manual = IssueInputs(price_band_low=band_low, price_band_high=band_high, lot_size=int(lot) if lot else None,
                         open_date=open_d, close_date=close_d)


    if pdf_bytes is None:
        render_head("", 0, None, None)
        st.info("Upload an RHP PDF, or choose the sample RHP, to start a note.")
        disclaimer_footer(disclaimer())
        st.stop()

    digest = file_hash(pdf_bytes)
    if ss.get("file_hash") != digest:
        bar = st.progress(0.0, text="Reading the PDF...")
        doc = extract_document(pdf_bytes, progress=lambda d, t: bar.progress(d / t, text=f"Reading page {d} of {t}"))
        bar.empty()
        ss.update(file_hash=digest, doc=doc, hits=find_sections(doc), results=None, draft=None, draft_ver=0)
    doc, hits = ss["doc"], ss["hits"]

    # ---------------------------------------------------------------------------- Sections
    with st.container(key="sheet-sections"):
        st.markdown(f"## Sections found in {doc.n_pages} pages")
        rows = []
        for h in hits.values():
            if h.found:
                left_pct = (h.start_page - 1) / doc.n_pages * 100
                width = max(0.8, (h.end_page - h.start_page + 1) / doc.n_pages * 100)
                bar_html = f'<div class="span-bar"><i style="left:{left_pct:.2f}%;width:{width:.2f}%"></i></div>'
                rows.append(f"<tr><td class='mark'>{tick()}</td><td>{html.escape(h.label)}</td><td class='n'>pp. {h.start_page}–{h.end_page}</td>"
                            f"<td style='width:38%'>{bar_html}</td><td class='dim small hide-sm'>{'set by you' if h.manual else html.escape(h.heading[:48])}</td></tr>")
            else:
                rows.append(f"<tr class='flag'><td class='mark'>{query('?')}</td><td>{html.escape(h.label)} <b>not found</b></td><td class='n'>-</td>"
                            f"<td style='width:38%'><div class='span-bar'></div></td><td class='dim small hide-sm'>Set the pages below</td></tr>")
        md(f'<div class="sched-wrap"><table class="sched"><tr><th></th><th>Section</th><th class="n">Pages</th>'
           f'<th>Position in the RHP</th><th class="hide-sm">Heading seen</th></tr>{"".join(rows)}</table></div>')
        missing = [h.label for h in hits.values() if not h.found]
        with st.expander("Set or correct a section's pages" + (f" ({len(missing)} not found)" if missing else "")):
            labels = {h.label: k for k, h in hits.items()}
            pick = st.selectbox("Section", list(labels))
            cs, ce, cb = st.columns([1, 1, 1], vertical_alignment="bottom")
            start = cs.number_input("Start page", 1, doc.n_pages, hits[labels[pick]].start_page or 1)
            end = ce.number_input("End page", 1, doc.n_pages, hits[labels[pick]].end_page or 1)
            if cb.button("Apply pages", width="stretch"):
                try:
                    set_manual_range(hits, labels[pick], int(start), int(end), doc.n_pages)
                    st.rerun()
                except ValueError as err:
                    st.error(str(err))
            peek = st.number_input("Read page", 1, doc.n_pages, 1)
            st.text_area("Page text", doc.page(int(peek))[:4000], height=200, disabled=True)

    # ---------------------------------------------------------------------------- AI extraction
    with st.container(key="sheet-extract"):
        st.markdown("## AI extraction")
        cfg = load_llm_config()
        key_ok = has_api_key(cfg.provider)
        e1, e2 = st.columns([2, 1], vertical_alignment="center")
        with e1:
            demo = st.toggle("Offline demo answers (sample RHP only, no API key or cost)", value=is_sample and not key_ok,
                             disabled=not is_sample, help="Canned answers for the fictional sample RHP. One figure is "
                             "deliberately wrong so you can watch the grounding check raise a query.")
            if demo:
                client = LLMClient(LLMConfig(provider="fake", model="offline-demo"), fake_reply=sample_fake_reply)
                st.caption(f"Offline demo answers. {len(TASKS)} tasks, only the first pages of each section are sent.")
            else:
                client = LLMClient(cfg)
                st.caption(f"{cfg.provider} · {cfg.model} · API key {'found' if key_ok else 'missing: add it to .env or Streamlit secrets'}. "
                           f"{len(TASKS)} tasks; results are cached per file, so re-running is free.")
        run = e2.button("Run AI extraction", type="primary", disabled=not (demo or key_ok), width="stretch")
        if run:
            bar = st.progress(0.0, text="Starting...")
            ss["results"] = run_all(doc, pdf_bytes, hits, client,
                                    progress=lambda i, n, label: bar.progress(i / n, text=f"{label} ({i} of {n})"))
            bar.empty()
            ss["draft"] = build_draft(ss["results"], manual, hits)
            ss["draft_ver"] = ss.get("draft_ver", 0) + 1
            ss["usage"] = client.usage
            st.rerun()

        results = ss.get("results")
        if results:
            all_g = [g for r in results.values() for g in r.grounding]
            tot = summary(all_g)
            trows = "".join(
                f"<tr{' class=flag' if not r.ok or summary(r.grounding)['verify manually'] else ''}>"
                f"<td>{html.escape(r.label)}</td><td class='n'>{len(r.pages_sent)}</td>"
                f"<td class='n'>{summary(r.grounding)['ok'] + summary(r.grounding)['page corrected']}</td>"
                f"<td class='n'>{summary(r.grounding)['verify manually'] or '-'}</td>"
                f"<td class='dim hide-sm'>{'cached' if r.from_cache else ''}{html.escape(r.error[:90])}</td></tr>"
                for r in results.values())
            md(f'<div class="sched-wrap"><table class="sched"><tr><th>Task</th><th class="n">Pages sent</th>'
               f'<th class="n">Ticked</th><th class="n">Queries</th><th class="hide-sm">Note</th></tr>{trows}</table></div>')
            usage = ss.get("usage")
            if usage and usage.calls:
                st.caption(f"LLM calls: {usage.calls} · tokens in / out: {usage.input_tokens:,} / {usage.output_tokens:,}")

results = ss.get("results")
if not results:
    render_head("", 1, doc.n_pages, digest)
    disclaimer_footer(disclaimer())
    st.stop()

# ---------------------------------------------------------------------------- Review (edits first, then the read view)
base: NoteDraft = ss["draft"]
v = ss["draft_ver"]
with review_area:
    tot = summary([g for r in results.values() for g in r.grounding])
    cleared_now = bool(ss.get(f"figok{ss['draft_ver']}"))  # reviewer has ticked the open queries off
    open_q = 0 if cleared_now else tot["verify manually"]
    tally(tot["ok"], tot["page corrected"], open_q, tot["verify manually"] if cleared_now else 0)
    review_left, review_right = st.columns([1.75, 1], gap="medium")
    schedule_slot = review_left.container(key="sheet-schedule")
    side_slot = review_right.container()
    edit_slot = st.container(key="sheet-edit")

with edit_slot:
    st.markdown("## Edit the draft")
    st.caption("Every value is editable. Valuation, red flags and the schedule above recompute from your edits.")
    t_fig, t_issue, t_text, t_more = st.tabs(["Financials", "Issue and capital", "Note text", "Peers and use of proceeds"])
    with t_fig:
        fin_cols = ["year", "revenue", "ebitda", "pat", "operating_cash_flow", "total_borrowings", "net_worth"]
        fin_df = st.data_editor(pd.DataFrame([y.model_dump() for y in base.financials], columns=fin_cols),
                                num_rows="dynamic", hide_index=True, width="stretch", key=f"fin{v}",
                                column_config={"year": "Year", **{c: st.column_config.NumberColumn(lbl, format="%.2f") for c, lbl in zip(
                                    fin_cols[1:], ["Revenue", "EBITDA", "PAT", "Operating cash flow", "Borrowings", "Net worth"])}})
        st.caption("₹ crore, oldest year first. Brackets in the RHP mean a negative number.")
    with t_issue:
        i1, i2, i3, i4 = st.columns(4)
        fresh = i1.number_input("Fresh issue (₹ cr)", value=base.issue.fresh_issue_cr, key=f"fr{v}")
        ofs = i2.number_input("Offer for sale (₹ cr)", value=base.issue.ofs_cr, key=f"ofs{v}")
        gcp = i3.number_input("General corporate purposes (₹ cr)", value=base.issue.gcp_cr, key=f"gcp{v}")
        post = i4.number_input("Post-issue shares", value=base.issue.post_issue_shares, step=1.0, format="%.0f", key=f"post{v}")
        o1, o2, o3 = st.columns(3)
        pledged = o1.number_input("Promoter shares pledged", value=base.promoter_pledged_shares, key=f"pl{v}")
        lit_cr = o2.number_input("Outstanding litigation (₹ cr)", value=base.litigation_cr, key=f"lit{v}")
        rpt_cr = o3.number_input("Related-party transactions, latest year (₹ cr)", value=base.rpt_cr, key=f"rpt{v}")
    with t_text:
        company = st.text_input("Company name", base.company, key=f"co{v}")
        snapshot = st.text_area("Company snapshot (3 lines)", base.snapshot, height=100, key=f"snap{v}")
        strengths = st.text_area("Key strengths, one per line", "\n".join(base.strengths), height=130, key=f"str{v}")
        risks = st.text_area("Top 5 risk factors, one per line", "\n".join(base.risks), height=150, key=f"risk{v}")
    with t_more:
        peer_df = st.data_editor(pd.DataFrame([p.model_dump() for p in base.peers], columns=["name", "pe"]),
                                 num_rows="dynamic", hide_index=True, width="stretch", key=f"peer{v}",
                                 column_config={"name": "Listed peer", "pe": st.column_config.NumberColumn("P/E", format="%.1f")})
        uses_df = st.data_editor(pd.DataFrame([u.model_dump() for u in base.uses], columns=["purpose", "amount_cr", "page"]),
                                 num_rows="dynamic", hide_index=True, width="stretch", key=f"uses{v}",
                                 column_config={"purpose": "Use of proceeds", "amount_cr": st.column_config.NumberColumn("₹ cr", format="%.2f"),
                                                "page": st.column_config.NumberColumn("RHP page", format="%d")})

draft = base.model_copy(update={
    "company": company, "snapshot": snapshot,
    "issue": manual.model_copy(update={"fresh_issue_cr": fresh, "ofs_cr": ofs, "gcp_cr": gcp, "post_issue_shares": post}),
    "uses": [UseRow(purpose=str(r["purpose"]), amount_cr=_none(r["amount_cr"]),
                    page=int(r["page"]) if _none(r["page"]) is not None else None)
             for _, r in uses_df.iterrows() if str(r["purpose"]).strip() not in ("", "None", "nan")],
    "financials": [YearFinancials(year=str(r["year"]), **{c: _none(r[c]) for c in fin_cols[1:]})
                   for _, r in fin_df.iterrows() if str(r["year"]).strip() not in ("", "None", "nan")],
    "peers": [PeerPE(name=str(r["name"]), pe=_none(r["pe"])) for _, r in peer_df.iterrows()
              if str(r["name"]).strip() not in ("", "None", "nan")],
    "promoter_pledged_shares": pledged, "litigation_cr": lit_cr, "rpt_cr": rpt_cr,
    "strengths": [s.strip() for s in strengths.splitlines() if s.strip()],
    "risks": [s.strip() for s in risks.splitlines() if s.strip()],
})
metrics, flags = evaluate(draft)
gi = grounding_index(draft)
queries = open_queries(draft)
qmap = {id(g): label for label, g in queries}
q_labels = ", ".join(label for label, _ in queries)
q_done = bool(ss.get(f"figok{v}"))  # the reviewer has ticked the queries off

# ---- schedule of figures (left)
with schedule_slot:
    st.markdown("## Schedule of figures")
    years = draft.financials
    metric_rows = [("Revenue from operations", "revenue"), ("EBITDA", "ebitda"), ("Profit after tax", "pat"),
                   ("Operating cash flow", "operating_cash_flow"), ("Total borrowings", "total_borrowings"),
                   ("Net worth", "net_worth")]
    body = []
    for label, key in metric_rows:
        cells, ref, flagged, phone_marks = [], None, False, ""
        for y in years:
            g = gi.get(f"financials:years[{y.year}].{key}")
            ref = ref or _ref_page(g)
            flagged = flagged or bool(g and g.status == "verify manually" and not q_done)
            hide = " hide-sm" if len(years) >= 3 and y is years[0] else ""  # phones keep the latest years and Ref
            if hide and g is not None and g.status == "verify manually":
                phone_marks += f"<span class='show-sm'>{_mark(g, qmap, q_done)}</span>"
            cells.append(f"<td class='n{hide}'>{_num(getattr(y, key))}{_mark(g, qmap, q_done)}</td>")
        body.append(f"<tr{' class=flag' if flagged else ''}><td>{label}{phone_marks}</td>{''.join(cells)}<td>{xref(ref)}</td></tr>")
    ratios = {r.year: r for r in metrics.yearly}
    for label, attr in [("EBITDA margin", "ebitda_margin_pct"), ("PAT margin", "pat_margin_pct"),
                        ("Revenue growth", "revenue_growth_pct"), ("Debt-to-equity", "debt_to_equity")]:
        fmt = (lambda x: times(x, 2)) if attr == "debt_to_equity" else pct
        cells = "".join(f"<td class='n dim{' hide-sm' if len(years) >= 3 and y is years[0] else ''}'>"
                        f"{fmt(getattr(ratios[y.year], attr))}</td>" for y in years)
        body.append(f"<tr><td class='dim'>{label}</td>{cells}<td class='dim'>Python</td></tr>")
    head_cells = "".join(f"<th class='n{' hide-sm' if len(years) >= 3 and y is years[0] else ''}'>{html.escape(y.year)}</th>"
                         for y in years)
    md(f'<div class="sched-wrap"><table class="sched"><tr><th>₹ crore</th>{head_cells}<th>Ref</th></tr>'
       f'{"".join(body)}</table></div>')

    st.markdown("### Issue, capital and disclosures")
    inputs = [("Fresh issue (₹ cr)", draft.issue.fresh_issue_cr, "objects:fresh_issue_amount"),
              ("Offer for sale (₹ cr)", draft.issue.ofs_cr, "objects:ofs_amount"),
              ("General corporate purposes (₹ cr)", draft.issue.gcp_cr, "objects:general_corporate_purposes"),
              ("Post-issue shares", draft.issue.post_issue_shares, "capital:post_issue_shares"),
              ("Promoter shares pledged", draft.promoter_pledged_shares, "capital:promoter_pledged_shares"),
              ("Outstanding litigation (₹ cr)", draft.litigation_cr, "litigation:total_amount"),
              ("Related-party transactions (₹ cr)", draft.rpt_cr, "rpt:latest_year_total")]
    irows = []
    for label, value, gkey in inputs:
        g = gi.get(gkey)
        shown = indian_group(value) if label == "Post-issue shares" and value else (
            "Nil" if label == "Promoter shares pledged" and value == 0 else _num(value))
        irows.append(f"<tr{' class=flag' if g and g.status == 'verify manually' and not q_done else ''}><td>{label}</td>"
                     f"<td class='n'>{shown}{_mark(g, qmap, q_done)}</td><td>{xref(_ref_page(g))}</td></tr>")
    for p in draft.peers:
        g = gi.get(f"basis:peers[{p.name}].pe")
        irows.append(f"<tr><td>Peer P/E · {html.escape(p.name)}</td><td class='n'>{times(p.pe)}{_mark(g, qmap, q_done)}</td>"
                     f"<td>{xref(_ref_page(g))}</td></tr>")
    md(f'<div class="sched-wrap"><table class="sched"><tr><th>Figure</th><th class="n">Value</th><th>Ref</th></tr>'
       f'{"".join(irows)}</table></div>')

    if queries:
        md(f'<div class="queries{" done" if q_done else ""}">' + "".join(
            f"<p>{cleared(lbl) if q_done else query(lbl)} {html.escape(query_text(g))} "
            f"{'Checked against the RHP by the reviewer.' if q_done else 'Verify against the RHP before sign-off.'}</p>"
            for lbl, g in queries) + "</div>")

# ---- valuation, flags and sign-off (right)
with side_slot:
    with st.container(key="sheet-valuation"):
        lead("P/E at upper band", times(metrics.pe),
             f"Peer median {times(metrics.peer_median_pe)} · computed in Python")
        i = draft.issue
        tl = timeline(i.close_date) if i.close_date else None
        facts([("Market cap", crore(metrics.market_cap_cr, symbol="₹")),
               ("Price band", f"₹{i.price_band_low:,.0f}–₹{i.price_band_high:,.0f}" if i.price_band_low and i.price_band_high else "-"),
               ("Listing (T+3)", nice_date(tl.listing) if tl else "Enter close date")])
        short = {"OFS over": "OFS over 50%", "Negative operating": "negative cash flow", "P/E above": "P/E vs peers",
                 "Promoter shares": "promoter pledge", "Litigation above": "litigation", "Related-party": "related parties",
                 "General corporate": "GCP near 25% limit"}
        flag_summary([next((v_ for k, v_ in short.items() if f.name.startswith(k)), f.name)
                      for f in flags if f.status == "flag"])
        with st.expander("EPS, issue size and minimum investment"):
            facts([("EPS, post-issue", inr(metrics.eps, 2, symbol="₹")),
                   ("Minimum investment", inr(metrics.min_investment, symbol="₹")),
                   ("Issue size", crore(metrics.issue_size_cr, symbol="₹")),
                   ("Fresh / OFS", f"{pct(metrics.fresh_pct, 0)} / {pct(metrics.ofs_pct, 0)}")])
    with st.container(key="signoff"):
        st.markdown("## Reviewer sign-off")
        issues = compliance_issues(draft)
        if issues:
            st.error(f"Advice-like words found: {', '.join(issues)}. Notes state facts only. Edit the text, "
                     "or confirm the words are used factually.")
        draft.reviewer = st.text_input("Reviewed by", key=f"rev{v}", placeholder="Your full name")
        fig_ok = st.checkbox(f"Clear {q_labels}: checked against the RHP" if queries else "No open queries",
                             disabled=not queries, key=f"figok{v}")
        # Only shown when the word scan actually found something to confirm.
        word_ok = (st.checkbox("The flagged words are used factually, not as advice", key=f"wok{v}")
                   if issues else False)
        blockers = export_blockers(draft, fig_ok, word_ok)
        if blockers:
            todo = []
            if not draft.reviewer.strip():
                todo.append("enter your name")
            if queries and not fig_ok:
                todo.append(f"clear {q_labels}")
            if issues and not word_ok:
                todo.append("resolve the flagged words")
            if not draft.company.strip():
                todo.append("enter the company name")
            st.button("Download note (PDF)", type="primary", width="stretch", disabled=True, icon=":material/lock:",
                      key=f"locked{v}")
            st.caption("To unlock: " + "; ".join(todo) + ".")
        else:
            stamp = f"REVIEWED BY {draft.reviewer} · {dt.date.today():%d %b %Y}".upper()
            md(f'<div class="stamp">{html.escape(stamp)}</div>')
            name = "".join(ch if ch.isalnum() else "_" for ch in draft.company)[:50] or "ipo_note"
            st.download_button("Download note (PDF)", to_pdf(draft), f"{name}_IPO_note.pdf", mime="application/pdf",
                               type="primary", width="stretch", icon=":material/download:")
            st.download_button("Download note (DOCX)", to_docx(draft), f"{name}_IPO_note.docx", width="stretch",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            st.caption("For internal review and approved channels only. Nothing is sent to clients.")
    with st.container(key="sheet-flags"):
        st.markdown("## Red flags")
        flag_rows([(f.name, f.status, f.reason.replace("Rs ", "₹")) for f in flags])
        st.caption("Rule checks that prompt closer reading. They are not ratings.")

render_head(draft.company, 3 if blockers else 4, doc.n_pages, digest,
            "" if blockers else f"REVIEWED {draft.reviewer[:24]} · {dt.date.today():%d %b %Y}".upper())
disclaimer_footer(disclaimer())
