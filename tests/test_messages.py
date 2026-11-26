"""Message draft tests: content and compliance."""
import datetime as dt
import re

import pandas as pd

from ipodesk.calendar import enrich
from ipodesk.config import get_settings
from ipodesk.formatting import indian_group
from ipodesk.messages import drafts_for_date, drafts_for_ipo, send_telegram_test

ROW = pd.DataFrame([{"company": "Demo Ltd", "board": "Mainboard", "price_band_low": 300, "price_band_high": 315,
                     "lot_size": 47, "open_date": dt.date(2026, 11, 30), "close_date": dt.date(2026, 12, 2),
                     "issue_size_cr": 1000, "rhp_link": ""}])


def test_indian_grouping() -> None:
    assert indian_group(14805) == "14,805" and indian_group(10_00_00_000) == "10,00,00,000"
    assert indian_group(1234567.5, 2) == "12,34,567.50"


def test_drafts_have_key_facts_and_disclaimer() -> None:
    row = enrich(ROW, dt.date(2026, 11, 30), []).iloc[0]
    d = drafts_for_ipo(row)
    assert "₹300 to ₹315" in d["Opens"] and "₹14,805" in d["Opens"]
    assert "5:00 pm" in d["Last day"] and "UPI mandate" in d["Last day"]
    assert "Fri, 4 Dec 2026" in d["Allotment"]
    assert "Mon, 7 Dec 2026" in d["Listing"]
    for text in d.values():
        assert "Not a recommendation" in text


def test_drafts_contain_no_advice_words() -> None:
    row = enrich(ROW, dt.date(2026, 11, 30), []).iloc[0]
    banned = get_settings()["compliance"]["banned_phrases"]
    for text in drafts_for_ipo(row).values():
        body = text.split("For information only")[0]
        assert not any(re.search(rf"\b{re.escape(b)}\b", body, re.I) for b in banned)


def test_drafts_for_date_picks_todays_events() -> None:
    enriched = enrich(ROW, dt.date(2026, 12, 2), [])
    assert [d["event"] for d in drafts_for_date(enriched, dt.date(2026, 12, 2))] == ["Last day"]


def test_sending_blocked_outside_demo_mode() -> None:
    assert send_telegram_test("hi", demo_mode=False).startswith("Blocked")
