"""Send each RHP section to the LLM, get strict JSON back, and ground every number.

Flow for one task (e.g. "objects"):
  section pages (from sections.py) -> column-aligned text with '=== PAGE n ===' markers
  -> LLM with a pydantic schema -> validated object -> grounding check -> cached on disk

Cost control: only the first few pages of each relevant section are sent (with a character
budget), and results are cached per (file hash, task, model, pages), so re-running the
same RHP costs nothing.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from ipodesk.config import PROJECT_ROOT
from ipodesk.grounding import GroundingResult, ground_model
from ipodesk.llm import LLMClient, LLMError
from ipodesk.pdf_extract import ExtractedDoc, add_layout_text
from ipodesk.schemas import (BasisOut, BusinessOut, CapitalOut, FinancialsOut, IssueInputs, LitigationOut,
                             NoteInputs, ObjectsOut, PeerPE, RisksOut, RptOut, Sourced, YearFinancials)
from ipodesk.sections import SectionHit
from ipodesk.valuation import CRORE, post_issue_shares_from_fresh

LLM_CACHE_DIR: Path = PROJECT_ROOT / ".cache" / "llm"
CHAR_BUDGET: int = 45_000  # roughly 11-12k tokens of RHP text per task

SYSTEM_PROMPT = """You extract facts from an Indian IPO Red Herring Prospectus (RHP) for a stock broker's
information note. TASK: {task}

