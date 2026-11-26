"""Rule-based red-flag checklist. Each rule is simple, explainable and has a stated reason.

A red flag is NOT a rating. It's a prompt for the reader to look closer, with the exact
rule and number shown. Thresholds live in config/settings.yaml so the desk can tune them.

Status of each check:
- "flag"    : the rule was triggered
- "ok"      : checked, not triggered
- "no data" : the input was missing, so we can't say (never silently treated as "ok")
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from ipodesk.config import get_settings
from ipodesk.schemas import NoteInputs
from ipodesk.valuation import Metrics

Status = Literal["flag", "ok", "no data"]


class RedFlag(BaseModel):
    """Result of one check."""

    name: str
    status: Status
    reason: str


def _fmt(x: float) -> str:
    """Format a number with 2 decimals and Indian-style thousands separators off (keep simple)."""
    return f"{x:,.2f}"


def check_ofs_share(inputs: NoteInputs, metrics: Metrics, t: dict[str, Any]) -> RedFlag:
    """Flag when the Offer for Sale is more than X% of the issue.

    Why it matters: OFS money goes to existing shareholders who are selling, not to the
    company. A mostly-OFS issue means the company itself raises little new capital.
    """
    name = f"OFS over {t['ofs_share_max_pct']}% of the issue"
    if metrics.ofs_pct is None:
        return RedFlag(name=name, status="no data", reason="Fresh issue / OFS sizes not available.")
    flagged = metrics.ofs_pct > t["ofs_share_max_pct"]
    reason = (f"OFS is Rs {_fmt(inputs.issue.ofs_cr or 0)} crore of a Rs {_fmt(metrics.issue_size_cr or 0)} crore "
              f"issue ({metrics.ofs_pct:.1f}%). OFS proceeds go to selling shareholders, not the company.")
    return RedFlag(name=name, status="flag" if flagged else "ok", reason=reason)


def check_negative_ocf(inputs: NoteInputs, t: dict[str, Any]) -> RedFlag:
    """Flag negative operating cash flow in N of the last 3 years.

    Why: profit on paper can differ from cash. Repeated negative operating cash flow can
    mean the business needs outside money (debt or equity) to keep running.
    """
    need = t["negative_ocf_years"]
    name = f"Negative operating cash flow in {need} of last 3 years"
    values = [y.operating_cash_flow for y in inputs.financials[-3:] if y.operating_cash_flow is not None]
    if len(values) < 3:
        return RedFlag(name=name, status="no data", reason="Operating cash flow not available for 3 years.")
    negatives = [y.year for y in inputs.financials[-3:] if (y.operating_cash_flow or 0) < 0]
    flagged = len(negatives) >= need
    detail = ", ".join(negatives) if negatives else "none"
    return RedFlag(name=name, status="flag" if flagged else "ok",
                   reason=f"Years with negative operating cash flow: {detail}.")


def check_pe_vs_peers(metrics: Metrics, t: dict[str, Any]) -> RedFlag:
    """Flag when P/E at the upper band is more than X times the peer median P/E."""
    limit = t["pe_vs_peer_median_max"]
    name = f"P/E above {limit}x the peer median"
    if metrics.pe is None or metrics.peer_median_pe is None:
        return RedFlag(name=name, status="no data", reason="Issuer P/E or peer P/E not available.")
    ratio = metrics.pe / metrics.peer_median_pe
    return RedFlag(name=name, status="flag" if ratio > limit else "ok",
                   reason=f"P/E at upper band {metrics.pe:.1f}x vs peer median {metrics.peer_median_pe:.1f}x "
                          f"({ratio:.2f} times the median; peers from the RHP's comparison table).")


def check_promoter_pledge(inputs: NoteInputs) -> RedFlag:
    """Flag when any promoter shares are pledged (used as loan collateral).

    Why: if the share price falls, lenders may sell pledged shares, adding selling pressure
    and possibly changing control.
    """
    name = "Promoter shares pledged"
    if inputs.promoter_pledged_shares is None:
        return RedFlag(name=name, status="no data", reason="Pledge information not available.")
    pledged = inputs.promoter_pledged_shares > 0
    reason = (f"{inputs.promoter_pledged_shares:,.0f} promoter shares are pledged." if pledged
              else "The RHP states no promoter shares are pledged.")
    return RedFlag(name=name, status="flag" if pledged else "ok", reason=reason)


def check_litigation(inputs: NoteInputs, t: dict[str, Any]) -> RedFlag:
    """Flag when outstanding litigation is more than X% of the latest net worth."""
    limit = t["litigation_pct_of_networth_max"]
    name = f"Litigation above {limit}% of net worth"
    net_worth = inputs.financials[-1].net_worth if inputs.financials else None
    if inputs.litigation_cr is None or not net_worth or net_worth <= 0:
        return RedFlag(name=name, status="no data", reason="Litigation amount or net worth not available.")
    pct = inputs.litigation_cr / net_worth * 100
    return RedFlag(name=name, status="flag" if pct > limit else "ok",
                   reason=f"Quantified litigation Rs {_fmt(inputs.litigation_cr)} crore = {pct:.1f}% of "
                          f"latest net worth Rs {_fmt(net_worth)} crore.")


def check_rpt(inputs: NoteInputs, t: dict[str, Any]) -> RedFlag:
    """Flag when related-party transactions are more than X% of revenue.

    Why: large dealings with promoter-linked entities can move profit in or out of the company.
    """
    limit = t["rpt_pct_of_revenue_max"]
    name = f"Related-party transactions above {limit}% of revenue"
    revenue = inputs.financials[-1].revenue if inputs.financials else None
    if inputs.rpt_cr is None or not revenue or revenue <= 0:
        return RedFlag(name=name, status="no data", reason="RPT total or revenue not available.")
    pct = inputs.rpt_cr / revenue * 100
    return RedFlag(name=name, status="flag" if pct > limit else "ok",
                   reason=f"RPT Rs {_fmt(inputs.rpt_cr)} crore = {pct:.1f}% of latest revenue.")


def check_gcp(inputs: NoteInputs, t: dict[str, Any]) -> RedFlag:
    """Flag when 'general corporate purposes' is close to (or over) its legal limit.

    SEBI ICDR caps general corporate purposes at 25% of the gross fresh-issue proceeds.
    A large GCP slice means a lot of the money has no specific stated use.
    """
    limit, margin = t["gcp_legal_limit_pct"], t["gcp_warning_margin_pct"]
    name = f"General corporate purposes near the {limit}% limit"
    fresh, gcp = inputs.issue.fresh_issue_cr, inputs.issue.gcp_cr
    if gcp is None or not fresh:
        return RedFlag(name=name, status="no data", reason="GCP amount or fresh issue size not available.")
    pct = gcp / fresh * 100
    if pct > limit:
        return RedFlag(name=name, status="flag",
                       reason=f"GCP is {pct:.1f}% of the fresh issue, above the {limit}% limit. Verify against the RHP.")
    flagged = pct >= limit - margin
    return RedFlag(name=name, status="flag" if flagged else "ok",
                   reason=f"GCP Rs {_fmt(gcp)} crore = {pct:.1f}% of the Rs {_fmt(fresh)} crore fresh issue "
                          f"(legal limit {limit}%).")


def run_checks(inputs: NoteInputs, metrics: Metrics, thresholds: dict[str, Any] | None = None) -> list[RedFlag]:
    """Run every red-flag rule and return the results in a fixed order."""
    t = thresholds or get_settings()["red_flags"]
    return [
        check_ofs_share(inputs, metrics, t),
        check_negative_ocf(inputs, t),
        check_pe_vs_peers(metrics, t),
        check_promoter_pledge(inputs),
        check_litigation(inputs, t),
        check_rpt(inputs, t),
        check_gcp(inputs, t),
    ]
