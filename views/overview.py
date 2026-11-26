"""Overview: what the desk tool does, today's counts, and how it stays factual (layout only)."""
import datetime as dt
import html

import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

from ipodesk import calendar as cal
from ipodesk.config import disclaimer
from ipodesk.formatting import nice_date
from ipodesk.llm import has_api_key, load_llm_config
from ipodesk.sample_data import sample_ipos
from ui_common import apply_theme, disclaimer_footer, md, query, reref, tick, wp_header

apply_theme()
today = dt.date.today()
cfg = load_llm_config()
ipos = cal.enrich(sample_ipos(today).drop(columns=["min_investment"]), today, None)
events = cal.events(ipos)

wp_header(
    "IPO Desk Assistant",
    "Turns a 300–700 page RHP into a factual, reviewed IPO note, keeps the IPO calendar on working days, "
    "and tracks subscription. Every AI figure is checked against its page before a person signs off. "
    + (f"AI: {cfg.provider} {cfg.model}." if has_api_key(cfg.provider)
       else "No API key set: the sample RHP runs on offline demo answers."),
    [f"PREPARED {today:%d %b %Y}".upper()],
)

open_now = int((ipos["status"] == "Open").sum())
closing = ipos[ipos["close_date"] == today]["company"].tolist()
week = cal.this_week(events, today)
rows = [
    ("Note Generator", "views/note_generator.py",
     "Upload an RHP. Sections are found, figures extracted with page references and ticked against the PDF, "
     "valuation and red flags computed in Python, then a reviewer signs off and exports DOCX / PDF.",
     "Sample RHP ready · runs offline"),
    ("IPO Calendar", "views/ipo_calendar.py",
     "Status from today's date, the T+1 / T+2 / T+3 timeline on working days, a month view and "
     "copy-ready client messages.",
     f"{open_now} open now · {len(closing)} closing today · {len(week)} events this week"),
    ("Subscription Tracker", "views/subscription_tracker.py",
     "Category-wise subscription by day with a chart and a neutral one-line update to copy.",
     "3 sample issues loaded"),
]

with st.container(key="sheet-index"):
    st.markdown("## Modules")
    for name, page, what, today_line in rows:
        c1, c2, c3 = st.columns([1.1, 2.6, 1.3], vertical_alignment="center")
        with c1:
            try:
                st.page_link(page, label=name, icon=":material/arrow_forward:")
            except StreamlitPageNotFoundError:  # page run on its own, outside the Home.py router
                st.markdown(f"**{name}**")
        c2.markdown(what)
        c3.caption(today_line)

left, right = st.columns(2, gap="large")
with left, st.container(key="sheet-grounding"):
    st.markdown("## How a figure gets its tick")
    md(f"""
<table class="sched">
<tr><th>Mark</th><th>Meaning</th></tr>
<tr><td>{tick()}</td><td>The number the AI returned is printed on the RHP page it cited.</td></tr>
<tr><td>{reref()}</td><td>The number is real but sits on another page that was sent; the reference is corrected.</td></tr>
<tr class="flag"><td>{query("Q1")}</td><td>Not found in any page sent. Marked <b>verify manually</b>; export stays locked until a reviewer confirms it.</td></tr>
</table>""")
    st.markdown(
        "Numbers are normalised before matching: `31,519.68` → 31519.68, `(12.60)` → −12.60, Indian "
        "`10,00,00,000` → 100000000. P/E, market cap, margins and red flags are then computed in Python, "
        "never by the AI.")

with right, st.container(key="sheet-compliance"):
    st.markdown("## Compliance by design")
    md("""
<table class="sched">
<tr><th>Rule</th><th>How the app holds it</th></tr>
<tr><td>No ratings</td><td>Never "subscribe / avoid / buy", no return promises, no grey market premium. A word scan locks export.</td></tr>
<tr><td>Disclaimer</td><td>On every note, message, chart and page.</td></tr>
<tr><td>Human sign-off</td><td>A named reviewer edits, clears queries and signs before export. Nothing is sent to clients.</td></tr>
<tr><td>Public data</td><td>RHPs from SEBI's website; calendar and subscription from CSV or manual entry. No scraping.</td></tr>
<tr><td>Synthetic clients</td><td>Every client, bid and mandate is generated; PAN-like IDs are masked.</td></tr>
</table>""")

if not week.empty:
    with st.container(key="sheet-week"):
        st.markdown(f"## This week at the desk · {nice_date(today)}")
        body = "".join(
            f"<tr{' class=due' if e['event'] == 'Last day' else ''}><td class='dim'>{e['date']:%a %d %b}</td>"
            f"<td><b>{html.escape(e['event'])}</b></td><td>{html.escape(e['company'])}</td><td class='dim'>{e['board']}</td></tr>"
            for _, e in week.iterrows())
        md(f'<div class="sched-wrap"><table class="sched"><tr><th>Date</th><th>Event</th><th>Company</th>'
           f'<th>Board</th></tr>{body}</table></div>')
        st.caption("Sample IPOs. Last-day rows are tinted blue: clients must approve UPI mandates by 5 pm.")

disclaimer_footer(disclaimer())
