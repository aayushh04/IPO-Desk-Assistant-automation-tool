"""Subscription tracker tests."""
import datetime as dt

import pandas as pd
import pytest

from ipodesk import subscription as sub
from ipodesk.sample_data import sample_subscription


def test_three_crore_bid_on_one_crore_offered_is_3x() -> None:
    assert sub.subscription_multiple(3e7, 1e7) == pytest.approx(3.0)


def test_total_is_weighted_not_average() -> None:
    df = pd.DataFrame([
        {"company": "A", "day": 1, "category": "QIB", "shares_offered": 100, "shares_bid": 1000},  # 10x
        {"company": "A", "day": 1, "category": "Retail", "shares_offered": 300, "shares_bid": 300},  # 1x
    ])
    clean, errors = sub.load_subscription(df)
    total = clean[clean["category"] == "total"]["subscription_x"].item()
    assert errors == [] and total == pytest.approx(3.25)  # 1300 / 400, not (10 + 1) / 2


def test_update_text_format() -> None:
    df = pd.DataFrame([
        {"company": "A", "day": 2, "category": c, "subscription_x": x}
        for c, x in [("qib", 3.4), ("nii", 5.1), ("retail", 2.2), ("total", 3.1)]
    ])
    clean, _ = sub.load_subscription(df)
    assert sub.update_text(clean, "A") == "Day 2 close: QIB 3.4x, NII 5.1x, Retail 2.2x, Total 3.1x"


def test_nii_combined_from_big_and_small() -> None:
    df = pd.DataFrame([
        {"company": "A", "day": 1, "category": "bNII", "shares_offered": 200, "shares_bid": 1000},
        {"company": "A", "day": 1, "category": "sNII", "shares_offered": 100, "shares_bid": 200},
    ])
    clean, _ = sub.load_subscription(df)
    assert "NII 4.0x" in sub.update_text(clean, "A")  # 1200 / 300


def test_unknown_category_and_missing_columns() -> None:
    _, errors = sub.load_subscription(pd.DataFrame({"company": ["A"], "day": [1], "category": ["Martians"],
                                                    "subscription_x": [1.0]}))
    assert "Unknown categories" in errors[0]
    _, errors = sub.load_subscription(pd.DataFrame({"company": ["A"]}))
    assert "Missing columns" in errors[0]


def test_sample_data_round_trip_chart_and_png() -> None:
    raw = sample_subscription(dt.date(2026, 11, 26)).drop(columns=["subscription_x", "date"])
    clean, errors = sub.load_subscription(raw[raw["category"] != "total"])
    assert errors == []
    company = "Corvi Specialty Chemicals Ltd (Sample)"
    assert sub.latest_day(clean, company) == 3
    assert sub.update_text(clean, company).startswith("Day 3 close: QIB 48.6x")
    table = sub.latest_table(clean, company)
    assert "Change vs previous day" in table.columns
    assert len(sub.chart(clean, company).data) == 6  # 5 categories + total
    assert sub.chart_png(clean, company)[:8] == b"\x89PNG\r\n\x1a\n"


def test_rounding_is_half_up() -> None:
    assert sub.fmt_x(0.95) == "1.0x" and sub.fmt_x(1.47) == "1.5x" and sub.fmt_x(3.44) == "3.4x"
