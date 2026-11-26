---
name: IPO Desk Assistant
description: An RHP turned into an auditor's working paper, every figure ticked to its page before a reviewer signs off.
colors:
  graphite-ink: "#2B2F2A"
  graphite-muted: "#5B6458"
  analysis-ground: "#EEF2EC"
  sheet-paper: "#FBFCFA"
  blank-white: "#FFFFFF"
  sage-hairline: "#CFD8CC"
  sage-row-rule: "#E1E7DF"
  sage-wash: "#E3E9E0"
  signoff-dash: "#9AA796"
  shell-text: "#C9D2C6"
  shell-active: "#3D4339"
  pencil-green: "#2E7D32"
  pencil-green-wash: "#DDEBDD"
  red-pencil: "#C62828"
  red-pencil-deep: "#8E1F1F"
  red-pencil-wash: "#FCEFEE"
  cross-reference-blue: "#1E4E8C"
  cross-reference-wash: "#DCE5F2"
  chart-umber: "#7A5C2E"
  chart-ochre: "#B08A3E"
  chart-plum: "#8E5A9C"
typography:
  display:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "1.85rem"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.01em"
  lead-figure:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "3rem"
    fontWeight: 700
    lineHeight: 1.05
    fontFeature: "tnum"
  tally-figure:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "1.7rem"
    fontWeight: 700
    lineHeight: 1.2
    fontFeature: "tnum"
  headline:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 700
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "1rem"
    fontWeight: 700
  body:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "15px"
    fontWeight: 400
  label:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "0.72rem"
    fontWeight: 700
    letterSpacing: "0.08em"
  mono-reference:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "0.78rem"
    fontWeight: 500
    lineHeight: 1.75
    letterSpacing: "0.02em"
  mono-mark:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "0.72rem"
    fontWeight: 600
    lineHeight: 1
rounded:
  hair: "2px"
  chip: "3px"
  mark: "4px"
  strip: "6px"
  sheet: "8px"
spacing:
  cell: "0.6rem"
  row: "0.55rem"
  block: "1rem"
  sheet-y: "1.25rem"
  sheet-x: "1.5rem"
  gutter-sm: "0.75rem"
components:
  button-primary:
    backgroundColor: "{colors.cross-reference-blue}"
    textColor: "{colors.blank-white}"
    rounded: "{rounded.mark}"
  shell-bar:
    backgroundColor: "{colors.graphite-ink}"
    textColor: "{colors.shell-text}"
    height: "3.5rem"
  shell-link-active:
    backgroundColor: "{colors.shell-active}"
    textColor: "{colors.blank-white}"
  sheet:
    backgroundColor: "{colors.sheet-paper}"
    rounded: "{rounded.sheet}"
    padding: "1.25rem 1.5rem 1.4rem"
  signoff-box:
    backgroundColor: "{colors.blank-white}"
    rounded: "{rounded.sheet}"
    padding: "1rem 1.1rem"
  tally-strip:
    backgroundColor: "{colors.blank-white}"
    typography: "{typography.tally-figure}"
    rounded: "{rounded.strip}"
  query-mark:
    textColor: "{colors.red-pencil}"
    typography: "{typography.mono-mark}"
    rounded: "{rounded.mark}"
    padding: "0.12rem 0.3rem"
  query-mark-cleared:
    textColor: "{colors.pencil-green}"
    rounded: "{rounded.mark}"
  xref:
    textColor: "{colors.cross-reference-blue}"
    typography: "{typography.mono-mark}"
  step:
    backgroundColor: "{colors.sage-wash}"
    textColor: "{colors.graphite-muted}"
    rounded: "{rounded.mark}"
    padding: "0.3rem 0.7rem"
  step-done:
    backgroundColor: "{colors.pencil-green-wash}"
    textColor: "{colors.pencil-green}"
  step-current:
    backgroundColor: "{colors.blank-white}"
    textColor: "{colors.graphite-ink}"
  schedule-row-flagged:
    backgroundColor: "{colors.red-pencil-wash}"
  event-opens:
    backgroundColor: "{colors.pencil-green-wash}"
    textColor: "{colors.graphite-ink}"
    rounded: "{rounded.chip}"
  event-allotment:
    backgroundColor: "{colors.cross-reference-wash}"
    textColor: "{colors.graphite-ink}"
    rounded: "{rounded.chip}"
  event-refund:
    backgroundColor: "{colors.sage-wash}"
    textColor: "{colors.graphite-ink}"
    rounded: "{rounded.chip}"
  event-last-day:
    backgroundColor: "{colors.blank-white}"
    textColor: "{colors.graphite-ink}"
    rounded: "{rounded.chip}"
  event-listing:
    backgroundColor: "{colors.graphite-ink}"
    textColor: "{colors.blank-white}"
    rounded: "{rounded.chip}"
