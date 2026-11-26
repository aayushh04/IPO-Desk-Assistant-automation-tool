"""The IPO note draft: built from LLM results, edited by a person, then exported.

Human in the loop: the draft is only a starting point. The review screen lets a person
edit every field; metrics and red flags are recomputed from the EDITED numbers; and export
is blocked until the reviewer has (a) entered their name, (b) confirmed any figures the
grounding check couldn't find, and (c) cleared the compliance word scan.
"""
from __future__ import annotations

import datetime as dt
import re

from pydantic import BaseModel, Field

from ipodesk.config import disclaimer, get_settings
from ipodesk.extraction import TASK_BY_NAME, TaskResult, to_crore, to_note_inputs
from ipodesk.grounding import GroundingResult
from ipodesk.red_flags import RedFlag, run_checks
from ipodesk.schemas import BusinessOut, IssueInputs, LitigationOut, NoteInputs, ObjectsOut, PeerPE, RisksOut, YearFinancials
from ipodesk.sections import SectionHit
from ipodesk.valuation import Metrics, compute_metrics


class UseRow(BaseModel):
    """One use-of-proceeds line in Rs crore."""

    purpose: str
    amount_cr: float | None = None
    page: int | None = None


class NoteDraft(BaseModel):
    """Everything on the note that a reviewer can edit."""

    company: str = ""
    snapshot: str = ""
    issue: IssueInputs = Field(default_factory=IssueInputs)
    uses: list[UseRow] = []
    financials: list[YearFinancials] = []
    peers: list[PeerPE] = []
    strengths: list[str] = []
    risks: list[str] = []
    litigation_notes: list[str] = []
    promoter_pledged_shares: float | None = None
    litigation_cr: float | None = None
    rpt_cr: float | None = None
    sources: dict[str, str] = {}  # section label -> page range
    grounding: list[GroundingResult] = []
    reviewer: str = ""
    prepared_on: dt.date = Field(default_factory=dt.date.today)

    def to_inputs(self) -> NoteInputs:
        """Clean inputs for the maths, taken from the (possibly edited) draft."""
        return NoteInputs(issue=self.issue, financials=self.financials, peers=self.peers,
                          promoter_pledged_shares=self.promoter_pledged_shares,
                          litigation_cr=self.litigation_cr, rpt_cr=self.rpt_cr)

    def unverified(self) -> list[GroundingResult]:
        """Figures the grounding check could not find in the source text."""
        return [g for g in self.grounding if g.status == "verify manually"]


def _with_page(text: str, page: int | None) -> str:
    """Append a page reference, e.g. 'Volatile raw material prices (p. 36)'."""
    return f"{text} (p. {page})" if page else text


def build_draft(results: dict[str, TaskResult], manual: IssueInputs, hits: dict[str, SectionHit],
                company_hint: str = "") -> NoteDraft:
    """Turn LLM results + manual fields into an editable draft."""
    inputs = to_note_inputs(results, manual)

    def get(name: str, schema: type[BaseModel]) -> BaseModel | None:
        r = results.get(name)
        return schema.model_validate(r.data) if r and r.ok and r.data else None

    business: BusinessOut | None = get("business", BusinessOut)  # type: ignore[assignment]
    risks: RisksOut | None = get("risks", RisksOut)  # type: ignore[assignment]
    objects: ObjectsOut | None = get("objects", ObjectsOut)  # type: ignore[assignment]
    lit: LitigationOut | None = get("litigation", LitigationOut)  # type: ignore[assignment]

    sources = {h.label: f"pp. {h.start_page}-{h.end_page}" for h in hits.values() if h.found}
    grounding = [g for r in results.values() for g in r.grounding]
    return NoteDraft(
        company=(business.company_name if business and business.company_name else company_hint),
        snapshot="\n".join(business.snapshot[:3]) if business else "",
        issue=inputs.issue,
        uses=[UseRow(purpose=u.purpose, amount_cr=to_crore(u.amount), page=u.amount.page) for u in objects.uses]
        if objects else [],
        financials=inputs.financials,
        peers=inputs.peers,
        strengths=[_with_page(s.text, s.page) for s in business.strengths] if business else [],
        risks=[_with_page(r.text, r.page) for r in risks.top_risks[:5]] if risks else [],
        litigation_notes=[_with_page(n.text, n.page) for n in lit.notable] if lit else [],
        promoter_pledged_shares=inputs.promoter_pledged_shares,
        litigation_cr=inputs.litigation_cr,
        rpt_cr=inputs.rpt_cr,
        sources=sources,
        grounding=grounding,
    )


