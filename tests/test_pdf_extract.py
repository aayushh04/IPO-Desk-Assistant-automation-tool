"""Tests for page-by-page PDF extraction and caching."""
from ipodesk.pdf_extract import add_layout_text, extract_document, file_hash


def test_pages_keep_their_numbers(sample_pdf_bytes, tmp_path) -> None:
    doc = extract_document(sample_pdf_bytes, cache_dir=tmp_path)
    assert doc.n_pages == 15
    assert "OBJECTS OF THE OFFER" in doc.page(7)
    assert doc.page(99) == ""


def test_cache_is_used_second_time(sample_pdf_bytes, tmp_path) -> None:
    extract_document(sample_pdf_bytes, cache_dir=tmp_path)
    assert len(list(tmp_path.glob(f"{file_hash(sample_pdf_bytes)}*.json"))) == 1
    calls: list[tuple[int, int]] = []
    doc = extract_document(sample_pdf_bytes, progress=lambda d, t: calls.append((d, t)), cache_dir=tmp_path)
    assert calls == [(15, 15)]  # loaded from cache in one step
    assert doc.n_pages == 15


def test_text_of_marks_pages_and_respects_budget(sample_pdf_bytes, tmp_path) -> None:
    doc = extract_document(sample_pdf_bytes, cache_dir=tmp_path)
    text = doc.text_of([6, 7])
    assert "=== PAGE 6 ===" in text and "=== PAGE 7 ===" in text
    assert "=== PAGE 7 ===" not in doc.text_of([6, 7], max_chars=len(doc.text_of([6])) + 5)


def test_layout_text_added_and_cached(sample_pdf_bytes, tmp_path) -> None:
    doc = extract_document(sample_pdf_bytes, cache_dir=tmp_path)
    add_layout_text(doc, sample_pdf_bytes, [5], cache_dir=tmp_path)
    assert 5 in doc.layout and "1,240.60" in doc.page(5)
    again = extract_document(sample_pdf_bytes, cache_dir=tmp_path)
    assert 5 in again.layout