---

# Design System: IPO Desk Assistant

## Overview

**Creative North Star: "Working Papers"**

The app reads like an auditor's working paper. A pale grey-green analysis ground holds near-white sheets edged in sage hairlines; a graphite shell bar carries the module navigation and the product mark. Every figure the model returns is vouched for in pencil: a green tick when it is found on the RHP page it cites, a blue cross-reference to that page, and a numbered red query when it cannot be found. An open query blocks sign-off until a reviewer clears it, and the clearing is drawn as a tick over the query box.

Density is that of a schedule, not a dashboard: hairline-ruled tables with tabular numerals, one lead figure per panel, compact fact lists, a single tally strip. Colour is ink on paper. Green, red and blue are pencil colours with fixed meanings; everything else is graphite and sage. The world refuses the white KPI-card fintech dashboard with a blue accent and pill badges.

The world lives inside Streamlit. Every control is a standard Streamlit widget themed through `.streamlit/config.toml`; the world supplies type, palette, density and the authored SVG marks through one CSS block injected with `st.html` (never `st.markdown`, which curls the quotes inside CSS). Sheets are keyed containers (`st-key-sheet-*`, `st-key-signoff`). Streamlit strips CSS-generated text, so no copy, label or glyph may come from `::before`/`::after` content.

**Key Characteristics:**
- Graphite shell bar, grey-green ground, near-white hairline sheets.
- Pencil marks with fixed meanings: green tick (found), blue cross-reference (page), red numbered query (not found).
- Working-paper header: title and one-line purpose left, mono reference block right, 2px graphite rule below.
- Public Sans for all UI; JetBrains Mono only for references, codes and dates.
- Tabular numerals on every figure; schedules ruled, not carded.

## Colors

Graphite ink on grey-green paper, with three pencil colours that each mean one thing.

### Primary
- **Cross-Reference Blue** (cross-reference-blue): the only action colour. Primary buttons, links, focus outlines, caret, RHP page references, the dashed re-reference mark, the reviewer stamp, and today's cell in the calendar.
- **Cross-Reference Wash** (cross-reference-wash): allotment event chips.

### Secondary
- **Pencil Green** (pencil-green): the tick. Figures found on their page, done steps, cleared queries, "Clear" flag rows, "No red flags triggered".
- **Pencil Green Wash** (pencil-green-wash): background of done steps and opening-day event chips.

### Tertiary
- **Red Pencil** (red-pencil): queries and red flags only. The query box, open-query count, flagged status word.
- **Red Pencil Deep** (red-pencil-deep): running text that reports queries and flags (query list, flag summary line), where full red would shout.
- **Red Pencil Wash** (red-pencil-wash): background of a schedule row that carries an open query.

### Neutral
- **Graphite Ink** (graphite-ink): text, headings, the shell bar, the 2px header rule, schedule header rule, current-step outline, listing-day chips.
- **Graphite Muted** (graphite-muted): secondary text, table header labels, fact-list terms, mono meta, the no-data dash.
- **Analysis Ground** (analysis-ground): the page background.
- **Sheet Paper** (sheet-paper): sheet surfaces, chart paper.
- **Blank White** (blank-white): surfaces that sit proud of a sheet: tally strip, sign-off box, calendar cells, current step.
- **Sage Hairline** (sage-hairline): sheet edges, tally dividers, widget borders, footer rule.
- **Sage Row Rule** (sage-row-rule): rules between schedule rows, flag rows, chart gridlines.
- **Sage Wash** (sage-wash): Streamlit secondary background (inputs, expanders), pending steps, refund chips, PDF table header.
- **Signoff Dash** (signoff-dash): the dashed edge of the reviewer sign-off box.
- **Shell Text** (shell-text) and **Shell Active** (shell-active): navigation text on the graphite bar and the active link's plate.

### Chart-only
- **Chart Umber**, **Chart Ochre**, **Chart Plum** (chart-umber, chart-ochre, chart-plum): subscription categories (NII, small NII, Employee) beside blue (QIB), green (Retail) and graphite (Total, drawn heavier). These never appear outside charts.

