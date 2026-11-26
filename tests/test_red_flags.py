"""Red-flag rule tests."""
from ipodesk.red_flags import run_checks
from ipodesk.schemas import IssueInputs, NoteInputs, PeerPE, YearFinancials
from ipodesk.valuation import compute_metrics


def _flags(inputs: NoteInputs) -> dict[str, str]:
    """Run checks and return {first word(s) of name: status}."""
    return {f.name: f.status for f in run_checks(inputs, compute_metrics(inputs))}


def _status(inputs: NoteInputs, starts: str) -> str:
    return next(s for n, s in _flags(inputs).items() if n.startswith(starts))


def test_ofs_800_of_1000_is_flagged() -> None:
    inputs = NoteInputs(issue=IssueInputs(fresh_issue_cr=200, ofs_cr=800))
    assert _status(inputs, "OFS over 50%") == "flag"


def test_ofs_400_of_1000_is_ok() -> None:
    assert _status(NoteInputs(issue=IssueInputs(fresh_issue_cr=600, ofs_cr=400)), "OFS over") == "ok"


def test_negative_ocf_two_of_three() -> None:
    yrs = [YearFinancials(year=f"FY{y}", operating_cash_flow=o) for y, o in [(24, -1), (25, 5), (26, -3)]]
    assert _status(NoteInputs(financials=yrs), "Negative operating") == "flag"
    yrs[0].operating_cash_flow = 2
    assert _status(NoteInputs(financials=yrs), "Negative operating") == "ok"


def test_pe_above_peer_median() -> None:
    inputs = NoteInputs(
        issue=IssueInputs(price_band_high=500, post_issue_shares=1e8),
        financials=[YearFinancials(year="FY26", pat=100)],  # EPS 10 -> P/E 50
        peers=[PeerPE(name="A", pe=20), PeerPE(name="B", pe=30), PeerPE(name="C", pe=25)],  # median 25
    )
    assert _status(inputs, "P/E above") == "flag"


def test_pledge_litigation_rpt_gcp() -> None:
    inputs = NoteInputs(
        issue=IssueInputs(fresh_issue_cr=200, gcp_cr=45),
        financials=[YearFinancials(year="FY26", revenue=1000, net_worth=500)],
        promoter_pledged_shares=1000, litigation_cr=80, rpt_cr=150,
    )
    f = _flags(inputs)
    assert _status(inputs, "Promoter shares pledged") == "flag"
    assert _status(inputs, "Litigation above") == "flag"        # 16% of net worth
    assert _status(inputs, "Related-party") == "flag"           # 15% of revenue
    assert _status(inputs, "General corporate") == "flag"       # 22.5%, within 5 pts of 25%
    assert len(f) == 7


def test_missing_data_is_no_data_not_ok() -> None:
    assert set(_flags(NoteInputs()).values()) == {"no data"}