def evaluate(draft: NoteDraft) -> tuple[Metrics, list[RedFlag]]:
    """Recompute metrics and red flags from the draft's current (edited) numbers."""
    inputs = draft.to_inputs()
    metrics = compute_metrics(inputs)
    return metrics, run_checks(inputs, metrics)


def compliance_issues(draft: NoteDraft) -> list[str]:
    """Find advice-like words (subscribe, avoid, buy, GMP, ...) in the note's free text.

    Words are matched as whole words, so 'subscription' or 'selling shareholders' don't trip it.
    The fixed disclaimer is not scanned.
    """
    texts = [draft.snapshot, *draft.strengths, *draft.risks, *draft.litigation_notes, *(u.purpose for u in draft.uses)]
    blob = "\n".join(texts)
    found = []
    for phrase in get_settings()["compliance"]["banned_phrases"]:
        if re.search(rf"\b{re.escape(phrase)}\b", blob, flags=re.IGNORECASE):
            found.append(phrase)
    return found


def export_blockers(draft: NoteDraft, figures_confirmed: bool, wording_confirmed: bool) -> list[str]:
    """Reasons export is not allowed yet (empty list = ready to export)."""
    blockers = []
    if not draft.reviewer.strip():
        blockers.append("Enter the reviewer's name.")
    if draft.unverified() and not figures_confirmed:
        blockers.append(f"Confirm the {len(draft.unverified())} figure(s) marked 'verify manually'.")
    if compliance_issues(draft) and not wording_confirmed:
        blockers.append("Remove advice-like words, or confirm they are used factually.")
    if not draft.company.strip():
        blockers.append("Enter the company name.")
    return blockers


def grounding_index(draft: NoteDraft) -> dict[str, GroundingResult]:
    """Look up a figure's grounding result by 'task:field', e.g. 'financials:years[FY2024].ebitda'."""
    return {f"{g.task}:{g.field}": g for g in draft.grounding}


def open_queries(draft: NoteDraft) -> list[tuple[str, GroundingResult]]:
    """Numbered queries (Q1, Q2, ...) for every figure the grounding check could not find."""
    return [(f"Q{i}", g) for i, g in enumerate(draft.unverified(), start=1)]


FIELD_LABELS: dict[str, str] = {
    "revenue": "revenue", "ebitda": "EBITDA", "pat": "profit after tax", "operating_cash_flow": "operating cash flow",
    "total_borrowings": "total borrowings", "net_worth": "net worth", "fresh_issue_amount": "fresh issue size",
    "ofs_amount": "offer for sale size", "ofs_shares": "offer for sale shares", "gross_fresh_proceeds": "gross proceeds",
    "general_corporate_purposes": "general corporate purposes", "pre_issue_shares": "pre-issue shares",
    "post_issue_shares": "post-issue shares", "promoter_pledged_shares": "promoter shares pledged",
    "total_amount": "litigation total", "latest_year_total": "related-party transactions", "pe": "P/E",
}


def query_text(g: GroundingResult) -> str:
    """Plain-English description of one open query, e.g. 'FY2024 EBITDA 118.80 was not found on RHP page 5.'"""
    page = f"RHP page {g.cited_page}" if g.cited_page else "the pages sent"
    field = g.field.split(" (in text)")[0]
    if "." in field:  # e.g. years[FY2024].ebitda -> "FY2024 EBITDA"
        last = field.rsplit(".", 1)[-1]
        label = FIELD_LABELS.get(last, last.replace("_", " "))
        scope = field.split("[", 1)[1].split("]", 1)[0] + " " if "[" in field else ""
    elif "[" not in field:  # e.g. fresh_issue_amount -> "fresh issue size"
        label, scope = FIELD_LABELS.get(field, field.replace("_", " ")), ""
    else:  # e.g. top_risks[0] -> "a figure in top risks item 1"
        name, _, idx = field.partition("[")
        item = f" item {int(idx.rstrip(']')) + 1}" if idx.rstrip("]").isdigit() else ""
        label, scope = f"a figure in {name.replace('_', ' ')}{item}:", ""
    where = " (in a summary sentence)" if "(in text)" in g.field else ""
    text = f"{scope}{label} {g.value:,.2f}{where} was not found on {page}."
    return text[0].upper() + text[1:]


def note_disclaimer() -> str:
    """The compliance line printed on every note."""
    return disclaimer()


def task_label(name: str) -> str:
    """Human label of an extraction task."""
    return TASK_BY_NAME[name].label if name in TASK_BY_NAME else name
