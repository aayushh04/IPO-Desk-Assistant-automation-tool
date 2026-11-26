"""Tests for the section finder."""
import pytest

from ipodesk.pdf_extract import ExtractedDoc, extract_document
from ipodesk.sample_data import sample_rhp_expected_pages
from ipodesk.sections import SECTION_SPECS, find_sections, is_toc_page, set_manual_range


def test_finds_all_headings_in_sample_pdf_with_correct_pages(sample_pdf_bytes, tmp_path) -> None:
    hits = find_sections(extract_document(sample_pdf_bytes, cache_dir=tmp_path))
    expected = sample_rhp_expected_pages()
    assert {k: h.start_page for k, h in hits.items()} == expected
    assert all(h.found for h in hits.values())


def test_toc_page_is_skipped(sample_pdf_bytes, tmp_path) -> None:
    doc = extract_document(sample_pdf_bytes, cache_dir=tmp_path)
    assert is_toc_page(doc.page(2))
    assert all(2 not in h.candidates for h in find_sections(doc).values())


def test_mentions_in_sentences_and_mixed_case_are_ignored() -> None:
    doc = ExtractedDoc("x", [
        "OUR MANAGEMENT\nFor details see 'Our Business' on page 3.\n",
        "Notes to Restated Financial Information\nCapital Structure\n",
        "OUR BUSINESS\nWe make things.",
        "SECTION VI – OBJECTS OF THE ISSUE\nThe issue...",
        "OUR MANAGEMENT\n...",
    ])
    hits = find_sections(doc)
    assert hits["business"].start_page == 3 and hits["business"].end_page == 3
    assert hits["objects"].start_page == 4  # wording variation + SECTION prefix
    assert not hits["capital_structure"].found
    assert not hits["restated_financials"].found


def test_missing_section_can_be_set_by_hand() -> None:
    doc = ExtractedDoc("x", ["nothing here"] * 10)
    hits = find_sections(doc)
    assert not hits["litigation"].found and hits["litigation"].pages == []
    set_manual_range(hits, "litigation", 4, 6, doc.n_pages)
    assert hits["litigation"].pages == [4, 5, 6] and hits["litigation"].manual
    with pytest.raises(ValueError):
        set_manual_range(hits, "litigation", 6, 4, doc.n_pages)


def test_section_list_covers_the_brief() -> None:
    keys = {s.key for s in SECTION_SPECS}
    assert {"objects", "basis_for_price", "risk_factors", "financial_summary", "restated_financials",
            "capital_structure", "promoters", "litigation", "related_party", "industry", "business"} <= keys
