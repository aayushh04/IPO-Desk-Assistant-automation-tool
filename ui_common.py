"""Shared look for every page: the "Working Papers" world (layout only, no business logic).

The idea: the app reads like an auditor's working paper. Figures found on their RHP page get a green pencil
tick, a blue cross-reference to that page and, when they can't be found, a numbered red query that blocks
sign-off. Controls stay standard Streamlit widgets; the world only supplies type, palette, density and marks.
"""
from __future__ import annotations

import html
import os
from typing import Iterable, Literal

import streamlit as st

SECRET_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_TEST_CHAT_ID",
               "IPODESK_LLM_PROVIDER")

INK, GROUND, SHEET, RULE = "#2B2F2A", "#EEF2EC", "#FBFCFA", "#CFD8CC"
TICK_GREEN, QUERY_RED, XREF_BLUE, MUTED = "#2E7D32", "#C62828", "#1E4E8C", "#5B6458"

_CSS = f"""
<style>
:root {{ --ink:{INK}; --ground:{GROUND}; --sheet:{SHEET}; --rule:{RULE}; --tick:{TICK_GREEN};
        --query:{QUERY_RED}; --xref:{XREF_BLUE}; --muted:{MUTED}; }}
html, body {{ -webkit-font-smoothing: antialiased; }}
::selection {{ background: #D6E2F3; color: var(--ink); }}
* {{ caret-color: var(--xref); scrollbar-color: #B9C4B5 transparent; }}
a {{ text-underline-offset: 3px; }}
:focus-visible {{ outline: 2px solid var(--xref) !important; outline-offset: 2px; }}
table, [data-testid="stDataFrame"] {{ font-variant-numeric: tabular-nums; }}

/* Shell: graphite bar carrying the module navigation */
header[data-testid="stHeader"] {{ background: var(--ink); height: 3.5rem; }}
header[data-testid="stHeader"] a, header[data-testid="stHeader"] span, header[data-testid="stHeader"] p {{ color: #C9D2C6; }}
header[data-testid="stHeader"] a[aria-current="page"], header[data-testid="stHeader"] a[aria-current="page"] span {{ color: #FFFFFF; }}
header[data-testid="stHeader"] button svg {{ color: #C9D2C6; fill: #C9D2C6; }}
header[data-testid="stHeader"] [data-testid="stTopNavLink"][aria-current="page"] {{ background: #3D4339; }}
.block-container {{ padding-top: 5rem; padding-bottom: 3rem; max-width: 1320px; }}
@media (max-width: 640px) {{ .block-container {{ padding-left: .75rem; padding-right: .75rem; padding-top: 4.5rem; }} }}

/* Sheets: near-white paper with sage hairline edges */
div[class*="st-key-sheet"] {{ background: var(--sheet); border: 1px solid var(--rule); border-radius: 8px;
    padding: 1.25rem 1.5rem 1.4rem; box-shadow: 0 1px 2px rgba(43,47,42,.05); }}
@media (max-width: 640px) {{ div[class*="st-key-sheet"] {{ padding: 1rem; }} }}
div[class*="st-key-signoff"] {{ border: 1.5px dashed #9AA796; border-radius: 8px; padding: .6rem 1.1rem 1rem; background: #FFFFFF; }}
div[class*="st-key-signoff"] h2 {{ padding-top: .2rem !important; }}

/* Headings: weight and size, never labels above */
h1, h2, h3 {{ color: var(--ink); letter-spacing: -0.01em; }}
h2 {{ font-size: 1.15rem !important; font-weight: 700 !important; margin-top: .25rem; }}
h3 {{ font-size: 1rem !important; font-weight: 700 !important; }}

/* Working-paper header */
.wp-head {{ display:flex; justify-content:space-between; align-items:flex-end; gap:1.5rem;
    border-bottom: 2px solid var(--ink); padding-bottom: .9rem; margin-bottom: 1.1rem; flex-wrap: wrap; }}
.wp-head h1 {{ font-size: 1.85rem; font-weight: 700; line-height: 1.15; margin: 0; padding: 0; }}
.wp-head p {{ margin: .3rem 0 0; color: var(--muted); font-size: .95rem; max-width: 68ch; }}
.wp-meta {{ font: 500 .78rem/1.75 "JetBrains Mono", monospace; color: var(--muted); text-align: right; letter-spacing: .02em; }}
@media (max-width: 640px) {{ .wp-meta {{ text-align: left; }} .wp-head h1 {{ font-size: 1.45rem; }} }}

/* Marks: the world's signature, drawn not typed */
.mk {{ display:inline-flex; align-items:center; vertical-align:-2px; margin-left:.35rem; }}
.q {{ display:inline-flex; align-items:center; font: 600 .72rem/1 "JetBrains Mono", monospace; color: var(--query);
    border: 1.5px solid var(--query); border-radius: 4px; padding: .12rem .3rem; margin-left: .35rem; vertical-align: 1px; }}
.xref {{ font: 600 .8rem "JetBrains Mono", monospace; color: var(--xref); text-decoration: underline; white-space: nowrap; }}

/* Tally strip */
.tally {{ display:grid; grid-template-columns: repeat(3, 1fr); border: 1px solid var(--rule); border-radius: 6px;
    background: #FFFFFF; margin: .2rem 0 1rem; }}
.tally > div {{ padding: .7rem 1rem; border-left: 1px solid var(--rule); display: flex; flex-direction: column;
    justify-content: space-between; }}
.tally > div:first-child {{ border-left: 0; }}
.tally span {{ display:block; font-size: .8rem; font-weight: 600; color: var(--muted); }}
.tally b {{ display:flex; align-items:center; gap:.45rem; font-size: 1.7rem; font-weight: 700; line-height: 1.2;
    font-variant-numeric: tabular-nums; }}
.tally .red b {{ color: var(--query); }}
@media (max-width: 640px) {{ .tally b {{ font-size: 1.3rem; }} .tally > div {{ padding: .55rem .6rem; }} }}

/* Schedules (read views of tabular figures) */
.sched-wrap {{ overflow-x: auto; }}
table.sched {{ width:100%; border-collapse: collapse; font-size: .92rem; font-variant-numeric: tabular-nums; }}
table.sched th {{ text-align:left; font-size:.72rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
    color: var(--muted); padding: .4rem .6rem; border-bottom: 1.5px solid var(--ink); white-space: nowrap; }}
table.sched td {{ padding: .55rem .6rem; border-bottom: 1px solid #E1E7DF; vertical-align: middle; }}
table.sched td.n, table.sched th.n {{ text-align: right; white-space: nowrap; }}
table.sched tr.flag td {{ background: #FCEFEE; }}
table.sched td.dim {{ color: var(--muted); }}
table.sched td.mark {{ width: 2rem; padding-right: 0; }}
.show-sm {{ display: none; }}
table.sched td.small {{ font-size: .8rem; }}
@media (max-width: 640px) {{
  .hide-sm {{ display: none; }}
  table.sched {{ font-size: .8rem; }}
  table.sched td, table.sched th {{ padding: .42rem .3rem; }}
  table.sched td:first-child:not(.mark) {{ min-width: 6.5rem; }}
  table.sched .mk {{ margin-left: .2rem; }}
  .xref {{ font-size: .72rem; }}
  .show-sm {{ display: inline-flex !important; }}
  .lead .big {{ font-size: 2.4rem; }}
}}
.span-bar {{ position: relative; height: 8px; background: #E4EAE2; border-radius: 2px; min-width: 120px; }}
.span-bar i {{ position: absolute; top: 0; height: 8px; background: var(--ink); border-radius: 2px; }}

/* Lead figure: the panel's own heading, then the one number that owns it */
.lead h2 {{ margin: 0 0 .1rem; padding: 0; }}
.lead .big {{ font-size: 3rem; font-weight: 700; line-height: 1.05; font-variant-numeric: tabular-nums; margin: .1rem 0 .2rem; }}
.lead p {{ margin: 0 0 .6rem; color: var(--muted); font-size: .9rem; }}

/* Fact list */
dl.facts {{ display:grid; grid-template-columns: auto 1fr; gap: .35rem 1rem; margin: 0; font-size: .9rem; }}
dl.facts dt {{ color: var(--muted); }}
dl.facts dd {{ margin: 0; text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }}

/* Flag rows */
.flags {{ display:flex; flex-direction:column; }}
.flag-row {{ display:grid; grid-template-columns: 1fr auto; gap: .2rem 1rem; padding: .55rem 0; border-bottom: 1px solid #E1E7DF; }}
.flag-row b {{ font-size: .92rem; font-weight: 600; }}
.flag-row em {{ font-style: normal; font-size: .8rem; font-weight: 700; display:flex; align-items:center; gap:.3rem; }}
.flag-row em.flag {{ color: var(--query); }} .flag-row em.ok {{ color: var(--tick); }} .flag-row em.nodata {{ color: var(--muted); }}
.flag-row small {{ grid-column: 1 / -1; color: var(--muted); font-size: .82rem; line-height: 1.45; }}

/* Steps: the note's sequence. Done steps carry a tick; the current step is outlined in ink (blue is for actions only) */
.steps {{ display:flex; gap:.4rem; flex-wrap: wrap; margin: 0 0 1rem; }}
.steps > span {{ display:inline-flex; align-items:center; font-size: .82rem; font-weight: 600; padding: .3rem .7rem;
    border-radius: 4px; background: #E3E9E0; color: var(--muted); border: 1.5px solid transparent; }}
.steps > span.done {{ background: #DDEBDD; color: #23602A; }}
.steps > span.done .mk {{ margin: 0 .3rem 0 0; }}
.steps > span.on {{ background: #FFFFFF; color: var(--ink); border-color: var(--ink); }}

/* A cleared query: the auditor's tick drawn over the query box, once, when the reviewer confirms */
.q.cleared {{ color: var(--tick); border-color: var(--tick); position: relative; }}
.q.cleared svg {{ position: absolute; left: 50%; top: 50%; transform: translate(-45%, -60%); overflow: visible; }}
.q.cleared path {{ stroke-dasharray: 24; stroke-dashoffset: 0; animation: draw-tick .55s cubic-bezier(.16,1,.3,1) both; }}
@keyframes draw-tick {{ from {{ stroke-dashoffset: 24; }} to {{ stroke-dashoffset: 0; }} }}
@media (prefers-reduced-motion: reduce) {{ .q.cleared path {{ animation: none; }} }}

/* Reviewer stamp */
.stamp {{ font: 600 .8rem/1.6 "JetBrains Mono", monospace; color: var(--xref); letter-spacing: .03em; margin: .2rem 0 .6rem; }}

/* Overview module links read as row headings */
div.st-key-sheet-index [data-testid="stPageLink"] p {{ font-size: 1rem; font-weight: 600; color: var(--xref); }}

/* Queries list */
.queries p {{ margin: .25rem 0; font-size: .9rem; color: #8E1F1F; }}
.queries.done p {{ color: var(--ink); }}
.cleared-note {{ display:inline-flex; align-items:center; font-size: .8rem; font-weight: 600; color: var(--tick); margin-left: .6rem; }}
.flag-summary {{ display:flex; align-items:flex-start; gap:.4rem; margin-top: .5rem; padding-top: .45rem;
    border-top: 1px solid #E1E7DF; font-size: .86rem; color: #8E1F1F; }}
.flag-summary.none {{ color: var(--tick); }}

/* Compliance line in the shell's footer */
.disclaimer {{ margin-top: 2rem; padding-top: .9rem; border-top: 1px solid var(--rule); font-size: .82rem; color: var(--muted); }}

/* Calendar month grid */
.cal-wrap {{ overflow-x: auto; }}
.cal {{ border-collapse: collapse; width: 100%; min-width: 600px; font-size: .78rem; table-layout: fixed; }}
.cal th {{ padding: .35rem; text-align: left; font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }}
.cal td {{ border: 1px solid #DCE3D9; vertical-align: top; height: 84px; padding: .3rem; background: #FFFFFF; }}
.cal .day {{ font: 600 .75rem "JetBrains Mono", monospace; color: var(--muted); }}
.cal td.today {{ outline: 2px solid var(--xref); outline-offset: -2px; }}
.cal td.today .day {{ color: var(--xref); }}
.cal td.off {{ background: #F1F4EF; }}
.ev {{ display:block; border-radius: 3px; padding: .1rem .3rem; margin-top: .2rem; line-height: 1.3; color: var(--ink);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }}
/* Event chips from the world's own inks: green, blue, sage, ink; the last day is outlined, not query-red */
.ev-Opens {{ background: #DDEBDD; }} .ev-Last {{ background: #FFFFFF; box-shadow: inset 0 0 0 1.5px var(--ink); }}
.ev-Allotment {{ background: #DCE5F2; }} .ev-Refund {{ background: #E3E9E0; }}
.ev-Listing {{ background: var(--ink); color: #FFFFFF; }}
table.sched tr.due td {{ background: #EAF0F8; }}
.legend {{ display:flex; flex-wrap:wrap; gap:.4rem .9rem; font-size:.8rem; color: var(--muted); margin-top:.6rem; }}
.legend i {{ display:inline-block; width:.8rem; height:.8rem; border-radius:2px; margin-right:.3rem; vertical-align:-1px; }}
</style>
"""


