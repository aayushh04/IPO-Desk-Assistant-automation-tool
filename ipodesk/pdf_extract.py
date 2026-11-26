"""Read an RHP PDF page by page, keeping page numbers, and cache the result by file hash.

Why page by page? Every number in the final note must point back to the page it came
from, so we never mix pages together without a "=== PAGE n ===" marker.

Two passes:
1. A fast plain-text pass over ALL pages (about 2-3 s for 700 pages) used to find sections.
2. A slower "layout" pass, only for the pages we send to the LLM, which keeps table
   columns lined up (so "Revenue  31,519.68  26,905.10" stays on one row).

Why cache? A 500-page RHP takes a few seconds to read. We hash the file's bytes
(SHA-256); if the same file is uploaded again, we load the saved text instantly.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import pymupdf

from ipodesk.config import PROJECT_ROOT

CACHE_DIR: Path = PROJECT_ROOT / ".cache" / "extract"
CACHE_VERSION: int = 2  # bump if the extraction logic changes, to ignore old cache files

ProgressFn = Callable[[int, int], None]  # (pages done, total pages)


@dataclass
class ExtractedDoc:
    """The text of every page of one PDF, plus its hash."""

    file_hash: str
    pages: list[str] = field(default_factory=list)  # pages[0] is page 1 (fast plain text)
    layout: dict[int, str] = field(default_factory=dict)  # page_no -> column-aligned text

    @property
    def n_pages(self) -> int:
        """Number of pages in the PDF."""
        return len(self.pages)

    def page(self, page_no: int) -> str:
        """Best text of a 1-based page: layout text if we have it, else plain ('' if out of range)."""
        if page_no in self.layout:
            return self.layout[page_no]
        return self.pages[page_no - 1] if 1 <= page_no <= self.n_pages else ""

    def text_of(self, page_numbers: list[int], max_chars: int | None = None) -> str:
        """Join the given pages with '=== PAGE n ===' markers, optionally capped in length."""
        parts, used = [], 0
        for n in page_numbers:
            chunk = f"=== PAGE {n} ===\n{self.page(n).strip()}\n"
            if max_chars is not None and used + len(chunk) > max_chars:
                break
            parts.append(chunk)
            used += len(chunk)
        return "\n".join(parts)


def file_hash(data: bytes) -> str:
    """SHA-256 fingerprint of the file bytes (same file -> same hash)."""
    return hashlib.sha256(data).hexdigest()


def extract_pages(data: bytes, progress: ProgressFn | None = None) -> list[str]:
    """Return the plain text of every page, in order. Calls `progress` every 10 pages."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        total = doc.page_count
        texts: list[str] = []
        for i, page in enumerate(doc):
            texts.append(page.get_text("text"))
            if progress and (i % 10 == 0 or i == total - 1):
                progress(i + 1, total)
    return texts


def extract_document(
    data: bytes, progress: ProgressFn | None = None, cache_dir: Path | None = CACHE_DIR
) -> ExtractedDoc:
    """Extract all pages, using the on-disk cache when this exact file was seen before."""
    digest = file_hash(data)
    cache_file = cache_dir / f"{digest}_v{CACHE_VERSION}.json" if cache_dir else None
    if cache_file and cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if progress:
            progress(len(cached["pages"]), len(cached["pages"]))
        cached["layout"] = {int(k): v for k, v in cached.get("layout", {}).items()}
        return ExtractedDoc(**cached)
    doc = ExtractedDoc(file_hash=digest, pages=extract_pages(data, progress))
    save_to_cache(doc, cache_dir)
    return doc


def save_to_cache(doc: ExtractedDoc, cache_dir: Path | None = CACHE_DIR) -> None:
    """Write the document (including any layout pages) to the cache folder."""
    if cache_dir is None:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{doc.file_hash}_v{CACHE_VERSION}.json"
    cache_file.write_text(json.dumps(asdict(doc)), encoding="utf-8")


def add_layout_text(
    doc: ExtractedDoc, data: bytes, page_numbers: list[int], cache_dir: Path | None = CACHE_DIR
) -> ExtractedDoc:
    """Fill in column-aligned text for the given pages (skips pages already done), then re-cache."""
    todo = [n for n in sorted(set(page_numbers)) if n not in doc.layout and 1 <= n <= doc.n_pages]
    if not todo:
        return doc
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        for n in todo:
            try:
                doc.layout[n] = pdf[n - 1].get_text("text", sort=True)
            except Exception:  # keep the plain text if layout mode fails on an odd page
                doc.layout[n] = doc.pages[n - 1]
    save_to_cache(doc, cache_dir)
    return doc


def extract_tables(data: bytes, page_numbers: list[int]) -> dict[int, list[list[list[str]]]]:
    """Find tables on selected pages only (table detection is slow, so never run it on all 500).

    Returns {page_no: [table, ...]} where each table is a list of rows of cell strings.
    Pages where no ruled table is detected are simply left out.
    """
    found: dict[int, list[list[list[str]]]] = {}
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for n in page_numbers:
            if not 1 <= n <= doc.page_count:
                continue
            try:
                tables = doc[n - 1].find_tables().tables
            except Exception:  # a malformed page must not crash the whole run
                continue
            rows = [[[(c or "").strip() for c in row] for row in t.extract()] for t in tables]
            if rows:
                found[n] = rows
    return found
