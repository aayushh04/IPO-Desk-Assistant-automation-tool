"""Data shapes (pydantic models) used across the app.

Two families:
1. LLM output schemas: what the model must return, as STRICT JSON. Every number is a
   `Sourced` value: the number exactly as printed, its unit, the page it came from and a
   short quote. That's what makes the grounding check (grounding.py) possible.
2. Clean inputs for the maths: plain numbers in Rs crore, after unit conversion and human
   review. valuation.py and red_flags.py only ever see these.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

# ======================================================================================
# 1. LLM output schemas
# ======================================================================================

Unit = Literal["crore", "million", "lakh", "rupees", "shares", "percent", "times"]


class Sourced(BaseModel):
    """One number taken from the RHP, with where it came from."""

    value: float | None = Field(
        None, description="The number exactly as printed (no commas). Negative if printed in brackets. null if not stated."
    )
    unit: Unit | None = Field(None, description="Unit as printed: crore, million, lakh, rupees, shares, percent or times.")
    page: int | None = Field(None, description="PDF page number (from the '=== PAGE n ===' marker) where the number appears.")
    quote: str = Field("", description="Short verbatim snippet (max 20 words) from that page containing the number.")


class SourcedText(BaseModel):
    """A short factual statement taken from the RHP, with its page."""

    text: str = Field(description="One neutral, factual sentence. No opinions or advice.")
    page: int | None = Field(None, description="PDF page number it came from.")


class BusinessOut(BaseModel):
    """From 'Our Business' (and 'Industry Overview')."""

    company_name: str = ""
    snapshot: list[str] = Field(default_factory=list, description="Exactly 3 short factual lines on what the company does.")
    strengths: list[SourcedText] = Field(default_factory=list, description="Up to 6 strengths as stated by the company in the RHP.")


class RisksOut(BaseModel):
    """From 'Risk Factors'."""

    top_risks: list[SourcedText] = Field(default_factory=list, description="The first 5 risk factors, summarised in one sentence each.")


class UseItem(BaseModel):
    """One line of 'use of proceeds'."""

    purpose: str
    amount: Sourced


class ObjectsOut(BaseModel):
    """From 'Objects of the Offer' (and the cover page if included)."""

    fresh_issue_amount: Sourced = Field(default_factory=Sourced, description="Size of the fresh issue in money terms.")
    ofs_amount: Sourced = Field(default_factory=Sourced, description="Offer for Sale size in money terms, if stated.")
    ofs_shares: Sourced = Field(default_factory=Sourced, description="Offer for Sale size in number of shares, if stated.")
    gross_fresh_proceeds: Sourced = Field(default_factory=Sourced, description="Gross proceeds of the fresh issue.")
    general_corporate_purposes: Sourced = Field(default_factory=Sourced, description="Amount for general corporate purposes.")
    uses: list[UseItem] = Field(default_factory=list, description="Each object of the fresh issue with its amount.")


class CapitalOut(BaseModel):
    """From 'Capital Structure'."""

    pre_issue_shares: Sourced = Field(default_factory=Sourced)
    post_issue_shares: Sourced = Field(default_factory=Sourced, description="null if printed as [*] or a blank.")
    face_value: Sourced = Field(default_factory=Sourced)
    promoter_holding_pre_pct: Sourced = Field(default_factory=Sourced)
    promoter_pledged_shares: Sourced = Field(
        default_factory=Sourced, description="Number of promoter shares pledged. 0 if the RHP says none are pledged (quote that sentence)."
    )


class YearRow(BaseModel):
    """One full financial year of figures."""

    year: str = Field(description="e.g. FY2026 for the year ended March 31, 2026.")
    revenue: Sourced = Field(default_factory=Sourced, description="Revenue from operations.")
    ebitda: Sourced = Field(default_factory=Sourced)
    pat: Sourced = Field(default_factory=Sourced, description="Restated profit after tax for the year.")
    operating_cash_flow: Sourced = Field(default_factory=Sourced, description="Net cash from/(used in) operating activities.")
    total_borrowings: Sourced = Field(default_factory=Sourced)
    net_worth: Sourced = Field(default_factory=Sourced, description="Net worth / total equity.")


class FinancialsOut(BaseModel):
    """From 'Summary of Financial Information' / 'Restated Financial Information'."""

    years: list[YearRow] = Field(default_factory=list, description="The 3 latest FULL financial years, oldest first. Skip part-year (stub) periods.")


class PeerRow(BaseModel):
    """One listed peer from the 'Basis for Offer Price' comparison table."""

    name: str
    pe: Sourced = Field(default_factory=Sourced)


class BasisOut(BaseModel):
    """From 'Basis for Offer Price'."""

    peers: list[PeerRow] = Field(default_factory=list, description="Listed peers (not the issuer) with their P/E.")
    issuer_eps: Sourced = Field(default_factory=Sourced, description="Issuer's basic EPS for the latest full year.")


class LitigationOut(BaseModel):
    """From 'Outstanding Litigation'."""

    total_amount: Sourced = Field(default_factory=Sourced, description="Total quantifiable amount involved, all cases.")
    notable: list[SourcedText] = Field(default_factory=list, description="Up to 4 notable matters, one neutral sentence each.")


class RptOut(BaseModel):
    """From 'Related Party Transactions'."""

    latest_year_label: str = ""
    latest_year_total: Sourced = Field(default_factory=Sourced, description="Total related-party transactions in the latest full year.")


# ======================================================================================
# 2. Clean inputs for the maths (Rs crore unless stated)
# ======================================================================================


class YearFinancials(BaseModel):
    """One year's figures in Rs crore."""

    year: str
    revenue: float | None = None
    ebitda: float | None = None
    pat: float | None = None
    operating_cash_flow: float | None = None
    total_borrowings: float | None = None
    net_worth: float | None = None


class IssueInputs(BaseModel):
    """Issue details. Price band, lot and dates are typed in by the user (often not in the RHP)."""

    price_band_low: float | None = None
    price_band_high: float | None = None
    lot_size: int | None = None
    open_date: dt.date | None = None
    close_date: dt.date | None = None
    fresh_issue_cr: float | None = None
    ofs_cr: float | None = None
    post_issue_shares: float | None = None
    gcp_cr: float | None = None


class PeerPE(BaseModel):
    """A listed peer's P/E multiple."""

    name: str
    pe: float | None = None


class NoteInputs(BaseModel):
    """Everything the valuation and red-flag engines need."""

    issue: IssueInputs = Field(default_factory=IssueInputs)
    financials: list[YearFinancials] = Field(default_factory=list)  # oldest first
    peers: list[PeerPE] = Field(default_factory=list)
    promoter_pledged_shares: float | None = None
    litigation_cr: float | None = None
    rpt_cr: float | None = None