def load_secrets_into_env() -> None:
    """Copy known keys from Streamlit secrets into environment variables (the ipodesk package reads env)."""
    try:
        for key in SECRET_KEYS:
            if key in st.secrets and not os.getenv(key):
                os.environ[key] = str(st.secrets[key])
    except Exception:  # no secrets file locally is fine
        pass


def apply_theme() -> None:
    """Inject the world's CSS and load secrets. Safe to call on every page run."""
    st.html(_CSS)  # st.html, not st.markdown: Markdown would curl the quotes inside the CSS
    load_secrets_into_env()


# ------------------------------------------------------------------ marks (authored SVG)

def tick(color: str = TICK_GREEN, size: int = 15) -> str:
    """A pencil tick: the figure was found on the page it cites."""
    return (f'<span class="mk" title="Ticked to source"><svg width="{size}" height="{size}" viewBox="0 0 16 16" '
            f'aria-label="ticked to source" role="img"><path d="M2.4 8.9 6.1 12.4 13.8 3.3" fill="none" '
            f'stroke="{color}" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/></svg></span>')


def reref(size: int = 15) -> str:
    """A blue tick in a dashed ring: the figure is real but sits on a different page than cited."""
    return (f'<span class="mk" title="Found on another page"><svg width="{size}" height="{size}" viewBox="0 0 16 16" '
            f'aria-label="page re-referenced" role="img"><circle cx="8" cy="8" r="6.6" fill="none" stroke="{XREF_BLUE}" '
            f'stroke-width="1.3" stroke-dasharray="2.2 1.8"/><path d="M4.8 8.3 7.1 10.5 11.4 5.6" fill="none" '
            f'stroke="{XREF_BLUE}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>')


