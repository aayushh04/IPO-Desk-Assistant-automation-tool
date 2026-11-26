"""Valuation maths, done in Python (never by the LLM, which can get arithmetic wrong).

Key formulas (all money in Rs crore unless stated; 1 crore = 10,000,000 = 1e7):
- Market cap at the upper band = upper band price x post-issue shares
- EPS (Rs per share)          = latest full-year PAT / post-issue shares
- P/E at the upper band        = upper band price / EPS
- Fresh issue % / OFS %        = each part / (fresh + OFS)
- Growth %                     = (this year / last year - 1) x 100
- Margin %                     = profit measure / revenue x 100
- Debt-to-equity               = total borrowings / net worth

Why post-issue shares for EPS? After listing, profit is shared by ALL shares, including the
new ones from the fresh issue. Using post-issue shares gives the "fully diluted at the
upper band" P/E that brokers usually quote. The RHP's own EPS uses pre-issue shares, so it
looks a bit higher.
"""
from __future__ import annotations

import statistics

from pydantic import BaseModel

from ipodesk.schemas import NoteInputs, YearFinancials

CRORE: float = 1e7


class YearRatios(BaseModel):
    """Margins and growth for one year."""

    year: str
    revenue_growth_pct: float | None = None
    pat_growth_pct: float | None = None
    ebitda_margin_pct: float | None = None
    pat_margin_pct: float | None = None
    debt_to_equity: float | None = None


class Metrics(BaseModel):
    """All computed numbers for the note. None means 'not enough data'."""

    issue_size_cr: float | None = None
    fresh_pct: float | None = None
    ofs_pct: float | None = None
    min_investment: float | None = None
    market_cap_cr: float | None = None
    eps: float | None = None
    pe: float | None = None
    peer_median_pe: float | None = None
    pe_vs_peer_median: float | None = None
    yearly: list[YearRatios] = []


def _div(a: float | None, b: float | None) -> float | None:
    """a / b, or None if either is missing or b is zero."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def market_cap_cr(upper_price: float | None, post_issue_shares: float | None) -> float | None:
    """Market cap in Rs crore = price x shares / 1 crore."""
    if upper_price is None or post_issue_shares is None:
        return None
    return upper_price * post_issue_shares / CRORE


def eps(pat_cr: float | None, post_issue_shares: float | None) -> float | None:
    """Earnings per share in Rs = PAT (converted from crore to Rs) / number of shares."""
    if pat_cr is None:
        return None
    return _div(pat_cr * CRORE, post_issue_shares)


def pe_ratio(price: float | None, eps_value: float | None) -> float | None:
    """Price-to-earnings multiple. None when EPS is zero/negative (P/E isn't meaningful)."""
    if eps_value is None or eps_value <= 0:
        return None
    return _div(price, eps_value)


def fresh_ofs_split(fresh_cr: float | None, ofs_cr: float | None) -> tuple[float | None, float | None]:
    """Return (fresh %, OFS %) of the total issue. A missing part counts as 0 if the other is known."""
    if fresh_cr is None and ofs_cr is None:
        return None, None
    fresh, ofs = fresh_cr or 0.0, ofs_cr or 0.0
    total = fresh + ofs
    if total == 0:
        return None, None
    return fresh / total * 100, ofs / total * 100


def growth_pct(current: float | None, previous: float | None) -> float | None:
    """Year-on-year growth %. None if last year was zero or negative (growth % misleads then)."""
    if current is None or previous is None or previous <= 0:
        return None
    return (current / previous - 1) * 100


def margin_pct(part: float | None, revenue: float | None) -> float | None:
    """part / revenue as a %."""
    value = _div(part, revenue)
    return None if value is None else value * 100


def debt_to_equity(debt: float | None, equity: float | None) -> float | None:
    """Total borrowings / net worth. None if net worth is zero or negative."""
    if equity is None or equity <= 0:
        return None
    return _div(debt, equity)


def peer_median(pes: list[float | None]) -> float | None:
    """Median P/E of peers, ignoring blanks and loss-making (zero/negative) peers."""
    valid = [p for p in pes if p is not None and p > 0]
    return statistics.median(valid) if valid else None


def yearly_ratios(years: list[YearFinancials]) -> list[YearRatios]:
    """Margins, growth and debt-to-equity for each year (growth needs the year before)."""
    out = []
    for i, y in enumerate(years):
        prev = years[i - 1] if i > 0 else None
        out.append(
            YearRatios(
                year=y.year,
                revenue_growth_pct=growth_pct(y.revenue, prev.revenue) if prev else None,
                pat_growth_pct=growth_pct(y.pat, prev.pat) if prev else None,
                ebitda_margin_pct=margin_pct(y.ebitda, y.revenue),
                pat_margin_pct=margin_pct(y.pat, y.revenue),
                debt_to_equity=debt_to_equity(y.total_borrowings, y.net_worth),
            )
        )
    return out


def compute_metrics(inputs: NoteInputs) -> Metrics:
    """Compute every number shown in the note's Issue and Valuation sections."""
    issue = inputs.issue
    latest = inputs.financials[-1] if inputs.financials else None
    fresh_pct, ofs_pct = fresh_ofs_split(issue.fresh_issue_cr, issue.ofs_cr)
    size = None
    if issue.fresh_issue_cr is not None or issue.ofs_cr is not None:
        size = (issue.fresh_issue_cr or 0) + (issue.ofs_cr or 0)
    eps_value = eps(latest.pat if latest else None, issue.post_issue_shares)
    pe = pe_ratio(issue.price_band_high, eps_value)
    median = peer_median([p.pe for p in inputs.peers])
    return Metrics(
        issue_size_cr=size,
        fresh_pct=fresh_pct,
        ofs_pct=ofs_pct,
        min_investment=(issue.price_band_high * issue.lot_size)
        if issue.price_band_high is not None and issue.lot_size
        else None,
        market_cap_cr=market_cap_cr(issue.price_band_high, issue.post_issue_shares),
        eps=eps_value,
        pe=pe,
        peer_median_pe=median,
        pe_vs_peer_median=_div(pe, median),
        yearly=yearly_ratios(inputs.financials),
    )


def post_issue_shares_from_fresh(pre_issue_shares: float | None, fresh_issue_cr: float | None,
                                 upper_price: float | None) -> float | None:
    """Estimate post-issue shares = pre-issue shares + new shares (fresh issue / upper price).

    RHPs often print post-issue shares as '[*]' because it depends on the final price.
    """
    if pre_issue_shares is None or upper_price in (None, 0):
        return None
    new_shares = (fresh_issue_cr or 0) * CRORE / upper_price
    return pre_issue_shares + round(new_shares)