### Named Rules
**The Pencil Meaning Rule.** Green means found, red means not found or flagged, blue means a reference, an action, or today's place on the calendar. A pencil colour is never used for decoration or for a meaning it does not carry.

**The Red Is For Queries Rule.** Red marks only open queries and red flags. Deadlines are not queries: the calendar's last day is outlined in graphite, never red.

## Typography

**Display Font:** Public Sans (self-hosted, with sans-serif)
**Body Font:** Public Sans
**Label/Mono Font:** JetBrains Mono (self-hosted, with monospace)

**Character:** A plain public-sector grotesque doing the work of a ledger hand, paired with a mono that appears only where a clerk would write a reference.

### Hierarchy
- **Display** (700, 1.85rem, 1.15; 1.45rem under 640px): the working-paper title, one per page.
- **Lead Figure** (700, 3rem, 1.05, tabular; 2.4rem under 640px): the one number that owns a panel, such as P/E at upper band.
- **Tally Figure** (700, 1.7rem, 1.2, tabular): counts in the tally strip, each followed by its mark.
- **Headline** (700, 1.15rem): sheet headings (`##`).
- **Title** (700, 1rem): sub-headings inside a sheet (`###`).
- **Body** (400, 15px base): running text, schedule cells at 0.92rem, fact lists at 0.9rem. Header purpose lines cap at 68ch.
- **Label** (700, 0.72rem, 0.08em, uppercase): table column headers and calendar weekday headers only.
- **Mono Reference** (500, 0.78rem, 0.02em): working-paper meta block (W/P REF, source, prepared date, compliance line).
- **Mono Mark** (600, 0.72-0.8rem): query labels (Q1), RHP page references (RHP/106), calendar day numbers, the reviewer stamp.

### Named Rules
**The Clerk's Hand Rule.** JetBrains Mono is for references, codes and dates. Prose, headings and figures are Public Sans. The one exception is a copy-ready client message shown in a Streamlit code block, which is Streamlit's copy affordance.

**The Heading Is The Label Rule.** Sections are named by weight and size alone. No kicker or eyebrow sits above a heading.

## Layout

A wide single page (`layout="wide"`) capped at 1320px, padded 5rem from the top to clear the 3.5rem shell bar. Each page opens with the working-paper header, then stacks keyed sheets; two-column splits (schedule left, valuation and sign-off right; week left, month right; chart left, numbers right) use Streamlit columns. Sheets pad 1.25rem by 1.5rem; table cells pad 0.55rem by 0.6rem; flag rows pad 0.55rem vertically. The rhythm is tight and rule-driven rather than gap-driven.

At 640px and below: side gutters drop to 0.75rem, sheets pad 1rem, the header meta block left-aligns, schedule text drops to 0.8rem with 0.3rem cell padding, `.hide-sm` columns disappear and `.show-sm` substitutes appear. Wide tables (schedules, the 600px-minimum calendar) scroll inside their own wrapper, never the page.

## Elevation & Depth

Flat paper on a ground. Depth comes from tone (ground, sheet paper, blank white) and from hairline borders, not shadow. Sheets carry one barely-there contact shadow so they read as paper laid down.

### Shadow Vocabulary
- **Paper contact** (`box-shadow: 0 1px 2px rgba(43,47,42,.05)`): sheets only.
- **Inset outline** (`box-shadow: inset 0 0 0 1.5px #2B2F2A`): the last-day calendar chip, an outline drawn inside the chip.

### Named Rules
**The Paper On A Desk Rule.** Surfaces are flat. Nothing lifts on hover; a sheet's only shadow is its contact shadow.

## Shapes

Small, quiet corners that tighten as the object shrinks: sheets and the sign-off box 8px, the tally strip 6px, query boxes and steps 4px, calendar event chips 3px, bars and legend swatches 2px. Streamlit widgets use the theme's `small` radius. Borders are hairlines (1px sage) except where a line carries meaning: the 2px graphite header rule, the 1.5px graphite schedule header rule, the 1.5px red query border, the 1.5px dashed sign-off edge. No pills.

## Components

