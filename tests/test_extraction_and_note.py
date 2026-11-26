"""End-to-end note pipeline on the sample RHP using the offline fake LLM."""
import datetime as dt

import pytest

from ipodesk.exports import to_docx, to_pdf
from ipodesk.extraction import run_all, sample_fake_reply, to_crore
from ipodesk.llm import LLMClient, LLMConfig
from ipodesk.note import build_draft, compliance_issues, evaluate, export_blockers
from ipodesk.pdf_extract import extract_document
from ipodesk.schemas import IssueInputs, Sourced
from ipodesk.sections import find_sections


@pytest.fixture()
def draft(sample_pdf_bytes, tmp_path, monkeypatch):
    monkeypatch.setattr("ipodesk.pdf_extract.CACHE_DIR", tmp_path)
    doc = extract_document(sample_pdf_bytes, cache_dir=tmp_path)
    hits = find_sections(doc)
    client = LLMClient(LLMConfig("fake", "fake"), fake_reply=sample_fake_reply)
    results = run_all(doc, sample_pdf_bytes, hits, client, use_cache=False)
    manual = IssueInputs(price_band_low=300, price_band_high=315, lot_size=47,
                         open_date=dt.date(2026, 11, 30), close_date=dt.date(2026, 12, 2))
    return build_draft(results, manual, hits)


def test_unit_conversion_to_crore() -> None:
    assert to_crore(Sourced(value=31519.68, unit="million")) == pytest.approx(3151.968)
    assert to_crore(Sourced(value=5000, unit="lakh")) == pytest.approx(50.0)
    assert to_crore(Sourced(value=None, unit="crore")) is None


def test_pipeline_numbers_and_flags(draft) -> None:
    metrics, flags = evaluate(draft)
    assert metrics.pe == pytest.approx(30.0) and metrics.market_cap_cr == pytest.approx(3150.0)
    status = {f.name.split(" ")[0]: f.status for f in flags}
    assert status["OFS"] == "flag" and status["General"] == "flag" and status["Negative"] == "ok"


def test_planted_hallucination_is_caught(draft) -> None:
    bad = draft.unverified()
    assert len(bad) == 1 and bad[0].value == 118.80


def test_export_needs_reviewer_and_confirmation(draft) -> None:
    assert export_blockers(draft, figures_confirmed=False, wording_confirmed=False)
    draft.reviewer = "Desk Analyst"
    assert export_blockers(draft, figures_confirmed=True, wording_confirmed=False) == []


def test_compliance_scan_catches_advice_words(draft) -> None:
    assert compliance_issues(draft) == []
    draft.snapshot += "\nInvestors should subscribe for listing gains."
    assert "subscribe" in compliance_issues(draft)
    draft.snapshot = "The issue saw strong subscription from selling shareholders."  # factual words are fine
    assert compliance_issues(draft) == []


def test_exports_produce_files_with_disclaimer(draft) -> None:
    draft.reviewer = "Desk Analyst"
    assert to_docx(draft)[:2] == b"PK"  # .docx is a zip file
    pdf = to_pdf(draft)
    assert pdf[:4] == b"%PDF"
    import pymupdf
    text = "".join(p.get_text() for p in pymupdf.open(stream=pdf, filetype="pdf"))
    assert "Not a recommendation" in text and "Mon, 7 Dec 2026" in text