Rules:
- Use ONLY the RHP text provided. Never guess or use outside knowledge. If something is not stated, use null.
- Copy every number exactly as printed, without commas. A number in brackets like (12.60) is negative: -12.60.
- Give the unit as printed (the table header often says "in million" or "in lakh" or "in crore").
- "page" is the number in the nearest '=== PAGE n ===' marker above the text you used.
- "quote" is a short verbatim snippet from that page containing the number.
- Write text as short, neutral, factual statements. No opinions, no recommendations, no ratings,
  and never words like subscribe, avoid, buy or sell. Never mention grey market premium.
{extra}"""


@dataclass(frozen=True)
class Task:
    """One extraction job: which sections to read and which schema to fill."""

    name: str
    label: str
    sections: tuple[str, ...]       # tried in order; pages from each are combined
    schema: type[BaseModel]
    pages_per_section: int
    instructions: str
    include_cover: bool = False


TASKS: list[Task] = [
    Task("business", "Company snapshot and strengths", ("business", "industry"), BusinessOut, 6,
         "Write 3 short lines on what the company does (products, customers, scale) and list up to 6 "
         "strengths exactly as the company describes them."),
    Task("risks", "Top risk factors", ("risk_factors",), RisksOut, 6,
         "Summarise the FIRST 5 numbered risk factors (RHPs list them in order of importance), "
         "one neutral sentence each."),
    Task("objects", "Issue structure and use of proceeds", ("objects",), ObjectsOut, 6,
         "Find the fresh issue size, the offer for sale (OFS) size (money and/or number of shares), the "
         "gross proceeds of the fresh issue, the amount for general corporate purposes, and each object "
         "with its amount.", include_cover=True),
    Task("capital", "Share capital and promoter pledge", ("capital_structure",), CapitalOut, 6,
         "Find shares outstanding before and after the offer, face value, promoter holding before the offer "
         "(%), and the number of promoter shares pledged (0 if the RHP says none are pledged)."),
    Task("financials", "Financials (3 years)", ("financial_summary", "restated_financials"), FinancialsOut, 8,
         "Extract the 3 latest FULL financial years (ignore part-year periods like 'three months ended'). "
         "For each year: revenue from operations, EBITDA, restated profit after tax, net cash from operating "
         "activities, total borrowings and net worth. If EBITDA is not shown, use null."),
    Task("basis", "Peer comparison", ("basis_for_price",), BasisOut, 8,
         "From the comparison with listed industry peers, list each peer (not the issuer) with its P/E. "
         "Also give the issuer's basic EPS for the latest full year."),
    Task("litigation", "Outstanding litigation", ("litigation",), LitigationOut, 6,
         "Find the total quantifiable amount involved in outstanding litigation (add the amounts in the "
         "summary table if there is no total) and up to 4 notable matters."),
    Task("rpt", "Related-party transactions", ("related_party",), RptOut, 5,
         "Find the total value of related party transactions in the latest full financial year."),
]
TASK_BY_NAME: dict[str, Task] = {t.name: t for t in TASKS}

ProgressFn = Callable[[int, int, str], None]  # (tasks done, total, label)


class TaskResult(BaseModel):
    """Outcome of one task."""

    name: str
    label: str
    ok: bool
    data: dict | None = None
    error: str = ""
    pages_sent: list[int] = []
    grounding: list[GroundingResult] = []
    from_cache: bool = False


def pages_for_task(task: Task, hits: dict[str, SectionHit]) -> list[int]:
    """The pages to send for a task: the first N pages of each relevant section that was found.

    Order matters: the main section comes first (e.g. 'Our Business' before 'Industry
    Overview'), so if the character budget runs out, it's the less important pages that are cut.
    """
    pages: list[int] = [1, 2] if task.include_cover else []
    for key in task.sections:
        hit = hits.get(key)
        if hit and hit.found:
            pages += hit.pages[: task.pages_per_section]
    return list(dict.fromkeys(pages))  # remove duplicates, keep order


def _cache_path(doc: ExtractedDoc, task: Task, client: LLMClient, pages: list[int]) -> Path:
    """Cache file name: changes if the file, task, model or page selection changes."""
    pages_key = hashlib.sha1(",".join(map(str, pages)).encode()).hexdigest()[:10]
    key = f"{doc.file_hash[:16]}_{task.name}_{client.config.provider}_{client.config.model}_{pages_key}"
    return LLM_CACHE_DIR / f"{key}.json"


def run_task(task: Task, doc: ExtractedDoc, pdf_bytes: bytes, hits: dict[str, SectionHit],
             client: LLMClient, use_cache: bool = True) -> TaskResult:
    """Run one extraction task end to end (pages -> LLM -> schema -> grounding)."""
    pages = pages_for_task(task, hits)
    if not pages or (task.include_cover and pages == [1, 2]):
        return TaskResult(name=task.name, label=task.label, ok=False,
                          error="Section not found. Set its page range by hand, then run again.")
    cache = _cache_path(doc, task, client, pages)
    if use_cache and cache.exists():
        cached = TaskResult.model_validate_json(cache.read_text(encoding="utf-8"))
        cached.from_cache = True
        return cached

    add_layout_text(doc, pdf_bytes, pages)
    context = doc.text_of(pages, max_chars=CHAR_BUDGET)
    system = SYSTEM_PROMPT.format(task=task.name, extra=task.instructions)
    try:
        parsed = client.complete_json(system, f"RHP pages:\n\n{context}", task.schema)
    except LLMError as exc:
        return TaskResult(name=task.name, label=task.label, ok=False, error=str(exc), pages_sent=pages)
    result = TaskResult(name=task.name, label=task.label, ok=True, data=parsed.model_dump(),
                        pages_sent=pages, grounding=ground_model(task.name, parsed, doc, pages))
    if use_cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(result.model_dump_json(), encoding="utf-8")
    return result


def run_all(doc: ExtractedDoc, pdf_bytes: bytes, hits: dict[str, SectionHit], client: LLMClient,
            progress: ProgressFn | None = None, use_cache: bool = True) -> dict[str, TaskResult]:
    """Run every task in order, reporting progress after each one."""
    results: dict[str, TaskResult] = {}
    for i, task in enumerate(TASKS):
        if progress:
            progress(i, len(TASKS), task.label)
        results[task.name] = run_task(task, doc, pdf_bytes, hits, client, use_cache)
    if progress:
        progress(len(TASKS), len(TASKS), "Done")
    return results


# --------------------------------------------------------------------------------------
# From LLM results to clean numbers (Rs crore)
# --------------------------------------------------------------------------------------

_TO_CRORE = {"crore": 1.0, "million": 0.1, "lakh": 0.01, "rupees": 1 / CRORE}


def to_crore(item: Sourced | dict | None) -> float | None:
    """Convert a sourced money figure to Rs crore (1 crore = 10 million = 100 lakh)."""
    if item is None:
        return None
    s = item if isinstance(item, Sourced) else Sourced(**item)
    if s.value is None:
        return None
    factor = _TO_CRORE.get(s.unit or "crore")
    return None if factor is None else round(s.value * factor, 4)


def _get(results: dict[str, TaskResult], task: str, schema: type[BaseModel]) -> BaseModel | None:
    """The parsed model for a task, or None if the task failed."""
    r = results.get(task)
    return schema.model_validate(r.data) if r and r.ok and r.data else None


def to_note_inputs(results: dict[str, TaskResult], manual: IssueInputs) -> NoteInputs:
    """Combine LLM results with the user's manual fields into clean inputs for the maths."""
    objects = _get(results, "objects", ObjectsOut)
    capital = _get(results, "capital", CapitalOut)
    fin = _get(results, "financials", FinancialsOut)
    basis = _get(results, "basis", BasisOut)
    lit = _get(results, "litigation", LitigationOut)
    rpt = _get(results, "rpt", RptOut)

    issue = manual.model_copy()
    if objects:
        fresh = to_crore(objects.fresh_issue_amount) or to_crore(objects.gross_fresh_proceeds)
        ofs = to_crore(objects.ofs_amount)
        if ofs is None and objects.ofs_shares.value and manual.price_band_high:
            ofs = round(objects.ofs_shares.value * manual.price_band_high / CRORE, 4)  # shares x upper band
        issue.fresh_issue_cr = manual.fresh_issue_cr or fresh
        issue.ofs_cr = manual.ofs_cr if manual.ofs_cr is not None else ofs
        issue.gcp_cr = manual.gcp_cr or to_crore(objects.general_corporate_purposes)
    if capital and not manual.post_issue_shares:
        issue.post_issue_shares = capital.post_issue_shares.value or post_issue_shares_from_fresh(
            capital.pre_issue_shares.value, issue.fresh_issue_cr, manual.price_band_high)

    years = []
    if fin:
        for y in fin.years:
            years.append(YearFinancials(
                year=y.year, revenue=to_crore(y.revenue), ebitda=to_crore(y.ebitda), pat=to_crore(y.pat),
                operating_cash_flow=to_crore(y.operating_cash_flow),
                total_borrowings=to_crore(y.total_borrowings), net_worth=to_crore(y.net_worth)))
    return NoteInputs(
        issue=issue,
        financials=years,
        peers=[PeerPE(name=p.name, pe=p.pe.value) for p in basis.peers] if basis else [],
        promoter_pledged_shares=capital.promoter_pledged_shares.value if capital else None,
        litigation_cr=to_crore(lit.total_amount) if lit else None,
        rpt_cr=to_crore(rpt.latest_year_total) if rpt else None,
    )


# --------------------------------------------------------------------------------------
# Offline demo: canned LLM answers for the SAMPLE RHP (no API key needed)
# --------------------------------------------------------------------------------------


def sample_fake_reply(system: str, user: str) -> str:
    """Pretend-LLM that answers from the sample RHP's known facts.

    One figure is deliberately wrong (FY2024 EBITDA 118.80 instead of 118.30) so the demo
    shows the grounding check catching a hallucinated number.
    """
    from ipodesk.sample_data import SAMPLE_RHP_FACTS as F
    from ipodesk.sample_data import sample_rhp_expected_pages

    pg = sample_rhp_expected_pages()
    task = system.split("TASK:", 1)[1].split()[0] if "TASK:" in system else ""

    def s(value: float | None, unit: str, page: int, quote: str = "") -> dict:
        return {"value": value, "unit": unit, "page": page, "quote": quote}

    if task == "business":
        out = {"company_name": F["company"], "snapshot": [
            "Makes and sells packaged snacks, ready-to-eat meals and spice blends under the 'Aarna' brand.",
            "Sells through 2,40,000 retail outlets in 18 states and on e-commerce platforms.",
            "Operates two automated plants at Nashik and Indore."],
            "strengths": [{"text": t, "page": pg["business"]} for t in [
                "An established brand in western and central India.", "Two automated plants at Nashik and Indore.",
                "A wide distribution network of 1,150 distributors.", "Revenue growth of 22.80% in FY2026."]]}
    elif task == "risks":
        out = {"top_risks": [{"text": t, "page": pg["risk_factors"]} for t in [
            "64% of revenue comes from the top three product categories.",
            "Operating cash flow was negative at Rs (12.60) crore in FY2025.",
            "The Nashik and Indore plants account for 78% of production.",
            "Prices of edible oil and wheat, the main raw materials, are volatile.",
            "The company will not receive any proceeds from the Rs 800.00 crore Offer for Sale."]]}
    elif task == "objects":
        p = pg["objects"]
        out = {"fresh_issue_amount": s(200.00, "crore", 1, "Fresh Issue of Rs 200.00 crore"),
               "ofs_amount": s(800.00, "crore", 1, "Offer for Sale of Rs 800.00 crore"),
               "ofs_shares": s(None, "shares", 1), "gross_fresh_proceeds": s(200.00, "crore", p),
               "general_corporate_purposes": s(45.00, "crore", p),
               "uses": [{"purpose": k, "amount": s(v, "crore", p)} for k, v in F["objects"].items()]}
    elif task == "capital":
        p = pg["capital_structure"]
        out = {"pre_issue_shares": s(F["pre_issue_shares"], "shares", p),
               "post_issue_shares": s(F["post_issue_shares"], "shares", p),
               "face_value": s(2, "rupees", 1), "promoter_holding_pre_pct": s(72.40, "percent", p),
               "promoter_pledged_shares": s(0, "shares", p, "None of the Equity Shares held by our Promoters are pledged")}
    elif task == "financials":
        p, pc = pg["financial_summary"], pg["restated_financials"]
        ebitda = list(F["ebitda"])
        ebitda[0] = 118.80  # deliberate hallucination for the demo
        out = {"years": [
            {"year": y, "revenue": s(F["revenue"][i], "crore", p), "ebitda": s(ebitda[i], "crore", p),
             "pat": s(F["pat"][i], "crore", p), "operating_cash_flow": s(F["operating_cash_flow"][i], "crore", pc),
             "total_borrowings": s(F["total_borrowings"][i], "crore", p), "net_worth": s(F["net_worth"][i], "crore", p)}
            for i, y in enumerate(F["years"])]}
    elif task == "basis":
        p = pg["basis_for_price"]
        out = {"peers": [{"name": k, "pe": s(v, "times", p)} for k, v in F["peers_pe"].items()],
               "issuer_eps": s(11.21, "rupees", p)}
    elif task == "litigation":
        p = pg["litigation"]
        out = {"total_amount": s(18.05, "crore", p), "notable": [
            {"text": "Direct and indirect tax proceedings involve Rs 14.20 crore.", "page": p},
            {"text": "One criminal proceeding against a Promoter; amount not quantifiable.", "page": p}]}
    elif task == "rpt":
        out = {"latest_year_label": "FY2026", "latest_year_total": s(26.10, "crore", pg["related_party"])}
    else:
        out = {}
    return json.dumps(out)
