---
version: 1
slug: "home-py"
primary_target: "Home.py"
related_targets: ["pages/1_IPO_Note_Generator.py","pages/2_IPO_Calendar.py","pages/3_Subscription_Tracker.py"]
---

## Scope and mode
Whole app (Home router + Note Generator, IPO Calendar, Subscription Tracker). Mode: Operate. Audience first: an
interview panel in a ~5-minute walkthrough; role played: IPO desk staff and a reviewer. Desktop first, phone for checks.

## Direction contract
THESIS: Every figure is vouched like an auditor's working paper: a pencil tick when it is found on its RHP page, a blue
cross-reference to that page, a numbered red query when it is not. Refuses the category default of a white KPI-card
fintech dashboard with a blue accent and pill badges.

OWN-WORLD: Pale grey-green analysis ground (#EEF2EC) with near-white sheets (#FBFCFA) edged in sage hairlines
(#CFD8CC); graphite shell bar (#2B2F2A) carrying the module nav. Pencil green (#2E7D32) ticks, red pencil (#C62828)
queries and flags, cross-reference blue (#1E4E8C) for links and the only action colour. Public Sans for all UI;
JetBrains Mono only for references, codes and dates (RHP/106, W/P REF, Q1). Authored SVG tick and query marks.

STORY: The panel sees an RHP turned into a schedule of figures, each ticked to its page; the one planted error is a
red query that blocks sign-off until a reviewer initials it. They believe the AI is checked, the maths is Python and a
person decides; they watch the export unlock.

FIRST VIEWPORT: Graphite top bar: product mark left, modules as top navigation (Streamlit strips CSS-generated text, so the compliance line closes the working-paper meta block and every page footer). Below,
a sheet header: company title left, mono working-paper meta right (W/P REF, source, prepared date) over a 2px
graphite rule; one tally strip (ticked / re-referenced / open queries). Main column: the schedule of figures with tick
and cross-reference columns; right column: P/E at upper band, red flags, dashed reviewer sign-off box with the
primary action.

FORM: Working Papers, IMPECCABLE'S PICK (grounded list position 1); seed:3e734cdf4a47b161

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Constraints
Streamlit only: theme via .streamlit/config.toml, fonts self-hosted through static serving, CSS and HTML blocks for the
world's marks; every control stays a standard Streamlit widget. Compliance copy and disclaimer unchanged. Synthetic
data labelled. All 69 tests keep passing.

## Unresolved
None.
