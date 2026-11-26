"""Smoke tests: every Streamlit page runs without errors (headless, via Streamlit's AppTest)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["Home.py", "views/overview.py", "views/note_generator.py", "views/ipo_calendar.py", "views/subscription_tracker.py"]


@pytest.mark.parametrize("page", PAGES)
def test_page_runs(page: str) -> None:
    at = AppTest.from_file(str(ROOT / page), default_timeout=60).run()
    assert not at.exception, at.exception


def test_note_generator_sample_flow_offline() -> None:
    at = AppTest.from_file(str(ROOT / "views/note_generator.py"), default_timeout=90).run()
    at.radio[0].set_value("Use the sample RHP (fictional company)").run()
    if not at.toggle[0].value:  # offline demo answers (on by default when no API key is set)
        at.toggle[0].set_value(True).run()
    next(b for b in at.button if b.label == "Run AI extraction").click().run()
    assert not at.exception, at.exception
    page = " ".join(m.value for m in at.markdown)
    assert "30.0x" in page and "Q1" in page and "Open queries" in page
    assert any("To unlock" in c.value for c in at.caption)  # export locked until sign-off
    assert any(b.label == "Download note (PDF)" and b.disabled for b in at.button)


def test_subscription_manual_entry_runs() -> None:
    at = AppTest.from_file(str(ROOT / "views/subscription_tracker.py"), default_timeout=60).run()
    at.radio[0].set_value("Enter by hand").run()
    assert not at.exception and any("Day 1 close" in c.value for c in at.code)
