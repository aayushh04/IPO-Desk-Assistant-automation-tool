"""Working-day timeline, status and table validation tests."""
import datetime as dt

import pandas as pd

from ipodesk import calendar as cal

D = dt.date
NO_HOLIDAYS: list[dt.date] = []


def test_timeline_closes_wednesday() -> None:
    tl = cal.timeline(D(2026, 12, 2), NO_HOLIDAYS)  # Wed
    assert (tl.allotment, tl.credit_refund, tl.listing) == (D(2026, 12, 3), D(2026, 12, 4), D(2026, 12, 7))


def test_timeline_with_holiday_on_3_dec() -> None:
    tl = cal.timeline(D(2026, 12, 2), [D(2026, 12, 3)])
    assert (tl.allotment, tl.credit_refund, tl.listing) == (D(2026, 12, 4), D(2026, 12, 7), D(2026, 12, 8))


def test_timeline_uses_config_holidays_by_default() -> None:
    # 2 Dec 2026 has no configured holiday nearby, so the default list gives the same answer.
    assert cal.timeline(D(2026, 12, 2)).listing == D(2026, 12, 7)


def test_status_through_the_lifecycle() -> None:
    o, c = D(2026, 11, 30), D(2026, 12, 2)
    expected = {D(2026, 11, 27): "Upcoming", D(2026, 11, 30): "Open", D(2026, 12, 2): "Open",
                D(2026, 12, 3): "Allotment", D(2026, 12, 4): "Allotment", D(2026, 12, 7): "Listed"}
    for today, status in expected.items():
        assert cal.ipo_status(o, c, today, NO_HOLIDAYS) == status, today


def test_closed_status_over_a_weekend() -> None:
    # Closes Friday; on Saturday the allotment (Monday) hasn't happened yet.
    assert cal.ipo_status(D(2026, 12, 2), D(2026, 12, 4), D(2026, 12, 5), NO_HOLIDAYS) == "Closed"


def test_validate_ipo_table_reports_bad_rows() -> None:
    df = pd.DataFrame([
        {"company": "A", "board": "mainboard", "price_band_low": 100, "price_band_high": 105, "lot_size": 140,
         "open_date": "2026-12-01", "close_date": "2026-12-03", "issue_size_cr": 500},
        {"company": "B", "board": "SME", "price_band_low": 110, "price_band_high": 105, "lot_size": 1000,
         "open_date": "2026-12-01", "close_date": "2026-12-03", "issue_size_cr": 40},
    ])
    good, errors = cal.validate_ipo_table(df)
    assert list(good["company"]) == ["A"] and good.loc[0, "board"] == "Mainboard"
    assert len(errors) == 1 and errors[0].startswith("Row 3")


def test_missing_columns_reported() -> None:
    _, errors = cal.validate_ipo_table(pd.DataFrame({"company": ["A"]}))
    assert "Missing columns" in errors[0]


def test_events_and_this_week() -> None:
    df = pd.DataFrame([{"company": "A", "board": "Mainboard", "price_band_low": 1, "price_band_high": 2,
                        "lot_size": 10, "open_date": D(2026, 11, 30), "close_date": D(2026, 12, 2),
                        "issue_size_cr": 1}])
    ev = cal.events(cal.enrich(df, D(2026, 12, 1), NO_HOLIDAYS))
    assert list(ev["event"]) == ["Opens", "Last day", "Allotment", "Refund & demat credit", "Listing"]
    week = cal.this_week(ev, D(2026, 12, 1))  # Mon 30 Nov - Sun 6 Dec
    assert len(week) == 4 and "Listing" not in set(week["event"])


def test_month_weeks_shape() -> None:
    weeks = cal.month_weeks(2026, 12)
    assert all(len(w) == 7 for w in weeks) and weeks[0][1] == D(2026, 12, 1)
