"""Client message drafts for each IPO event, plus an optional TEST-only Telegram sender.

Every message is neutral: dates, prices and process reminders only. No "apply now",
no opinions, no GMP. Each ends with the compliance line. A person copies the draft and
sends it through the broker's approved channel; nothing goes to clients automatically.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from typing import Any

import pandas as pd

from ipodesk.config import disclaimer, get_settings
from ipodesk.formatting import indian_group, nice_date


def _band(row: Any) -> str:
    """'₹300 to ₹315' style price band."""
    return f"₹{indian_group(row['price_band_low'])} to ₹{indian_group(row['price_band_high'])}"


def opens_today(row: Any) -> str:
    """Draft for the day the issue opens."""
    link = f"\nRHP: {row['rhp_link']}" if row.get("rhp_link") else ""
    return (
        f"IPO opens today: {row['company']} ({row['board']})\n"
        f"Price band: {_band(row)} per share\n"
        f"Lot size: {row['lot_size']} shares (minimum ₹{indian_group(row['price_band_high'] * row['lot_size'])} "
        f"at the upper band)\n"
        f"Bidding: {nice_date(row['open_date'])} to {nice_date(row['close_date'])}{link}\n\n"
        f"{disclaimer()}"
    )


def last_day(row: Any) -> str:
    """Draft for the close day: approve the UPI mandate before the cut-off."""
    cutoff = get_settings()["calendar"]["mandate_cutoff_time"]
    return (
        f"Last day today: the {row['company']} IPO closes today ({nice_date(row['close_date'])}).\n"
        f"If you have placed a bid, please approve your UPI mandate in your UPI app before {cutoff} today. "
        f"A bid without an approved mandate is not valid.\n\n{disclaimer()}"
    )


def allotment_out(row: Any) -> str:
    """Draft for allotment day (T+1)."""
    return (
        f"Allotment status for the {row['company']} IPO is out. You can check it in your app or on the "
        f"registrar's website using your PAN or application number.\n"
        f"If shares are not allotted, the blocked amount is released by {nice_date(row['credit_date'])}.\n\n"
        f"{disclaimer()}"
    )


def lists_today(row: Any) -> str:
    """Draft for listing day (T+3)."""
    return (
        f"{row['company']} shares list on the exchange today ({nice_date(row['listing_date'])}).\n"
        f"Allotted shares are credited to your demat account before listing.\n\n{disclaimer()}"
    )


TEMPLATES = {"Opens": opens_today, "Last day": last_day, "Allotment": allotment_out, "Listing": lists_today}


def drafts_for_ipo(row: Any) -> dict[str, str]:
    """All four message drafts for one enriched IPO row: {event: text}."""
    return {event: fn(row) for event, fn in TEMPLATES.items()}


def drafts_for_date(enriched: pd.DataFrame, day: dt.date) -> list[dict[str, str]]:
    """Message drafts for every event happening on `day` (e.g. today)."""
    columns = {"Opens": "open_date", "Last day": "close_date", "Allotment": "allotment_date", "Listing": "listing_date"}
    out = []
    for _, row in enriched.iterrows():
        for event, col in columns.items():
            if row[col] == day:
                out.append({"company": row["company"], "event": event, "text": TEMPLATES[event](row)})
    return out


def send_telegram_test(text: str, demo_mode: bool | None = None) -> str:
    """Send `text` to the TEST Telegram chat only (bot token + chat id from secrets/env).

    Refuses unless demo mode is on, so this can never be pointed at real clients by accident.
    Returns a short status message instead of raising, so the UI can show it.
    """
    demo_mode = get_settings()["alerts"]["demo_mode"] if demo_mode is None else demo_mode
    if not demo_mode:
        return "Blocked: sending is only allowed in demo mode, to a test chat."
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_TEST_CHAT_ID", "")
    if not token or not chat_id:
        return "Not configured: add TELEGRAM_BOT_TOKEN and TELEGRAM_TEST_CHAT_ID to secrets."
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": f"[TEST] {text}"}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10) as r:
            ok = json.loads(r.read().decode()).get("ok", False)
        return "Sent to the test chat." if ok else "Telegram did not accept the message."
    except Exception as exc:  # network errors etc. -> show, don't crash
        return f"Send failed: {type(exc).__name__}"