### Buttons
- **Shape:** Streamlit button with the theme's small radius.
- **Primary:** cross-reference blue fill with white text, one per sheet at most: "Run AI extraction", "Add IPO", "Download note (PDF)".
- **Locked:** the primary export stays visible but disabled with a lock icon until every query is cleared and the reviewer has signed.
- **Secondary:** default Streamlit buttons and download buttons on the sage-bordered theme.

### Navigation
- **Style:** Streamlit top navigation on a 3.5rem graphite bar; product mark (ruled square with a pencil tick, authored SVG) at left; links in shell text with Material icons; the current page in white on a shell-active plate. Mobile uses Streamlit's own overflow menu.

### Cards / Containers (Sheets)
- **Corner Style:** 8px.
- **Background:** sheet paper on the analysis ground.
- **Shadow Strategy:** paper contact shadow only.
- **Border:** 1px sage hairline.
- **Internal Padding:** 1.25rem 1.5rem 1.4rem (1rem on phones).

### Inputs / Fields
- **Style:** standard Streamlit widgets: sage-wash fill, sage hairline border, small radius.
- **Focus:** 2px cross-reference blue outline, 2px offset, on every focusable element.

### Working-Paper Header
Title and one-line purpose at left; a right-aligned mono reference block (W/P REF, source, prepared date) that always ends with "INFORMATION ONLY · NOT A RECOMMENDATION"; a 2px graphite rule beneath.

### Pencil Marks (signature)
Authored inline SVG, never glyphs or icon fonts.
- **Tick:** a green pencil stroke (2.3 width, round caps): found on the cited page.
- **Re-reference:** a blue tick inside a dashed blue ring: real figure, different page.
- **Query:** a numbered red mono label in a 1.5px red box (Q1, or "!" for a flag).
- **Cleared query:** the box turns green and a tick is drawn over it once (0.55s, `cubic-bezier(.16,1,.3,1)` stroke draw; none under reduced motion).
- **No data:** a short graphite-muted dash.
- **Cross-reference:** underlined blue mono "RHP/106".

### Tally Strip
Three equal cells on blank white in a 6px hairline box: Ticked to source, On another page, Open queries. Each count carries its mark; the queries count turns red when non-zero, and cleared queries are counted apart in green.

### Schedule
Ruled table: uppercase muted labels over a 1.5px graphite rule, sage row rules, right-aligned tabular numbers with the mark inline after each figure, an REF column of cross-references. A row with an open query takes the red wash. Computed rows cite "Python" instead of a page.

### Steps
The note's five-step sequence as small 4px plates: done steps in green wash with a tick, the current step outlined in graphite on white, pending steps in sage wash.

### Reviewer Sign-off
A blank-white box with a 1.5px dashed signoff-dash edge, holding the reviewer name, query-clearing checkboxes and the locked or unlocked export. Once signed, a blue mono stamp records who reviewed it.

### Flag Rows and Flag Summary
Checklist rows: name left, status word with its mark right (Flag in red, Clear in green, No data in muted), and only flagged rows explain themselves underneath. The summary line above them names triggered flags in deep red after a query mark, or states "No red flags triggered" with a tick.

### Calendar
A month grid of white 84px cells with muted mono day numbers, shaded off-days, and today outlined in 2px blue. Event chips use the world's own inks: opens green wash, allotment blue wash, refund sage wash, listing solid graphite, last day outlined in graphite.

## Do's and Don'ts

### Do:
- **Do** vouch for every model-returned figure with a mark: tick, re-reference or numbered query.
- **Do** draw marks as authored inline SVG in the pencil colours.
- **Do** keep cross-reference blue as the single action colour, with one primary button per sheet at most.
- **Do** set every figure in tabular numerals and right-align numeric columns.
- **Do** open every page with the working-paper header and close it with the compliance footer.
- **Do** carry sheet styling on keyed containers (`st-key-sheet-*`, `st-key-signoff`) and inject the world CSS with `st.html`.
- **Do** keep every control a standard Streamlit widget.

### Don't:
- **Don't** build white KPI cards with a blue accent and pill badges.
- **Don't** use red for anything but open queries and red flags; outline deadlines in graphite.
- **Don't** set prose, headings or figures in JetBrains Mono (copy-ready messages in code blocks excepted).
- **Don't** put a kicker or eyebrow label above a heading.
- **Don't** generate text, labels or glyphs with CSS `content`; Streamlit strips it.
- **Don't** inject the world CSS with `st.markdown`; it curls the quotes.
- **Don't** let the chart-only umber, ochre or plum leave the charts.
