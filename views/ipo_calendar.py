"""Module 2: IPO Calendar and client alert drafts (layout only)."""
from __future__ import annotations

import datetime as dt
import html

import pandas as pd
import streamlit as st

from ipodesk import calendar as cal
from ipodesk.config import disclaimer, get_settings, load_holidays
from ipodesk.formatting import indian_group, nice_date
from ipodesk.messages import drafts_for_date, drafts_for_ipo, send_telegram_test
from ipodesk.sample_data import sample_ipos
from ui_common import apply_theme, disclaimer_footer, md, wp_header

apply_theme()
ss = st.session_state
head = st.container()

# ------------------------------------------------------------------ data in
with st.expander("Data source, date and holidays", expanded="ipo_table" not in ss):
    src = st.radio("IPO list", ["Sample IPOs (synthetic)", "Upload CSV"], horizontal=True)
    if src.startswith("Upload"):
        template = sample_ipos(dt.date.today()).head(2).drop(columns=["min_investment"])
        st.download_button("Download CSV template", template.to_csv(index=False), "ipo_template.csv", "text/csv")
        up = st.file_uploader("IPO CSV", type=["csv"])
        if up is not None:
            raw = pd.read_csv(up)
            for col in ("open_date", "close_date"):
                if col in raw:
                    raw[col] = pd.to_datetime(raw[col], errors="coerce").dt.date
            good, errors = cal.validate_ipo_table(raw)
            for e in errors:
                st.error(e)
            ss["ipo_table"] = good
    else:
        ss["ipo_table"] = sample_ipos(dt.date.today()).drop(columns=["min_investment"])
    d1, d2 = st.columns(2)
    today = d1.date_input("Treat today as", dt.date.today(), format="DD/MM/YYYY",
                          help="Change this to see statuses and message drafts on another day.")
    extra = d2.text_input("Extra holidays (YYYY-MM-DD, comma separated)", "",
                          help="Added to config/holidays.yaml for this session.")
    holidays = set(load_holidays())
    for part in [p.strip() for p in extra.split(",") if p.strip()]:
        try:
            holidays.add(dt.date.fromisoformat(part))
        except ValueError:
            st.error(f"'{part}' is not a date. Use YYYY-MM-DD, for example 2026-12-25.")
    st.caption(f"{len(holidays)} exchange holidays loaded. Check config/holidays.yaml against the NSE circular each year.")

with st.expander("Add an IPO by hand"):
    with st.form("add_ipo", clear_on_submit=True):
        a1, a2 = st.columns([3, 1])
        name = a1.text_input("Company")
        board = a2.selectbox("Board", ["Mainboard", "SME"])
        b1, b2, b3, b4 = st.columns(4)
        low = b1.number_input("Band low (₹)", min_value=0.0, step=1.0)
        high = b2.number_input("Band high (₹)", min_value=0.0, step=1.0)
        lot = b3.number_input("Lot size", min_value=1, step=1)
        size = b4.number_input("Issue size (₹ cr)", min_value=0.0, step=10.0)
        c1, c2, c3 = st.columns([1, 1, 2])
        od = c1.date_input("Opens", format="DD/MM/YYYY")
        cd = c2.date_input("Closes", format="DD/MM/YYYY")
        link = c3.text_input("RHP link (SEBI)")
        if st.form_submit_button("Add IPO", type="primary"):
            new = pd.DataFrame([{"company": name, "board": board, "price_band_low": low, "price_band_high": high,
                                 "lot_size": lot, "open_date": od, "close_date": cd, "issue_size_cr": size,
                                 "rhp_link": link}])
            good, errors = cal.validate_ipo_table(new)
            if errors or not name.strip():
                st.error(errors[0] if errors else "Enter the company name.")
            else:
                ss["manual_ipos"] = pd.concat([ss.get("manual_ipos", pd.DataFrame()), good], ignore_index=True)
                st.success(f"Added {name}.")

table = pd.concat([ss.get("ipo_table", pd.DataFrame()), ss.get("manual_ipos", pd.DataFrame())], ignore_index=True)
with head:
    wp_header("IPO Calendar",
              "Status from today's date and the T+1 / T+2 / T+3 timeline on working days, with copy-ready client "
              "messages. " + ("Showing the synthetic sample IPOs." if src.startswith("Sample") else "Showing your CSV."),
              [f"TODAY {today:%d %b %Y}".upper(), f"IPOS {len(table)} · HOLIDAYS {len(holidays)}"])
if table.empty:
    st.info("No IPOs yet. Upload a CSV, use the sample, or add one by hand.")
    disclaimer_footer(disclaimer())
    st.stop()
ipos = cal.enrich(table, today, holidays)
events = cal.events(ipos)

