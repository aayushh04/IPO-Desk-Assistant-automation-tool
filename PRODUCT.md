# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Primary audience for the design: an **interview panel** for a Finance Intern role on the Mutual Funds & IPO desk of an
Indian stock broker, watching a roughly five-minute walkthrough by the builder (a final-year B.Tech AI student).
They must grasp, at a glance, that the tool automates real desk work and does it responsibly: the AI + grounding +
compliance story has to be obvious without explanation, even at some cost to daily-use density.

The role the product plays in that demo: a working tool for **IPO desk staff** who read 300–700 page RHPs to write
client notes, track IPO dates, watch subscription numbers and remind clients to approve UPI mandates. A desk reviewer
edits and signs off every AI draft before anything is exported.

## Product Purpose
Turn an RHP into a factual, reviewed IPO note with every number traced to its page; keep the IPO calendar on a
working-day T+1/T+2/T+3 timeline with ready-to-copy client messages; and track category-wise subscription with a
neutral update line. Success in the demo: the panel sees the mechanism (sections found → numbers grounded → maths in
Python → human sign-off) and trusts it.

## Positioning
Not an "AI stock picker". The distinctive mechanism is the **grounding check**: every figure the LLM returns must be
found on the cited PDF page or it is flagged *verify manually* and export is blocked until a person confirms it.
Valuation and red flags are computed in Python, never by the model. Compliance is built into the workflow rather than
added as a footer.

## Operating Context
- Input documents: Red Herring Prospectuses downloaded from SEBI's public filings page (e.g. a 729-page RHP).
- Manual inputs: price band, lot size, open/close dates (usually announced after the RHP), CSV uploads of IPO lists
  and day-wise subscription from exchange websites.
- Indian market conventions: ₹ crore / lakh, Indian digit grouping (10,00,00,000), mainboard vs SME, QIB / NII
  (sNII, bNII) / Retail / Employee categories, UPI mandate cut-off at 5 pm on the close day, SEBI T+3 listing.
- Use: desktop at a desk for note review; phone for calendar and subscription checks during the day.

## Capabilities and Constraints
- Stack is fixed: Python 3.11, Streamlit multi-page app (Home + 3 pages), logic in the `ipodesk/` package with no
  Streamlit imports. Visual design is limited to what Streamlit theming, custom CSS and HTML blocks allow.
- Deploy target: Streamlit Community Cloud (free tier).
- LLM: Anthropic or OpenAI via one wrapper; an offline demo mode answers for the fictional sample RHP and plants one
  wrong figure to show the grounding check.
- Module 4 (UPI mandate monitor, allotment report, desk analytics on synthetic data) is not built; only if requested.

## Brand Commitments
- Independent identity: "IPO Desk Assistant" is its own tool. No real broker's name, logo or colours, and nothing that
  implies an affiliation.
- Voice: factual, neutral, plain English. Never "subscribe / avoid / buy", no return promises, no grey market premium.
- Every note, message and chart carries: "For information only. Not a recommendation. Read the RHP before investing."

## Evidence on Hand
- Real public RHP used for testing (outside the repo): Crystal Crop Protection Ltd, 729 pages; all 11 sections found
  in about 2 seconds; 67 of 729 pages sent to the LLM.
- Fictional sample RHP (`ipodesk/sample_data.py`), 8 sample IPOs, 3 subscription series, 500 synthetic client bids.
- 69 automated tests. Screenshots in `docs/screenshots/`.
- Absent and must not be fabricated: real clients, users, testimonials, adoption figures, broker partnerships,
  live LLM accuracy figures (no real-key run has been recorded yet).

## Product Principles
1. Show the evidence: every figure points to its page, and unverified figures are visibly different.
2. The person decides: AI drafts, a named reviewer signs off; nothing goes to clients automatically.
3. Facts, never advice: compliance is a property of the workflow, not a disclaimer bolted on.
4. Legible in five minutes: the mechanism must be understandable to a non-technical finance panel at a glance.
5. Indian market native: units, grouping, categories and timelines as the desk actually uses them.
