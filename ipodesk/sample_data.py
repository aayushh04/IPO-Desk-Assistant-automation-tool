"""Synthetic (fake) data for demos and tests. NOTHING here is real.

- 8 sample IPOs whose dates move with "today" (spread over the previous and next 30 days)
- Day-wise, category-wise subscription data for 3 of them
- 500 client bids with masked PAN-like IDs, UPI mandate status and allotment results
- A registrar-style allotment file (for the Module 4 matching exercise)
- A small PDF that mimics an RHP's section headings, with known numbers for tests

Everything is generated from a fixed random seed, so the same inputs always give the
same output (tests depend on that). Run `python -m ipodesk.sample_data` to write it all
to data/sample/.
"""
from __future__ import annotations

import datetime as dt
import random
import string
from pathlib import Path
from typing import Any

import pandas as pd

from ipodesk.config import PROJECT_ROOT, load_holidays

SEED: int = 42
SAMPLE_DIR: Path = PROJECT_ROOT / "data" / "sample"
SAMPLE_TAG: str = "SAMPLE - FICTIONAL DATA FOR SOFTWARE TESTING. NOT A REAL OFFER OR CLIENT."

# --------------------------------------------------------------------------------------
# Working-day helpers (a fuller version lives in ipodesk/calendar.py from Stage 4)
# --------------------------------------------------------------------------------------


def _is_working_day(day: dt.date, holidays: set[dt.date]) -> bool:
    """True if `day` is a weekday and not an exchange holiday."""
    return day.weekday() < 5 and day not in holidays


def _next_working_day(day: dt.date, holidays: set[dt.date]) -> dt.date:
    """Return `day` itself if it is a working day, else the next working day."""
    while not _is_working_day(day, holidays):
        day += dt.timedelta(days=1)
    return day


def _add_working_days(day: dt.date, n: int, holidays: set[dt.date]) -> dt.date:
    """Move forward `n` working days from `day`."""
    while n > 0:
        day += dt.timedelta(days=1)
        if _is_working_day(day, holidays):
            n -= 1
    return day


# --------------------------------------------------------------------------------------
# 1. Sample IPO calendar
# --------------------------------------------------------------------------------------

# (company, board, price low, price high, lot size, issue size Rs crore, open offset in days)
_IPO_SPECS: list[tuple[str, str, int, int, int, float, int]] = [
    ("Aranya Agritech Ltd (Sample)", "Mainboard", 240, 252, 59, 1150.0, -29),
    ("Bluepeak Logistics Ltd (Sample)", "Mainboard", 410, 432, 34, 2400.0, -20),
    ("Corvi Specialty Chemicals Ltd (Sample)", "Mainboard", 300, 315, 47, 1000.0, -11),
    ("Hastin Textiles Ltd (Sample)", "SME", 82, 86, 1600, 42.5, -5),
    ("Elara Diagnostics Ltd (Sample)", "Mainboard", 520, 548, 27, 1850.0, -1),
    ("Greenline Solar Glass Ltd (Sample)", "SME", 120, 126, 1000, 68.0, 5),
    ("Farsight Fintech Solutions Ltd (Sample)", "Mainboard", 690, 725, 20, 3200.0, 16),
    ("Dhruva Precision Engineering Ltd (Sample)", "Mainboard", 155, 163, 92, 640.0, 27),
]

ISSUE_OPEN_WORKING_DAYS: int = 3  # an issue stays open for at least 3 working days


