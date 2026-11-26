"""Module 3: Subscription Tracker (layout only)."""
from __future__ import annotations

import datetime as dt
import html

import pandas as pd
import streamlit as st

from ipodesk import subscription as sub
from ipodesk.config import disclaimer
from ipodesk.formatting import indian_group
from ipodesk.sample_data import sample_subscription
from ui_common import apply_theme, disclaimer_footer, md, wp_header

apply_theme()
head = st.container()

with st.container(key="sheet-input"):
    st.markdown("## Subscription data")
    src = st.radio("Data", ["Sample (synthetic)", "Upload CSV", "Enter by hand"], horizontal=True,
                   label_visibility="collapsed")
    template = pd.DataFrame([
        {"company": "My IPO Ltd", "day": 1, "category": c, "shares_offered": o, "shares_bid": b}
        for c, o, b in [("QIB", 2_000_000, 400_000), ("bNII", 1_000_000, 300_000), ("sNII", 500_000, 250_000),
                        ("Retail", 3_500_000, 2_800_000), ("Employee", 50_000, 20_000)]])
    if src.startswith("Sample"):
        raw = sample_subscription(dt.date.today()).drop(columns=["date", "subscription_x"])
        raw = raw[raw["category"] != "total"]
        st.caption("Three synthetic issues, cumulative by day, as the exchanges publish them.")
    elif src.startswith("Upload"):
        st.download_button("Download CSV template", template.to_csv(index=False), "subscription_template.csv", "text/csv")
        st.caption("Columns: company, day, category, shares_offered, shares_bid. Or company, day, category, "
                   "subscription_x when you only have the multiples.")
        up = st.file_uploader("Subscription CSV", type=["csv"])
        raw = pd.read_csv(up) if up is not None else None
    else:
        st.caption("One row per category per day. Totals are calculated for you.")
        raw = st.data_editor(template, num_rows="dynamic", hide_index=True, width="stretch", key="sub_manual")

if raw is None:
    with head:
        wp_header("Subscription Tracker", "Upload a CSV to start.", ["SOURCE CSV"])
    disclaimer_footer(disclaimer())
    st.stop()

data, errors = sub.load_subscription(raw)
for e in errors:
    st.error(e)
if data.empty:
    with head:
        wp_header("Subscription Tracker", "No valid rows yet.", [])
    disclaimer_footer(disclaimer())
    st.stop()

with st.container(key="sheet-update"):
    p1, p2 = st.columns([2, 1], vertical_alignment="bottom")
    company = p1.selectbox("IPO", sorted(data["company"].unique()))
    days = sorted(int(d) for d in data.loc[data["company"] == company, "day"].unique())
    day = p2.selectbox("Day", days, index=len(days) - 1, format_func=lambda d: f"Day {d} close")
    st.markdown("## Update to copy")
    st.code(sub.client_update(data, company, int(day)), language=None, wrap_lines=True)
    st.caption("Figures only, no view on demand. Copy with the icon at the top right of the box.")

with head:
    wp_header("Subscription Tracker",
              f"{company}: category-wise subscription by day, shares bid ÷ shares offered, cumulative as the "
              "exchanges publish it, with a neutral update line.",
              [f"DAY {day} OF {max(days)}"])

left, right = st.columns([1.6, 1], gap="medium")
with left, st.container(key="sheet-chart"):
    st.plotly_chart(sub.chart(data, company), width="stretch", config={"displaylogo": False})
    st.download_button("Download chart (PNG)", sub.chart_png(data, company),
                       f"{company[:40].replace(' ', '_')}_subscription.png", "image/png", icon=":material/download:")

with right, st.container(key="sheet-numbers"):
    st.markdown(f"## Day {day} numbers")
    table = sub.latest_table(data, company, int(day))
    rows = []
    for _, r in table.iterrows():
        is_total = r["Category"] == "Total"
        change = r["Change vs previous day"]
        change_txt = "-" if pd.isna(change) else f"+{change:.2f}" if change >= 0 else f"{change:.2f}"
        offered = f"<td class='n dim'>{indian_group(r['Shares offered'])}</td>" if "Shares offered" in table else ""
        rows.append(f"<tr><td>{'<b>' if is_total else ''}{html.escape(r['Category'])}{'</b>' if is_total else ''}</td>{offered}"
                    f"<td class='n'><b>{sub.fmt_x(r['Subscription (x)'])}</b></td><td class='n dim'>{change_txt}</td></tr>")
    off_head = "<th class='n'>Offered</th>" if "Shares offered" in table else ""
    md(f'<div class="sched-wrap"><table class="sched"><tr><th>Category</th>{off_head}<th class="n">Times</th>'
       f'<th class="n">vs prev.</th></tr>{"".join(rows)}</table></div>')

with st.container(key="sheet-explain"):
    st.markdown("## What the categories mean")
    md("""
<table class="sched">
<tr><th>Category</th><th>Who</th><th>Share of a mainboard issue</th></tr>
<tr><td><b>QIB</b></td><td>Mutual funds, insurers, banks, foreign portfolio investors. Watched closely because they study the business and valuation in depth. They often bid on the last day, so early QIB numbers can look low.</td><td>50%, of which up to 60% goes to anchor investors the day before opening (exchange figures exclude anchors)</td></tr>
<tr><td><b>NII</b></td><td>Individuals and entities bidding above ₹2 lakh: sNII ₹2–10 lakh, bNII above ₹10 lakh.</td><td>15% (one-third sNII, two-thirds bNII)</td></tr>
<tr><td><b>Retail</b></td><td>Bids up to ₹2 lakh. When oversubscribed, allotment is by lottery of one lot each.</td><td>35%</td></tr>
<tr><td><b>Employee</b></td><td>Eligible employees, when the company offers a reservation.</td><td>Separate quota</td></tr>
</table>""")
    st.caption("Times subscribed = shares bid ÷ shares offered. Total = all bids ÷ all shares offered, not an average. "
               "Subscription shows demand during the issue; it says nothing certain about listing price or returns.")

disclaimer_footer(disclaimer())
