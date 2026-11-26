"""Load settings from config/settings.yaml and the exchange holiday list.

Pure Python (no Streamlit). Pages and modules call `get_settings()` instead of
reading YAML themselves, so every setting lives in one place.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
CONFIG_DIR: Path = PROJECT_ROOT / "config"


@lru_cache(maxsize=1)
def get_settings() -> dict[str, Any]:
    """Return the parsed settings.yaml as a dict (read once, then cached)."""
    with open(CONFIG_DIR / "settings.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_holidays(path: Path | None = None) -> list[dt.date]:
    """Return the exchange holiday dates from holidays.yaml, sorted."""
    path = path or PROJECT_ROOT / get_settings()["calendar"]["holidays_file"]
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    dates = [_to_date(item["date"]) for item in data.get("holidays", [])]
    return sorted(dates)


def _to_date(value: Any) -> dt.date:
    """Accept a date object or an ISO 'YYYY-MM-DD' string and return a date."""
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def disclaimer() -> str:
    """Return the compliance disclaimer that must appear on every note."""
    return get_settings()["compliance"]["disclaimer"]