# ------------------------------------------------------------------ schedule of IPOs
with st.container(key="sheet-ipos"):
    counts = ipos["status"].value_counts()
    st.markdown("## IPOs  ·  " + "  ·  ".join(f"{s} {int(counts.get(s, 0))}" for s in cal.STATUSES))
    order = {s: i for i, s in enumerate(["Open", "Allotment", "Closed", "Upcoming", "Listed"])}
    rows = []
    any_link = bool(ipos["rhp_link"].astype(str).str.strip().ne("").any())
    for _, r in ipos.sort_values(by="status", key=lambda s: s.map(order)).iterrows():
        link = (f"<td><a href='{html.escape(r['rhp_link'])}' target='_blank'>Open</a></td>" if r["rhp_link"]
                else "<td class='dim'>-</td>") if any_link else ""
        rows.append(
            f"<tr{' class=due' if r['close_date'] == today else ''}><td><b>{html.escape(r['company'])}</b></td>"
            f"<td class='dim'>{r['board']}</td><td><b>{r['status']}</b></td>"
            f"<td class='n'>₹{indian_group(r['price_band_low'])}–{indian_group(r['price_band_high'])}</td>"
            f"<td class='n'>{r['lot_size']}</td><td class='n'>₹{indian_group(r['min_investment'])}</td>"
            f"<td class='n'>{r['open_date']:%d %b}</td><td class='n'>{r['close_date']:%d %b}</td>"
            f"<td class='n'>{r['allotment_date']:%d %b}</td><td class='n'>{r['credit_date']:%d %b}</td>"
            f"<td class='n'>{r['listing_date']:%d %b}</td><td class='n'>{indian_group(r['issue_size_cr'], 1)}</td>{link}</tr>")
    md('<div class="sched-wrap"><table class="sched"><tr><th>Company</th><th>Board</th><th>Status</th>'
       '<th class="n">Band</th><th class="n">Lot</th><th class="n">Min. inv.</th><th class="n">Opens</th>'
       '<th class="n">Closes</th><th class="n">T+1 allot.</th><th class="n">T+2 credit</th><th class="n">T+3 list</th>'
       f'<th class="n">₹ cr</th>{"<th>RHP</th>" if any_link else ""}</tr>{"".join(rows)}</table></div>')
    st.caption("Blue rows close today. T+1 allotment, T+2 refunds and demat credit, T+3 listing, all on working days.")

# ------------------------------------------------------------------ this week + month
left, right = st.columns([1, 2], gap="medium")
with left, st.container(key="sheet-week"):
    start, end = cal.week_bounds(today)
    st.markdown(f"## This week · {start:%d %b} – {end:%d %b}")
    week = cal.this_week(events, today)
    if week.empty:
        st.write("No IPO events this week.")
    else:
        body = "".join(
            f"<tr{' class=due' if e['date'] == today else ''}><td class='dim'>{e['date']:%a %d}</td>"
            f"<td><b>{html.escape(e['event'])}</b><br><span class='dim'>{html.escape(e['company'])}</span></td></tr>"
            for _, e in week.iterrows())
        md(f'<table class="sched">{body}</table>')
        st.caption("Blue: today.")

with right, st.container(key="sheet-month"):
    month_options = sorted({(d.year, d.month) for d in events["date"]} | {(today.year, today.month)})
    mh, ms = st.columns([1, 1], vertical_alignment="center")
    mh.markdown("## Month")
    ym = ms.selectbox("Month", month_options, index=month_options.index((today.year, today.month)),
                      format_func=lambda t: dt.date(t[0], t[1], 1).strftime("%B %Y"), label_visibility="collapsed")
    by_day: dict[dt.date, list[str]] = {}
    for _, e in events.iterrows():
        css = e["event"].split()[0]
        short = e["company"].replace(" (Sample)", "").replace(" Ltd", "")
        by_day.setdefault(e["date"], []).append(
            f"<span class='ev ev-{css}' title='{html.escape(e['company'])}: {e['event']}'>{html.escape(short)}</span>")
    heads = "".join(f"<th>{d}</th>" for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    body = ""
    for week_days in cal.month_weeks(*ym):
        body += "<tr>"
        for d in week_days:
            if d is None:
                body += "<td class='off'></td>"
                continue
            klass = (["today"] if d == today else []) + ([] if cal.is_working_day(d, holidays) else ["off"])
            body += f"<td class='{' '.join(klass)}'><span class='day'>{d.day}</span>{''.join(by_day.get(d, []))}</td>"
        body += "</tr>"
    legend = "".join(f"<span><i class='ev-{k}'></i>{label}</span>" for k, label in
                     [("Opens", "Opens"), ("Last", "Last day"), ("Allotment", "Allotment"),
                      ("Refund", "Refund & credit"), ("Listing", "Listing")])
    md(f"<div class='cal-wrap'><table class='cal'><tr>{heads}</tr>{body}</table></div><div class='legend'>{legend}"
       f"<span>Shaded: weekend or holiday</span></div>")

# ------------------------------------------------------------------ messages
with st.container(key="sheet-messages"):
    st.markdown(f"## Client messages for {nice_date(today)}")
    todays = drafts_for_date(ipos, today)
    if not todays:
        st.write("No client messages are due today.")
    cols = st.columns(2) if len(todays) > 1 else [st.container()]
    for n, d in enumerate(todays):
        with cols[n % len(cols)]:
            st.markdown(f"**{d['event']}** · {d['company']}")
            st.code(d["text"], language=None, wrap_lines=True)
    st.markdown("### Draft any message")
    m1, m2 = st.columns(2)
    pick = m1.selectbox("IPO", list(ipos["company"]))
    event = m2.selectbox("Message", ["Opens", "Last day", "Allotment", "Listing"])
    text = drafts_for_ipo(ipos[ipos["company"] == pick].iloc[0])[event]
    st.code(text, language=None, wrap_lines=True)
    st.caption("Copy with the icon at the top right of the box, then send through the approved channel.")

    demo_mode = get_settings()["alerts"]["demo_mode"]
    with st.expander("Send to a test Telegram chat (demo only)"):
        st.write("Sends only to the test chat in secrets (TELEGRAM_TEST_CHAT_ID), and only while demo mode is on in "
                 f"config/settings.yaml (now **{'on' if demo_mode else 'off'}**). Never a client chat.")
        if st.toggle("I understand this goes to a test chat only", key="tg_ok") and st.button("Send this draft"):
            st.info(send_telegram_test(text))

disclaimer_footer(disclaimer())
