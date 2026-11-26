"""Number formatting in the Indian style (lakh / crore grouping).

Indian grouping puts the first comma after 3 digits, then every 2 digits:
12,34,567 (twelve lakh ...) instead of 1,234,567.
"""
from __future__ import annotations

import datetime as dt


def indian_group(value: float, decimals: int = 0) -> str:
    """Format a number with Indian digit grouping, e.g. 1234567.5 -> '12,34,567.50'."""
    sign = "-" if value < 0 else ""
    text = f"{abs(value):.{decimals}f}"
    whole, _, frac = text.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return sign + whole + (f".{frac}" if frac else "")


def inr(value: float | None, decimals: int = 0, symbol: str = "Rs ") -> str:
    """Money in rupees, e.g. inr(14805) -> 'Rs 14,805'. '-' if missing."""
    if value is None:
        return "-"
    return f"{symbol}{indian_group(value, decimals)}"


def crore(value: float | None, symbol: str = "Rs ") -> str:
    """Money in crore, e.g. crore(1240.6) -> 'Rs 1,240.60 cr'."""
    if value is None:
        return "-"
    return f"{symbol}{indian_group(value, 2)} cr"


def pct(value: float | None, decimals: int = 1) -> str:
    """Percentage, e.g. 22.8 -> '22.8%'."""
    return "-" if value is None else f"{value:.{decimals}f}%"


def times(value: float | None, decimals: int = 1) -> str:
    """Multiple, e.g. 30 -> '30.0x'."""
    return "-" if value is None else f"{value:.{decimals}f}x"


def nice_date(day: dt.date | None) -> str:
    """Date like 'Wed, 2 Dec 2026'."""
    if day is None:
        return "-"
    return f"{day:%a}, {day.day} {day:%b %Y}"
