"""Export a reviewed note to DOCX (python-docx) and PDF (reportlab).

Both exporters render the same list of "blocks" (heading / paragraph / bullets / table),
built once by `note_blocks`, so the Word and PDF versions always match.
'Rs' is used instead of the rupee sign because standard PDF fonts don't include it.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Literal
from xml.sax.saxutils import escape

from ipodesk.calendar import timeline
from ipodesk.formatting import crore, indian_group, inr, nice_date, pct, times
from ipodesk.note import NoteDraft, evaluate, note_disclaimer

BlockKind = Literal["title", "subtitle", "heading", "para", "bullets", "table", "disclaimer"]


@dataclass
class Block:
    """One piece of the document."""

    kind: BlockKind
    text: str = ""
    items: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)  # first row = header


def _num(x: float | None, decimals: int = 2) -> str:
    """Plain number for tables, '-' if missing."""
    return "-" if x is None else f"{x:,.{decimals}f}"


def note_blocks(draft: NoteDraft) -> list[Block]:
    """Lay out the whole note as blocks, computing metrics and red flags from the draft."""
    metrics, flags = evaluate(draft)
    i = draft.issue
    blocks: list[Block] = [
        Block("title", f"{draft.company}: IPO information note"),
        Block("subtitle", f"Prepared {nice_date(draft.prepared_on)} | Reviewed by: {draft.reviewer or '-'}"),
        Block("disclaimer", note_disclaimer()),
        Block("heading", "Company snapshot"),
        Block("para", draft.snapshot or "-"),
        Block("heading", "Issue details"),
    ]
    band = (f"Rs {i.price_band_low:,.0f} to Rs {i.price_band_high:,.0f}"
            if i.price_band_low is not None and i.price_band_high is not None else "-")
    rows = [["Item", "Detail"],
            ["Price band", band],
            ["Lot size", f"{i.lot_size} shares" if i.lot_size else "-"],
            ["Minimum investment (1 lot, upper band)", inr(metrics.min_investment)],
            ["Issue opens / closes", f"{nice_date(i.open_date)} / {nice_date(i.close_date)}"],
            ["Issue size", crore(metrics.issue_size_cr)],
            ["Fresh issue", f"{crore(i.fresh_issue_cr)} ({pct(metrics.fresh_pct)})"],
            ["Offer for sale (OFS)", f"{crore(i.ofs_cr)} ({pct(metrics.ofs_pct)})"]]
    if i.close_date:
        tl = timeline(i.close_date)
        rows += [["Allotment (T+1)", nice_date(tl.allotment)],
                 ["Refunds and demat credit (T+2)", nice_date(tl.credit_refund)],
                 ["Listing (T+3)", nice_date(tl.listing)]]
    blocks.append(Block("table", rows=rows))

    blocks.append(Block("heading", "Use of proceeds (fresh issue)"))
    if draft.uses:
        blocks.append(Block("table", rows=[["Purpose", "Rs crore", "Page"]] + [
            [u.purpose, _num(u.amount_cr), str(u.page or "-")] for u in draft.uses]))
    else:
        blocks.append(Block("para", "Not available."))

    blocks.append(Block("heading", "Financials (Rs crore)"))
    if draft.financials:
        yrs = draft.financials
        ratios = {r.year: r for r in metrics.yearly}
        def row(label: str, values: list[str]) -> list[str]:
            return [label, *values]
        blocks.append(Block("table", rows=[
            row("Particulars", [y.year for y in yrs]),
            row("Revenue from operations", [_num(y.revenue) for y in yrs]),
            row("Revenue growth", [pct(ratios[y.year].revenue_growth_pct) for y in yrs]),
            row("EBITDA", [_num(y.ebitda) for y in yrs]),
            row("EBITDA margin", [pct(ratios[y.year].ebitda_margin_pct) for y in yrs]),
            row("Profit after tax (PAT)", [_num(y.pat) for y in yrs]),
            row("PAT margin", [pct(ratios[y.year].pat_margin_pct) for y in yrs]),
            row("PAT growth", [pct(ratios[y.year].pat_growth_pct) for y in yrs]),
            row("Total borrowings", [_num(y.total_borrowings) for y in yrs]),
            row("Net worth", [_num(y.net_worth) for y in yrs]),
            row("Debt-to-equity", [times(ratios[y.year].debt_to_equity, 2) for y in yrs]),
            row("Operating cash flow", [_num(y.operating_cash_flow) for y in yrs]),
        ]))
    else:
        blocks.append(Block("para", "Not available."))

    blocks.append(Block("heading", "Valuation at the upper price band"))
    blocks.append(Block("table", rows=[
        ["Measure", "Value"],
        ["Post-issue shares", indian_group(i.post_issue_shares) if i.post_issue_shares else "-"],
        ["Market capitalisation", crore(metrics.market_cap_cr)],
        ["EPS (latest full-year PAT / post-issue shares)", inr(metrics.eps, 2)],
        ["P/E at upper band", times(metrics.pe)],
        ["Median P/E of listed peers (from RHP)", times(metrics.peer_median_pe)],
    ]))
    if draft.peers:
        blocks.append(Block("table", rows=[["Listed peer (from RHP)", "P/E"]] + [
            [p.name, times(p.pe)] for p in draft.peers]))

    blocks += [Block("heading", "Key strengths (as stated in the RHP)"),
               Block("bullets", items=draft.strengths or ["-"]),
               Block("heading", "Top risk factors (from the RHP)"),
               Block("bullets", items=draft.risks or ["-"])]
    if draft.litigation_notes:
        blocks += [Block("heading", "Outstanding litigation (from the RHP)"),
                   Block("bullets", items=draft.litigation_notes)]

    blocks.append(Block("heading", "Red-flag checklist (rule-based)"))
    blocks.append(Block("table", rows=[["Check", "Result", "Reason"]] + [
        [f.name, {"flag": "FLAG", "ok": "OK", "no data": "No data"}[f.status], f.reason] for f in flags]))
    blocks.append(Block("para", "Red flags are automatic rule checks to prompt closer reading. They are not ratings."))

    blocks.append(Block("heading", "Sources"))
    blocks.append(Block("bullets", items=[f"{k}: {v}" for k, v in draft.sources.items()] or ["-"]))
    unverified = draft.unverified()
    if unverified:
        blocks.append(Block("para", f"{len(unverified)} figure(s) could not be matched automatically to the RHP text "
                                    f"and were confirmed by the reviewer."))
    blocks.append(Block("disclaimer", note_disclaimer()))
    return blocks


def to_docx(draft: NoteDraft) -> bytes:
    """Render the note as a Word document and return its bytes."""
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name, style.font.size = "Calibri", Pt(10)
    for b in note_blocks(draft):
        if b.kind == "title":
            doc.add_heading(b.text, level=0)
        elif b.kind == "subtitle":
            doc.add_paragraph(b.text).runs[0].italic = True
        elif b.kind == "heading":
            doc.add_heading(b.text, level=2)
        elif b.kind == "para":
            for line in b.text.splitlines() or [""]:
                doc.add_paragraph(line)
        elif b.kind == "bullets":
            for item in b.items:
                doc.add_paragraph(item, style="List Bullet")
        elif b.kind == "table":
            table = doc.add_table(rows=len(b.rows), cols=len(b.rows[0]))
            table.style = "Light Grid Accent 1"
            for r, row in enumerate(b.rows):
                for c, cell in enumerate(row):
                    table.cell(r, c).text = cell
        elif b.kind == "disclaimer":
            run = doc.add_paragraph().add_run(b.text)
            run.bold, run.font.color.rgb = True, RGBColor(0xC6, 0x28, 0x28)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def to_pdf(draft: NoteDraft) -> bytes:
    """Render the note as a PDF and return its bytes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=ss["BodyText"], fontSize=8, leading=10)
    warn = ParagraphStyle("warn", parent=ss["BodyText"], textColor=colors.HexColor("#C62828"), fontName="Helvetica-Bold")
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title="IPO information note")
    width = A4[0] - 32 * mm
    story = []
    for b in note_blocks(draft):
        if b.kind == "title":
            story.append(Paragraph(escape(b.text), ss["Title"]))
        elif b.kind == "subtitle":
            story.append(Paragraph(f"<i>{escape(b.text)}</i>", ss["BodyText"]))
        elif b.kind == "heading":
            story += [Spacer(1, 4), Paragraph(escape(b.text), ss["Heading3"])]
        elif b.kind == "para":
            story.append(Paragraph(escape(b.text).replace("\n", "<br/>"), ss["BodyText"]))
        elif b.kind == "bullets":
            story.append(ListFlowable([ListItem(Paragraph(escape(x), ss["BodyText"])) for x in b.items],
                                      bulletType="bullet", leftIndent=12))
        elif b.kind == "table":
            data = [[Paragraph(escape(c), cell) for c in row] for row in b.rows]
            n = len(b.rows[0])
            first = 0.42 if n > 2 else 0.5
            col_w = [width * first] + [width * (1 - first) / (n - 1)] * (n - 1)
            if n == 3 and b.rows[0][0] == "Check":
                col_w = [width * 0.30, width * 0.12, width * 0.58]
            t = Table(data, colWidths=col_w, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3E9E0")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CFD8CC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story += [t, Spacer(1, 4)]
        elif b.kind == "disclaimer":
            story.append(Paragraph(escape(b.text), warn))
    pdf.build(story)
    return buf.getvalue()