def query(label: str) -> str:
    """A numbered red query: the figure could not be found and must be verified."""
    return f'<span class="q" title="Not found in the RHP text: verify manually">{html.escape(label)}</span>'


def cleared(label: str) -> str:
    """A query the reviewer has confirmed: the tick is drawn over the query box (one short stroke animation)."""
    return (f'<span class="q cleared" title="Query cleared by the reviewer">{html.escape(label)}<svg width="18" height="18" '
            f'viewBox="0 0 16 16" aria-label="cleared" role="img"><path d="M2.4 8.9 6.1 12.4 13.8 3.3" fill="none" '
            f'stroke="{TICK_GREEN}" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/></svg></span>')


def nodata_mark(size: int = 13) -> str:
    """A short graphite dash: no data to check."""
    return (f'<span class="mk"><svg width="{size}" height="{size}" viewBox="0 0 16 16" aria-label="no data" role="img">'
            f'<path d="M3.5 8h9" stroke="{MUTED}" stroke-width="2" stroke-linecap="round"/></svg></span>')


def xref(page: int | None) -> str:
    """Cross-reference to an RHP page, e.g. RHP/106."""
    return f'<span class="xref">RHP/{page}</span>' if page else '<span class="xref">-</span>'


# ------------------------------------------------------------------ blocks

