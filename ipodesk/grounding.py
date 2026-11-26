"""Grounding check: every number the LLM gives us must actually appear in the RHP text.

LLMs can "hallucinate": produce a confident, plausible number that isn't in the document.
So we never trust a figure just because the model returned it. For each number:

1. Collect every number printed on the page the model cited, normalised
   ("31,519.68" -> 31519.68, "(12.60)" -> 12.60, Indian "1,00,000" -> 100000).
2. If the model's number is there -> "ok".
3. If not, look on the other pages we sent -> "page corrected" (number real, page wrong).
4. If it is nowhere in the text we sent -> "verify manually". It stays in the draft
   but is highlighted, and the reviewer must confirm it before export.

We compare absolute values because RHPs show negatives in brackets, and allow a tiny
tolerance so "72.4" matches "72.40".
"""
from __future__ import annotations

import re
from typing import Iterator, Literal

from pydantic import BaseModel

from ipodesk.pdf_extract import ExtractedDoc
from ipodesk.schemas import Sourced, SourcedText

Status = Literal["ok", "page corrected", "verify manually"]

# A number: optional bracket, digits with commas, optional decimals.
_NUM = re.compile(r"(?<![\w.])\(?\d[\d,]*(?:\.\d+)?\)?(?![\w])")
TOLERANCE: float = 0.0051


class GroundingResult(BaseModel):
    """Grounding outcome for one number."""

    task: str
    field: str
    value: float
    cited_page: int | None
    status: Status
    found_on: list[int] = []
    message: str = ""


def parse_number(token: str) -> float | None:
    """'1,240.60' -> 1240.6, '(12.60)' -> 12.6 (absolute value), junk -> None."""
    cleaned = token.strip("()").replace(",", "")
    try:
        return abs(float(cleaned))
    except ValueError:
        return None


def numbers_in_text(text: str) -> list[float]:
    """Every number printed in `text`, as absolute values."""
    out = []
    for token in _NUM.findall(text.replace("₹", " ")):
        value = parse_number(token)
        if value is not None:
            out.append(value)
    return out


def value_in_text(value: float, text: str) -> bool:
    """True if |value| is printed in `text` (within a tiny rounding tolerance)."""
    target = abs(value)
    return any(abs(n - target) <= TOLERANCE for n in numbers_in_text(text))


def _normal(text: str) -> str:
    """Lowercase and squash whitespace/punctuation, for quote matching."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def check_number(task: str, field: str, value: float, cited_page: int | None, quote: str,
                 doc: ExtractedDoc, sent_pages: list[int]) -> GroundingResult:
    """Ground one number against the cited page, then against all pages that were sent."""
    if cited_page and value_in_text(value, doc.page(cited_page)):
        return GroundingResult(task=task, field=field, value=value, cited_page=cited_page,
                               status="ok", found_on=[cited_page])
    # A zero backed by a verbatim quote (e.g. "none of the shares are pledged") is grounded.
    if value == 0 and cited_page and quote and _normal(quote) in _normal(doc.page(cited_page)):
        return GroundingResult(task=task, field=field, value=value, cited_page=cited_page, status="ok",
                               found_on=[cited_page], message="Zero supported by quoted text.")
    elsewhere = [p for p in sent_pages if p != cited_page and value_in_text(value, doc.page(p))]
    if elsewhere and cited_page is None:  # no page was claimed, so finding it anywhere is fine
        return GroundingResult(task=task, field=field, value=value, cited_page=None, status="ok",
                               found_on=elsewhere[:5])
    if elsewhere:
        return GroundingResult(task=task, field=field, value=value, cited_page=cited_page,
                               status="page corrected", found_on=elsewhere[:5],
                               message=f"Not on cited page {cited_page}; found on page {elsewhere[0]}.")
    return GroundingResult(task=task, field=field, value=value, cited_page=cited_page,
                           status="verify manually",
                           message="Number not found in the source pages. Verify manually.")


def iter_sourced(model: BaseModel, prefix: str = "") -> Iterator[tuple[str, Sourced | SourcedText]]:
    """Walk a pydantic model and yield (path, item) for every Sourced / SourcedText inside it."""
    for name, value in model:
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, (Sourced, SourcedText)):
            yield path, value
        elif isinstance(value, BaseModel):
            yield from iter_sourced(value, path)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                label = getattr(item, "year", None) or getattr(item, "name", None) or getattr(item, "purpose", None) or i
                if isinstance(item, (Sourced, SourcedText)):
                    yield f"{path}[{label}]", item
                elif isinstance(item, BaseModel):
                    yield from iter_sourced(item, f"{path}[{label}]")


def ground_model(task: str, model: BaseModel, doc: ExtractedDoc, sent_pages: list[int]) -> list[GroundingResult]:
    """Check every number in an LLM result: Sourced values and numbers inside sentences."""
    results: list[GroundingResult] = []
    for path, item in iter_sourced(model):
        if isinstance(item, Sourced):
            if item.value is not None:
                results.append(check_number(task, path, item.value, item.page, item.quote, doc, sent_pages))
        else:  # numbers inside summary sentences, e.g. "64% of revenue"
            for n in numbers_in_text(item.text):
                results.append(check_number(task, f"{path} (in text)", n, item.page, "", doc, sent_pages))
    # Plain lists of sentences (e.g. the 3-line snapshot) carry no page: search all sent pages.
    for name, value in model:
        if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
            for i, line in enumerate(value):
                for n in numbers_in_text(line):
                    results.append(check_number(task, f"{name}[{i}] (in text)", n, None, "", doc, sent_pages))
    return results


def summary(results: list[GroundingResult]) -> dict[str, int]:
    """Count results by status, e.g. {'ok': 40, 'page corrected': 2, 'verify manually': 1}."""
    counts = {"ok": 0, "page corrected": 0, "verify manually": 0}
    for r in results:
        counts[r.status] += 1
    return counts