def sample_ipos(today: dt.date | None = None) -> pd.DataFrame:
    """Return 8 fictional IPOs with open/close dates placed around `today`."""
    today = today or dt.date.today()
    holidays = set(load_holidays())
    rows = []
    for name, board, low, high, lot, size, offset in _IPO_SPECS:
        open_date = _next_working_day(today + dt.timedelta(days=offset), holidays)
        close_date = _add_working_days(open_date, ISSUE_OPEN_WORKING_DAYS - 1, holidays)
        rows.append(
            {
                "company": name,
                "board": board,
                "price_band_low": low,
                "price_band_high": high,
                "lot_size": lot,
                "min_investment": high * lot,  # one lot at the upper band
                "open_date": open_date,
                "close_date": close_date,
                "issue_size_cr": size,
                "rhp_link": "",  # paste the SEBI RHP link here for real IPOs
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------
# 2. Day-wise subscription for 3 mainboard IPOs
# --------------------------------------------------------------------------------------

CATEGORIES: list[str] = ["qib", "nii_big", "nii_small", "retail", "employee"]

# Fraction of the TOTAL issue (in shares) open for public bidding in each category, for a
# mainboard issue where QIB = 50%, NII = 15% (1/3 small NII, 2/3 big NII), Retail = 35%.
# Up to 60% of the QIB portion goes to anchor investors the day before opening, and the
# exchanges' subscription figures exclude anchors, so only 40% of 50% = 20% is left for QIBs.
# Employees get a small separate reservation.
_QIB_NET = 0.50 * 0.40
_CATEGORY_WEIGHTS: dict[str, float] = {
    "qib": _QIB_NET,
    "nii_big": 0.15 * 2 / 3,
    "nii_small": 0.15 * 1 / 3,
    "retail": 0.35,
    "employee": 0.005,
}

# Final (last-day) subscription multiples we want each sample IPO to end with.
_FINAL_MULTIPLES: dict[str, dict[str, float]] = {
    "Bluepeak Logistics Ltd (Sample)": {"qib": 2.4, "nii_big": 1.3, "nii_small": 1.8, "retail": 0.95, "employee": 1.2},
    "Corvi Specialty Chemicals Ltd (Sample)": {"qib": 48.6, "nii_big": 31.2, "nii_small": 19.4, "retail": 7.8, "employee": 4.1},
    "Elara Diagnostics Ltd (Sample)": {"qib": 12.5, "nii_big": 9.8, "nii_small": 6.6, "retail": 3.9, "employee": 2.2},
}

# What fraction of the final demand has arrived by the end of each day.
# QIBs typically bid on the last day, retail spreads out more evenly.
_DAY_PROGRESS: dict[str, list[float]] = {
    "qib": [0.02, 0.15, 1.0],
    "nii_big": [0.04, 0.30, 1.0],
    "nii_small": [0.10, 0.40, 1.0],
    "retail": [0.25, 0.55, 1.0],
    "employee": [0.30, 0.60, 1.0],
}


def sample_subscription(today: dt.date | None = None) -> pd.DataFrame:
    """Return day-wise cumulative subscription for 3 sample IPOs (only days up to `today`).

    Columns: company, day, date, category, shares_offered, shares_bid, subscription_x.
    subscription_x = shares bid / shares offered (e.g. 3 crore bid / 1 crore offered = 3.0x).
    A 'total' row per day is the weighted figure: all bids / all shares offered.
    """
    today = today or dt.date.today()
    rng = random.Random(SEED)
    holidays = set(load_holidays())
    ipos = sample_ipos(today).set_index("company")
    rows: list[dict[str, Any]] = []
    for company, finals in _FINAL_MULTIPLES.items():
        ipo = ipos.loc[company]
        total_shares = ipo["issue_size_cr"] * 1e7 / ipo["price_band_high"]  # 1 crore = 1e7
        day_date = ipo["open_date"]
        for day_no in range(1, ISSUE_OPEN_WORKING_DAYS + 1):
            if day_date > today:
                break
            total_offered = total_bid = 0
            for cat in CATEGORIES:
                offered = int(total_shares * _CATEGORY_WEIGHTS[cat])
                noise = 1 + rng.uniform(-0.08, 0.08) if day_no < 3 else 1.0
                bid = int(offered * finals[cat] * _DAY_PROGRESS[cat][day_no - 1] * noise)
                total_offered += offered
                total_bid += bid
                rows.append(_sub_row(company, day_no, day_date, cat, offered, bid))
            rows.append(_sub_row(company, day_no, day_date, "total", total_offered, total_bid))
            day_date = _add_working_days(day_date, 1, holidays)
    return pd.DataFrame(rows)


def _sub_row(company: str, day: int, date: dt.date, cat: str, offered: int, bid: int) -> dict[str, Any]:
    """Build one subscription row."""
    return {
        "company": company,
        "day": day,
        "date": date,
        "category": cat,
        "shares_offered": offered,
        "shares_bid": bid,
        "subscription_x": round(bid / offered, 2) if offered else 0.0,
    }


# --------------------------------------------------------------------------------------
# 3. Synthetic clients and bids
# --------------------------------------------------------------------------------------

_FIRST = ["Aarav", "Diya", "Kabir", "Meera", "Rohan", "Ananya", "Ishaan", "Sana", "Vikram", "Priya",
          "Arjun", "Neha", "Kunal", "Tara", "Siddharth", "Pooja", "Nikhil", "Riya", "Aditya", "Kavya"]
_LAST = ["Sharma", "Iyer", "Patel", "Reddy", "Khan", "Nair", "Gupta", "Das", "Joshi", "Menon",
         "Kulkarni", "Singh", "Bose", "Shah", "Pillai"]
_CITIES = ["Mumbai", "Pune", "Ahmedabad", "Bengaluru", "Chennai", "Delhi", "Kolkata", "Hyderabad", "Jaipur", "Indore"]

MANDATE_STATUSES: list[str] = ["approved", "pending", "declined", "expired", "failed"]
REJECTION_REASONS: list[str] = [
    "UPI mandate not approved before cut-off",
    "PAN not linked with demat account",
    "Multiple applications under the same PAN",
    "Funds could not be blocked in bank account",
]
RETAIL_MAX_AMOUNT: int = 200_000      # retail individual investor: up to Rs 2 lakh
SMALL_NII_MAX_AMOUNT: int = 1_000_000  # small NII: above Rs 2 lakh up to Rs 10 lakh


def _fake_masked_pan(rng: random.Random) -> str:
    """Make a random PAN-shaped ID and return only its masked form, e.g. 'AB******4K'.

    Format of a PAN: 5 letters, 4 digits, 1 letter; the 4th letter is 'P' for individuals.
    The unmasked value is never stored.
    """
    letters = string.ascii_uppercase
    pan = "".join(rng.choices(letters, k=3)) + "P" + rng.choice(letters)
    pan += "".join(rng.choices(string.digits, k=4)) + rng.choice(letters)
    return pan[:2] + "******" + pan[-2:]


def sample_clients(n: int = 200) -> pd.DataFrame:
    """Return `n` fake clients (IDs, names, masked PAN, masked UPI ID, city)."""
    rng = random.Random(SEED)
    rows = []
    for i in range(1, n + 1):
        first, last = rng.choice(_FIRST), rng.choice(_LAST)
        rows.append(
            {
                "client_id": f"CL{i:05d}",
                "client_name": f"{first} {last}",
                "pan_masked": _fake_masked_pan(rng),
                "upi_id_masked": f"{first[:2].lower()}***@okdemo",
                "city": rng.choice(_CITIES),
            }
        )
    return pd.DataFrame(rows)


def sample_bids(n: int = 500, today: dt.date | None = None) -> pd.DataFrame:
    """Return `n` fake client bids on the sample IPOs that have already opened.

    Mandate status depends on where the IPO is in its life:
    - still open: some mandates are 'pending' (client hasn't approved in the UPI app yet)
    - closed: a pending mandate has 'expired' and that bid is rejected
    Allotment is decided only once the allotment date (close + 1 working day) has passed.
    """
    today = today or dt.date.today()
    rng = random.Random(SEED + 1)
    holidays = set(load_holidays())
    clients = sample_clients()
    ipos = sample_ipos(today)
    ipos = ipos[ipos["open_date"] <= today].reset_index(drop=True)
    retail_x = _final_retail_multiple()
    rows = []
    for i in range(1, n + 1):
        client = clients.iloc[rng.randrange(len(clients))]
        ipo = ipos.iloc[rng.randrange(len(ipos))]
        price, lot = int(ipo["price_band_high"]), int(ipo["lot_size"])
        lot_value = price * lot

        if ipo["board"] == "SME":
            category, lots = "individual", rng.choice([1, 1, 2])
        else:
            category = rng.choices(["retail", "nii_small", "nii_big"], weights=[85, 11, 4])[0]
            max_retail_lots = RETAIL_MAX_AMOUNT // lot_value
            if category == "retail":
                lots = rng.choice([1, 1, 1, 2, max_retail_lots])
            elif category == "nii_small":
                lots = rng.randint(max_retail_lots + 1, SMALL_NII_MAX_AMOUNT // lot_value)
            else:
                lots = SMALL_NII_MAX_AMOUNT // lot_value + rng.randint(1, 40)

        is_open = ipo["close_date"] >= today
        allotment_date = _add_working_days(ipo["close_date"], 1, holidays)
        mandate = rng.choices(MANDATE_STATUSES, weights=[82, 8, 4, 3, 3])[0]
        if not is_open and mandate == "pending":
            mandate = "expired"

        # Bids can only be placed on working days between open and close (and not in the future).
        window = [d for d in _date_range(ipo["open_date"], min(ipo["close_date"], today))
                  if _is_working_day(d, holidays)]
        bid_date = rng.choice(window)

        shares_applied = lots * lot
        allotment, reason, shares_allotted = "pending", "", 0
        if today >= allotment_date:
            if mandate != "approved":
                allotment, reason = "rejected", REJECTION_REASONS[0]
            elif rng.random() < 0.02:
                allotment, reason = "rejected", rng.choice(REJECTION_REASONS[1:])
            else:
                # Oversubscribed retail = lottery for one lot; chance ~ 1 / subscription.
                chance = min(1.0, 1 / retail_x.get(ipo["company"], 2.5))
                if rng.random() < chance:
                    allotment, shares_allotted = "allotted", lot
                else:
                    allotment = "not_allotted"

        rows.append(
            {
                "application_no": f"APP{i:06d}",
                "client_id": client["client_id"],
                "client_name": client["client_name"],
                "pan_masked": client["pan_masked"],
                "upi_id_masked": client["upi_id_masked"],
                "company": ipo["company"],
                "board": ipo["board"],
                "category": category,
                "lots": lots,
                "shares_applied": shares_applied,
                "bid_price": price,
                "cut_off": category in ("retail", "individual"),
                "amount": shares_applied * price,
                "bid_date": bid_date,
                "mandate_status": mandate,
                "allotment_status": allotment,
                "shares_allotted": shares_allotted,
                "rejection_reason": reason,
            }
        )
    return pd.DataFrame(rows)


def _date_range(start: dt.date, end: dt.date) -> list[dt.date]:
    """All calendar dates from `start` to `end`, inclusive."""
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]


def _final_retail_multiple() -> dict[str, float]:
    """Retail subscription per sample IPO (used for the allotment lottery odds)."""
    return {name: m["retail"] for name, m in _FINAL_MULTIPLES.items()}


def sample_registrar_allotment(bids: pd.DataFrame) -> pd.DataFrame:
    """Turn our bids into a registrar-style file (what a registrar like KFin/Link publishes).

    It only knows application number, masked PAN, shares allotted and a status code, so
    Module 4 has to match it back to the client list.
    """
    decided = bids[bids["allotment_status"] != "pending"]
    code = {"allotted": "A", "not_allotted": "N", "rejected": "R"}
    return pd.DataFrame(
        {
            "application_no": decided["application_no"],
            "pan_masked": decided["pan_masked"],
            "company": decided["company"],
            "shares_applied": decided["shares_applied"],
            "shares_allotted": decided["shares_allotted"],
            "status_code": decided["allotment_status"].map(code),
            "remarks": decided["rejection_reason"],
        }
    ).reset_index(drop=True)


# --------------------------------------------------------------------------------------
# 4. A small fake RHP PDF with known headings and numbers
# --------------------------------------------------------------------------------------

# Known answers for tests (Rs crore unless stated). Kept consistent with the Stage 2 tests:
# upper band 315, post-issue shares 10 crore, latest PAT 105 crore -> EPS 10.50, P/E 30.0x.
SAMPLE_RHP_FACTS: dict[str, Any] = {
    "company": "Aarna Sutra Foods Limited (Sample)",
    "years": ["FY2024", "FY2025", "FY2026"],
    "revenue": [820.40, 1010.25, 1240.60],
    "ebitda": [118.30, 152.80, 189.90],
    "pat": [61.75, 83.40, 105.00],
    "operating_cash_flow": [44.20, -12.60, 71.35],
    "total_borrowings": [310.00, 292.50, 248.00],
    "net_worth": [518.60, 602.00, 707.00],
    "issue_size_cr": 1000.00,
    "fresh_issue_cr": 200.00,
    "ofs_cr": 800.00,
    "post_issue_shares": 100_000_000,
    "pre_issue_shares": 93_650_794,
    "objects": {"Repayment of borrowings": 90.00, "Capex for new Nashik plant": 60.00,
                "General corporate purposes": 45.00, "Issue expenses (fresh issue share)": 5.00},
    "peers_pe": {"Northwind Snacks Ltd (Sample)": 28.4, "Kaveri Consumer Foods Ltd (Sample)": 22.1,
                 "Sahyadri Packaged Foods Ltd (Sample)": 19.6},
    "promoter_holding_pre_pct": 72.40,
    "promoter_shares_pledged": 0,
    "litigation_total_cr": 18.05,
    "rpt_fy2026_cr": 26.10,
}

# Section key -> heading text exactly as printed in the sample PDF (variations on purpose).
SAMPLE_RHP_HEADINGS: dict[str, str] = {
    "risk_factors": "SECTION II - RISK FACTORS",
    "financial_summary": "SUMMARY OF FINANCIAL INFORMATION",
    "capital_structure": "CAPITAL STRUCTURE",
    "objects": "OBJECTS OF THE OFFER",
    "basis_for_price": "BASIS FOR OFFER PRICE",
    "industry": "INDUSTRY OVERVIEW",
    "business": "OUR BUSINESS",
    "promoters": "OUR PROMOTERS AND PROMOTER GROUP",
    "restated_financials": "RESTATED FINANCIAL INFORMATION",
    "related_party": "RELATED PARTY TRANSACTIONS",
    "litigation": "OUTSTANDING LITIGATION AND MATERIAL DEVELOPMENTS",
}


def _rhp_pages() -> list[tuple[str | None, str]]:
    """Return the sample RHP as a list of (heading or None, body text), one per page."""
    f = SAMPLE_RHP_FACTS
    toc_lines = "\n".join(
        f"{h} {'.' * (60 - len(h))} {p}"
        for p, h in enumerate(SAMPLE_RHP_HEADINGS.values(), start=4)
    )
    return [
        ("RED HERRING PROSPECTUS",
         f"{f['company']}\nCorporate Identity Number: U00000MH2010PLC000000 (fictional)\n\n"
         "INITIAL PUBLIC OFFER OF EQUITY SHARES OF FACE VALUE OF Rs 2 EACH\n"
         "Total Offer Size: Rs 1,000.00 crore, comprising a Fresh Issue of Rs 200.00 crore and an\n"
         "Offer for Sale of Rs 800.00 crore by the Selling Shareholders.\n"
         "Price Band: [*] (to be announced at least two working days before the Bid/Offer opening date)\n"
         "BOOK RUNNING LEAD MANAGERS: Sample Capital Advisors (fictional)"),
        ("TABLE OF CONTENTS", toc_lines),
        ("DEFINITIONS AND ABBREVIATIONS",
         "Company / Issuer: Aarna Sutra Foods Limited.\nOFS: Offer for Sale.\nQIB: Qualified Institutional Buyer.\n"
         "NII: Non-Institutional Investor.\nRII: Retail Individual Investor.\n"
         "For details of our operations, see 'Our Business' on page 10."),
        ("SECTION II - RISK FACTORS",
         "An investment in equity shares involves a high degree of risk.\n\n"
         "1. We derive 64% of our revenue from our top three product categories (snacks, ready-to-eat\n"
         "   meals and spices). A fall in demand for these could reduce our revenue.\n"
         "2. We reported negative cash flow from operating activities of Rs (12.60) crore in FY2025.\n"
         "3. Our Nashik and Indore plants account for 78% of production; any disruption could hurt output.\n"
         "4. Prices of edible oil and wheat, our main raw materials, are volatile.\n"
         "5. The Offer includes an Offer for Sale of Rs 800.00 crore; we will not receive any proceeds\n"
         "   from the Offer for Sale.\n"
         "6. There are outstanding legal proceedings involving our Company amounting to Rs 18.05 crore."),
        ("SUMMARY OF FINANCIAL INFORMATION",
         "Restated summary (Rs in crore)\n"
         "Particulars              FY2024     FY2025     FY2026\n"
         "Revenue from operations  820.40   1,010.25   1,240.60\n"
         "EBITDA                   118.30     152.80     189.90\n"
         "Profit after tax          61.75      83.40     105.00\n"
         "Net worth                518.60     602.00     707.00\n"
         "Total borrowings         310.00     292.50     248.00"),
        ("CAPITAL STRUCTURE",
         "Equity Shares outstanding prior to the Offer: 9,36,50,794 Equity Shares of Rs 2 each.\n"
         "Equity Shares outstanding after the Offer (at the upper end of the Price Band): 10,00,00,000\n"
         "Equity Shares.\n"
         "Shareholding of our Promoters prior to the Offer: 72.40%.\n"
         "None of the Equity Shares held by our Promoters are pledged or otherwise encumbered."),
        ("OBJECTS OF THE OFFER",
         "The Offer comprises a Fresh Issue and an Offer for Sale. Our Company will not receive any\n"
         "proceeds from the Offer for Sale.\n\n"
         "Utilisation of Net Proceeds of the Fresh Issue (Rs in crore)\n"
         "Repayment / prepayment of borrowings                 90.00\n"
         "Capital expenditure for new Nashik plant             60.00\n"
         "General corporate purposes                           45.00\n"
         "Offer expenses (Company's share)                      5.00\n"
         "Gross Proceeds of the Fresh Issue                   200.00"),
        ("BASIS FOR OFFER PRICE",
         "Basic and diluted EPS for FY2026: Rs 11.21 (on pre-Offer shares).\n"
         "Return on Net Worth FY2026: 14.85%.\n\n"
         "Comparison with listed industry peers (FY2026)\n"
         "Company                                  P/E (x)\n"
         "Northwind Snacks Ltd (Sample)             28.4\n"
         "Kaveri Consumer Foods Ltd (Sample)        22.1\n"
         "Sahyadri Packaged Foods Ltd (Sample)      19.6"),
        ("INDUSTRY OVERVIEW",
         "The Indian packaged foods market was estimated at Rs 5,20,000 crore in FY2026 and is projected\n"
         "to grow at a CAGR of 11% to FY2031 (source: fictional industry report)."),
        ("OUR BUSINESS",
         "We make and sell packaged snacks, ready-to-eat meals and spice blends under the 'Aarna' brand.\n"
         "We sell through 2,40,000 retail outlets in 18 states and on e-commerce platforms.\n\n"
         "Our strengths:\n- An established brand in western and central India\n"
         "- Two automated plants at Nashik and Indore\n- A wide distribution network of 1,150 distributors\n"
         "- Revenue growth of 22.80% in FY2026"),
        ("OUR PROMOTERS AND PROMOTER GROUP",
         "Our Promoters are Promoter A (Sample) and Promoter B (Sample), who together hold 72.40% of the\n"
         "pre-Offer share capital. Promoter A has over 25 years of experience in the food industry."),
        ("RESTATED FINANCIAL INFORMATION",
         "Restated Statement of Cash Flows (Rs in crore)\n"
         "Particulars                                FY2024     FY2025     FY2026\n"
         "Net cash from operating activities          44.20     (12.60)     71.35\n"
         "Net cash used in investing activities      (65.10)    (80.40)    (58.20)\n"
         "Net cash from financing activities          18.30      95.10     (10.75)"),
        ("RELATED PARTY TRANSACTIONS",
         "Total related party transactions in FY2026 were Rs 26.10 crore, being 2.10% of revenue from\n"
         "operations, mainly purchases of packaging material from a Promoter Group entity."),
        ("OUTSTANDING LITIGATION AND MATERIAL DEVELOPMENTS",
         "Litigation involving our Company (Rs in crore)\n"
         "Direct and indirect tax proceedings          14.20\n"
         "Civil proceedings                             3.85\n"
         "Total                                        18.05\n"
         "There is one criminal proceeding against a Promoter; the amount is not quantifiable."),
        ("DECLARATION",
         "We certify that all relevant provisions of the Companies Act, 2013 and the SEBI ICDR\n"
         "Regulations have been complied with. (Sample text.)"),
    ]


def sample_rhp_expected_pages() -> dict[str, int]:
    """Section key -> 1-based PDF page where its heading appears in the sample PDF."""
    page_of = {heading: i for i, (heading, _) in enumerate(_rhp_pages(), start=1)}
    return {key: page_of[heading] for key, heading in SAMPLE_RHP_HEADINGS.items()}


def make_sample_rhp_pdf(path: Path | str) -> Path:
    """Write the small fake RHP PDF to `path` and return the path.

    Each page has a running header (the SAMPLE warning), a bold heading, body text and a
    page number footer, which is roughly how real RHP pages look to a text extractor.
    """
    import pymupdf as fitz  # PyMuPDF (older code calls it "fitz")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for page_no, (heading, body) in enumerate(_rhp_pages(), start=1):
        page = doc.new_page(width=595, height=842)  # A4 in points
        page.insert_text((40, 30), SAMPLE_TAG, fontsize=7, fontname="helv")
        y = 80
        if heading:
            page.insert_text((40, y), heading, fontsize=14, fontname="hebo")
            y += 30
        page.insert_textbox(fitz.Rect(40, y, 555, 800), body, fontsize=9.5, fontname="cour")
        page.insert_text((290, 820), str(page_no), fontsize=8, fontname="helv")
    doc.save(path)
    doc.close()
    return path


# --------------------------------------------------------------------------------------
# Write everything to disk
# --------------------------------------------------------------------------------------


def write_all(out_dir: Path = SAMPLE_DIR, today: dt.date | None = None) -> dict[str, Path]:
    """Generate every sample dataset into `out_dir` (CSV + PDF) and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    bids = sample_bids(today=today)
    outputs = {
        "ipos": (sample_ipos(today), "sample_ipos.csv"),
        "subscription": (sample_subscription(today), "sample_subscription.csv"),
        "clients": (sample_clients(), "sample_clients.csv"),
        "bids": (bids, "sample_bids.csv"),
        "registrar": (sample_registrar_allotment(bids), "sample_registrar_allotment.csv"),
    }
    paths: dict[str, Path] = {}
    for key, (df, name) in outputs.items():
        paths[key] = out_dir / name
        df.to_csv(paths[key], index=False)
    paths["rhp_pdf"] = make_sample_rhp_pdf(out_dir / "sample_rhp.pdf")
    return paths


if __name__ == "__main__":
    for key, p in write_all().items():
        print(f"{key:13s} -> {p.relative_to(PROJECT_ROOT)}")