def md(markup: str) -> None:
    """Render trusted HTML built by these helpers."""
    st.markdown(markup, unsafe_allow_html=True)


def wp_header(title: str, subtitle: str = "", meta: Iterable[str] = ()) -> None:
    """Working-paper header: title and one-line purpose left, mono reference lines right, graphite rule below."""
    meta_html = "<br>".join(html.escape(m) for m in [*meta, "INFORMATION ONLY · NOT A RECOMMENDATION"])
    sub = f"<p>{html.escape(subtitle)}</p>" if subtitle else ""
    md(f'<div class="wp-head"><div><h1>{html.escape(title)}</h1>{sub}</div><div class="wp-meta">{meta_html}</div></div>')


def tally(ticked: int, rereferenced: int, queries: int, cleared_count: int = 0) -> None:
    """One strip: figures ticked, re-referenced, and still-open queries (cleared ones are counted apart)."""
    note = f'<small class="cleared-note">{cleared_count} cleared{tick(size=13)}</small>' if cleared_count else ""
    md(f'<div class="tally"><div><span>Ticked to source</span><b>{ticked}{tick(size=18)}</b></div>'
       f'<div><span>On another page</span><b>{rereferenced}{reref(18)}</b></div>'
       f'<div class="{"red" if queries else ""}"><span>Open queries</span><b>{queries}{note}</b></div></div>')


