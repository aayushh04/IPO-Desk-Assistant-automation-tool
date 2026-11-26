"""Find the key RHP chapters (Risk Factors, Objects of the Offer, ...) and their page ranges.

How it works, in plain words:
1. A real chapter heading is printed in CAPITALS near the TOP of a page, on a line by itself
   (sometimes with a prefix like "SECTION II -"). Mentions inside sentences ("see 'Our
   Business' on page 309") and mixed-case running headers ("Notes to Restated ...") are ignored.
2. Each section has a few regex patterns to allow for wording variations
   ("Objects of the Offer" / "Objects of the Issue").
3. The table of contents lists every heading too, so TOC pages are skipped.
4. A section ends where the next known chapter heading starts (capped at a maximum length).
5. If a section isn't found, we say so, and the user can type the page range by hand.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ipodesk.pdf_extract import ExtractedDoc

HEAD_LINES: int = 8  # how many non-empty lines at the top of a page can hold a heading


@dataclass(frozen=True)
class SectionSpec:
    """A section we look for: its key, display label, heading patterns and max length."""

    key: str
    label: str
    patterns: tuple[str, ...]
    max_pages: int = 40


SECTION_SPECS: list[SectionSpec] = [
    SectionSpec("risk_factors", "Risk Factors", (r"RISK FACTORS",), 60),
    SectionSpec("financial_summary", "Summary of Financial Information",
                (r"SUMMARY (OF )?(THE )?(RESTATED )?(CONSOLIDATED )?FINANCIAL (INFORMATION|STATEMENTS)",), 12),
    SectionSpec("capital_structure", "Capital Structure", (r"CAPITAL STRUCTURE",), 40),
    SectionSpec("objects", "Objects of the Offer", (r"OBJECTS? OF THE (OFFER|ISSUE)",), 30),
    SectionSpec("basis_for_price", "Basis for Offer Price",
                (r"BASIS (FOR|OF) (THE )?(OFFER|ISSUE) PRICE",), 30),
    SectionSpec("industry", "Industry Overview", (r"(OUR )?INDUSTRY OVERVIEW",), 80),
    SectionSpec("business", "Our Business", (r"OUR BUSINESS", r"BUSINESS OVERVIEW"), 60),
    SectionSpec("promoters", "Our Promoters",
                (r"(OUR )?PROMOTERS?( AND (THE )?PROMOTER GROUP)?",), 15),
    SectionSpec("restated_financials", "Restated Financial Information",
                (r"RESTATED (CONSOLIDATED |STANDALONE )?FINANCIAL (INFORMATION|STATEMENTS)",), 120),
    SectionSpec("related_party", "Related Party Transactions",
                (r"(SUMMARY OF )?RELATED PARTY TRANSACTIONS",), 10),
    SectionSpec("litigation", "Outstanding Litigation",
                (r"OUTSTANDING LITIGATIONS?( AND (OTHER )?MATERIAL DEVELOPMENTS)?",
                 r"LITIGATION AND MATERIAL DEVELOPMENTS"), 40),
]
SPEC_BY_KEY: dict[str, SectionSpec] = {s.key: s for s in SECTION_SPECS}

# Other common RHP chapter headings. We don't extract them, but they mark where a section ends.
BOUNDARY_PATTERNS: tuple[str, ...] = (
    r"GENERAL INFORMATION", r"THE OFFER", r"SUMMARY OF THE OFFER DOCUMENT",
    r"STATEMENT OF (POSSIBLE )?SPECIAL TAX BENEFITS", r"KEY REGULATIONS AND POLICIES( IN INDIA)?",
    r"HISTORY AND CERTAIN CORPORATE MATTERS", r"OUR MANAGEMENT", r"OUR GROUP COMPAN(Y|IES)",
    r"DIVIDEND POLICY", r"OTHER FINANCIAL INFORMATION", r"CAPITALI[SZ]ATION STATEMENT",
    r"FINANCIAL INDEBTEDNESS", r"MANAGEMENT.?S DISCUSSION AND ANALYSIS.*",
    r"GOVERNMENT AND OTHER APPROVALS", r"OTHER REGULATORY AND STATUTORY DISCLOSURES",
    r"TERMS OF THE OFFER", r"OFFER STRUCTURE", r"OFFER PROCEDURE", r"DECLARATION",
    r"MAIN PROVISIONS OF (THE )?ARTICLES OF ASSOCIATION", r"MATERIAL CONTRACTS AND DOCUMENTS FOR INSPECTION",
    r"DEFINITIONS AND ABBREVIATIONS",
)

_SECTION_PREFIX = re.compile(r"^SECTION\s+[IVXL0-9]+\s*(?:[^A-Z0-9\s]\s*)?", re.IGNORECASE)
_SECTION_DIVIDER = re.compile(r"^SECTION [IVXL]+")
_TOC_LINE = re.compile(r"(\.{4,}|\s{3,})\s*\d{1,4}\s*$")


@dataclass
class SectionHit:
    """Where one section was found (or not)."""

    key: str
    label: str
    found: bool = False
    start_page: int | None = None
    end_page: int | None = None
    heading: str = ""
    candidates: list[int] = field(default_factory=list)  # every page whose top matched
    manual: bool = False  # True if the user typed the range

    @property
    def pages(self) -> list[int]:
        """All page numbers in the range ([] if not found)."""
        if self.start_page is None or self.end_page is None:
            return []
        return list(range(self.start_page, self.end_page + 1))


def normalize_line(line: str) -> str:
    """Uppercase, turn quotes/dashes/odd symbols into spaces, collapse whitespace."""
    line = re.sub(r"[^\w&'’]+", " ", line)
    return re.sub(r"\s+", " ", line).strip().upper().replace("’", "'")


def _is_caps(line: str) -> bool:
    """True if the letters in the line are (nearly) all capitals, like a chapter heading."""
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) >= 0.9


def _top_lines(text: str) -> list[str]:
    """The first few non-empty lines of a page, skipping bare page numbers and dashes."""
    out = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or re.fullmatch(r"[\d\W_]+", stripped):
            continue
        out.append(stripped)
        if len(out) >= HEAD_LINES:
            break
    return out


def is_toc_page(text: str) -> bool:
    """A table-of-contents page has a 'CONTENTS' title or many 'Heading ..... 34' style lines."""
    head = " ".join(_top_lines(text)[:3]).upper()
    if "TABLE OF CONTENTS" in head or head.startswith("CONTENTS"):
        return True
    return sum(bool(_TOC_LINE.search(line)) for line in text.splitlines()) >= 6


def _heading_match(line: str, patterns: tuple[str, ...]) -> bool:
    """True if the whole line (minus any 'SECTION II -' prefix) matches one of the patterns."""
    norm = _SECTION_PREFIX.sub("", normalize_line(line)).strip()
    return any(re.fullmatch(p, norm) for p in patterns)


def find_sections(doc: ExtractedDoc) -> dict[str, SectionHit]:
    """Locate every section in SECTION_SPECS. Returns {key: SectionHit}."""
    hits = {s.key: SectionHit(s.key, s.label) for s in SECTION_SPECS}
    boundaries: set[int] = set()
    for page_no, text in enumerate(doc.pages, start=1):
        if is_toc_page(text):
            continue
        for line in _top_lines(text):
            if not _is_caps(line):
                continue
            # "SECTION V - FINANCIAL INFORMATION" style dividers always start a new chapter.
            if _heading_match(line, BOUNDARY_PATTERNS) or _SECTION_DIVIDER.match(normalize_line(line)):
                boundaries.add(page_no)
            for spec in SECTION_SPECS:
                if _heading_match(line, spec.patterns):
                    hit = hits[spec.key]
                    if page_no not in hit.candidates:
                        hit.candidates.append(page_no)
                    if not hit.found:
                        hit.found, hit.start_page, hit.heading = True, page_no, line.strip()
                    boundaries.add(page_no)
    _set_end_pages(hits, boundaries, doc.n_pages)
    return hits


def _set_end_pages(hits: dict[str, SectionHit], boundaries: set[int], n_pages: int) -> None:
    """End each section the page before the next chapter starts, capped at its max length."""
    starts = sorted(boundaries)
    for hit in hits.values():
        if not hit.found or hit.start_page is None:
            continue
        nxt = next((p for p in starts if p > hit.start_page), n_pages + 1)
        cap = hit.start_page + SPEC_BY_KEY[hit.key].max_pages - 1
        hit.end_page = max(hit.start_page, min(nxt - 1, cap, n_pages))


def set_manual_range(hits: dict[str, SectionHit], key: str, start: int, end: int, n_pages: int) -> None:
    """Let the user point to a section's pages by hand (e.g. when it wasn't found)."""
    start, end = max(1, start), min(n_pages, end)
    if end < start:
        raise ValueError("End page must be on or after the start page.")
    hit = hits[key]
    hit.found, hit.start_page, hit.end_page, hit.manual = True, start, end, True
    hit.heading = hit.heading or "(set manually)"


def sections_table(hits: dict[str, SectionHit]) -> list[dict[str, object]]:
    """Rows for a 'which sections were found, on which pages' table."""
    return [
        {
            "Section": h.label,
            "Found": "Yes" if h.found else "Not found",
            "Pages": f"{h.start_page}-{h.end_page}" if h.found else "-",
            "Heading seen": h.heading if h.found else "",
            "Set by": "user" if h.manual else ("finder" if h.found else ""),
        }
        for h in hits.values()
    ]
