"""IPO calendar logic: working days, the T+1/T+2/T+3 timeline, status and events.

Plain-words version of the SEBI T+3 timeline (T = the day the issue closes):
- T+1 working day: basis of allotment is finalised (allotment status comes out)
- T+2 working day: shares are credited to demat accounts and blocked money is released
                   for those who didn't get shares (refunds / unblocking)
- T+3 working day: the shares list and start trading on the exchange

"Working day" = not a Saturday/Sunday and not an exchange holiday (config/holidays.yaml).
"""
from __future__ import annotations

import calendar as _stdlib_calendar
import datetime as dt
from dataclasses import dataclass
from typing import Iterable, Literal

import pandas as pd
from pydantic import BaseModel, ValidationError, field_validator, model_validator

from ipodesk.config import load_holidays

STATUSES: list[str] = ["Upcoming", "Open", "Closed", "Allotment", "Listed"]
EVENT_ORDER: list[str] = ["Opens", "Last day", "Allotment", "Refund & demat credit", "Listing"]
REQUIRED_COLUMNS: list[str] = ["company", "board", "price_band_low", "price_band_high", "lot_size",
                               "open_date", "close_date", "issue_size_cr"]


def _holiday_set(holidays: Iterable[dt.date] | None) -> set[dt.date]:
    """Use the given holidays, or load config/holidays.yaml if none are given."""
    return set(load_holidays() if holidays is None else holidays)


def is_working_day(day: dt.date, holidays: Iterable[dt.date] | None = None) -> bool:
    """True on Monday-Friday, unless it's an exchange holiday."""
    return day.weekday() < 5 and day not in _holiday_set(holidays)


def add_working_days(day: dt.date, n: int, holidays: Iterable[dt.date] | None = None) -> dt.date:
    """Move forward n working days, skipping weekends and holidays."""
    hol = _holiday_set(holidays)
    while n > 0:
        day += dt.timedelta(days=1)
        if day.weekday() < 5 and day not in hol:
            n -= 1
    return day


@dataclass(frozen=True)
class Timeline:
    """Key post-issue dates, all computed from the close date."""

    close: dt.date
    allotment: dt.date       # T+1
    credit_refund: dt.date   # T+2
    listing: dt.date         # T+3


def timeline(close_date: dt.date, holidays: Iterable[dt.date] | None = None) -> Timeline:
    """Build the T+1 / T+2 / T+3 timeline from the issue close date."""
    hol = _holiday_set(holidays)
    return Timeline(
        close=close_date,
        allotment=add_working_days(close_date, 1, hol),
        credit_refund=add_working_days(close_date, 2, hol),
        listing=add_working_days(close_date, 3, hol),
    )


def ipo_status(open_date: dt.date, close_date: dt.date, today: dt.date,
               holidays: Iterable[dt.date] | None = None) -> str:
    """Upcoming / Open / Closed / Allotment / Listed, based on today's date."""
    if today < open_date:
        return "Upcoming"
    if today <= close_date:
        return "Open"
    tl = timeline(close_date, holidays)
    if today < tl.allotment:
        return "Closed"
    if today < tl.listing:
        return "Allotment"
    return "Listed"


class IPORecord(BaseModel):
    """One row of the IPO table, validated (catches typos in uploaded CSVs)."""

    company: str
    board: Literal["Mainboard", "SME"]
    price_band_low: float
    price_band_high: float
    lot_size: int
    open_date: dt.date
    close_date: dt.date
    issue_size_cr: float
    rhp_link: str = ""

    @field_validator("board", mode="before")
    @classmethod
    def _board(cls, v: object) -> object:
        """Accept 'mainboard', 'sme', 'Main board' etc."""
        text = str(v).strip().lower().replace(" ", "")
        return {"mainboard": "Mainboard", "main": "Mainboard", "sme": "SME"}.get(text, v)

    @field_validator("rhp_link", mode="before")
    @classmethod
    def _link(cls, v: object) -> str:
        """Blank cells come in as NaN from CSVs; treat them as ''."""
        return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)

    @model_validator(mode="after")
    def _check(self) -> "IPORecord":
        """Close must be on/after open, and the band low must not exceed the high."""
        if self.close_date < self.open_date:
            raise ValueError("close_date is before open_date")
        if self.price_band_low > self.price_band_high:
            raise ValueError("price_band_low is above price_band_high")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        return self


def validate_ipo_table(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Check an uploaded IPO table. Returns (valid rows, list of error messages)."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return pd.DataFrame(columns=REQUIRED_COLUMNS + ["rhp_link"]), [f"Missing columns: {', '.join(missing)}"]
    good, errors = [], []
    for i, row in df.iterrows():
        try:
            good.append(IPORecord(**{k: row[k] for k in df.columns if k in IPORecord.model_fields}).model_dump())
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(x) for x in first["loc"]) or "row"
            errors.append(f"Row {int(i) + 2}: {where}: {first['msg']}")  # +2 = header + 1-based
    return pd.DataFrame(good, columns=list(IPORecord.model_fields)), errors


def enrich(df: pd.DataFrame, today: dt.date, holidays: Iterable[dt.date] | None = None) -> pd.DataFrame:
    """Add status, min investment and the T+1/T+2/T+3 dates to a validated IPO table."""
    hol = _holiday_set(holidays)
    out = df.copy()
    tls = [timeline(c, hol) for c in out["close_date"]]
    out["allotment_date"] = [t.allotment for t in tls]
    out["credit_date"] = [t.credit_refund for t in tls]
    out["listing_date"] = [t.listing for t in tls]
    out["status"] = [ipo_status(o, c, today, hol) for o, c in zip(out["open_date"], out["close_date"])]
    out["min_investment"] = out["price_band_high"] * out["lot_size"]
    return out


def events(enriched: pd.DataFrame) -> pd.DataFrame:
    """One row per (date, company, event) for the calendar and the 'this week' list."""
    mapping = {"Opens": "open_date", "Last day": "close_date", "Allotment": "allotment_date",
               "Refund & demat credit": "credit_date", "Listing": "listing_date"}
    rows = [
        {"date": r[col], "company": r["company"], "board": r["board"], "event": ev}
        for _, r in enriched.iterrows() for ev, col in mapping.items()
    ]
    df = pd.DataFrame(rows, columns=["date", "company", "board", "event"])
    df["order"] = df["event"].map(EVENT_ORDER.index)
    return df.sort_values(["date", "order", "company"]).drop(columns="order").reset_index(drop=True)


def week_bounds(today: dt.date) -> tuple[dt.date, dt.date]:
    """Monday and Sunday of the week containing `today`."""
    monday = today - dt.timedelta(days=today.weekday())
    return monday, monday + dt.timedelta(days=6)


def this_week(events_df: pd.DataFrame, today: dt.date) -> pd.DataFrame:
    """Events falling in the current Monday-Sunday week."""
    start, end = week_bounds(today)
    mask = (events_df["date"] >= start) & (events_df["date"] <= end)
    return events_df[mask].reset_index(drop=True)


def month_weeks(year: int, month: int) -> list[list[dt.date | None]]:
    """The month as a list of weeks (Mon..Sun); days outside the month are None."""
    cal = _stdlib_calendar.Calendar(firstweekday=0)
    return [[d if d.month == month else None for d in week] for week in cal.monthdatescalendar(year, month)]