def steps(labels: list[str], current: int) -> None:
    """The note's five-step sequence; steps before `current` are done, `current` is highlighted."""
    parts = []
    for i, label in enumerate(labels):
        cls = "done" if i < current else ("on" if i == current else "")
        mark = tick(size=12) if i < current else ""
        parts.append(f'<span class="{cls}">{mark}{html.escape(label)}</span>')
    md(f'<div class="steps">{"".join(parts)}</div>')


def lead(label: str, value: str, note: str = "") -> None:
    """The one figure that owns a panel."""
    md(f'<div class="lead"><h2>{html.escape(label)}</h2><div class="big">{html.escape(value)}</div>'
       f'<p>{html.escape(note)}</p></div>')


def facts(rows: list[tuple[str, str]]) -> None:
    """A compact two-column fact list."""
    body = "".join(f"<dt>{html.escape(k)}</dt><dd>{html.escape(v)}</dd>" for k, v in rows)
    md(f'<dl class="facts">{body}</dl>')


FlagStatus = Literal["flag", "ok", "no data"]


def flag_rows(rows: list[tuple[str, FlagStatus, str]]) -> None:
    """Red-flag checklist rows: name, status word with its mark, and the reason underneath."""
    label = {"flag": ("flag", "Flag"), "ok": ("ok", "Clear"), "no data": ("nodata", "No data")}
    out = []
    for name, status, reason in rows:
        cls, word = label[status]
        mark = query("!") if status == "flag" else (tick(size=13) if status == "ok" else nodata_mark())
        why = f'<small>{html.escape(reason)}</small>' if status == "flag" else ""  # only flagged rows explain
        out.append(f'<div class="flag-row" title="{html.escape(reason)}"><b>{html.escape(name)}</b>'
                   f'<em class="{cls}">{word}{mark}</em>{why}</div>')
    md(f'<div class="flags">{"".join(out)}</div>')


def flag_summary(names: list[str]) -> None:
    """One line naming the triggered red flags, for the first viewport."""
    if names:
        md(f'<div class="flag-summary">{query("!")}<span><b>{len(names)} red flag{"s" if len(names) > 1 else ""}:</b> '
           f'{html.escape("; ".join(names))}. Details below.</span></div>')
    else:
        md(f'<div class="flag-summary none">{tick(size=13)}<span>No red flags triggered.</span></div>')


def disclaimer_footer(text: str) -> None:
    """The compliance line, closing every page."""
    md(f'<div class="disclaimer">{html.escape(text)} All client data in this app is synthetic.</div>')
