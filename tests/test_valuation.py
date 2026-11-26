"""Valuation tests with known answers."""
import pytest

from ipodesk import valuation as v
from ipodesk.sample_data import SAMPLE_RHP_FACTS as F
from ipodesk.schemas import IssueInputs, NoteInputs, PeerPE, YearFinancials


def test_known_answer_eps_pe_market_cap() -> None:
    # Upper band Rs 315, 10 crore post-issue shares, PAT Rs 105 crore
    shares = 10 * v.CRORE
    eps = v.eps(105, shares)
    assert eps == pytest.approx(10.50)
    assert v.pe_ratio(315, eps) == pytest.approx(30.0)
    assert v.market_cap_cr(315, shares) == pytest.approx(3150.0)


def test_fresh_ofs_split() -> None:
    assert v.fresh_ofs_split(200, 800) == pytest.approx((20.0, 80.0))
    assert v.fresh_ofs_split(500, None) == pytest.approx((100.0, 0.0))
    assert v.fresh_ofs_split(None, None) == (None, None)


def test_growth_margin_and_leverage() -> None:
    assert v.growth_pct(1240.60, 1010.25) == pytest.approx(22.80, abs=0.01)
    assert v.growth_pct(10, -5) is None  # growth from a loss is not meaningful
    assert v.margin_pct(189.90, 1240.60) == pytest.approx(15.31, abs=0.01)
    assert v.debt_to_equity(248, 707) == pytest.approx(0.351, abs=0.001)
    assert v.debt_to_equity(100, 0) is None


def test_negative_eps_gives_no_pe() -> None:
    assert v.pe_ratio(315, -2.0) is None


def test_peer_median_ignores_loss_makers() -> None:
    assert v.peer_median([28.4, 22.1, 19.6, None, -5]) == pytest.approx(22.1)


def test_compute_metrics_on_sample_rhp() -> None:
    years = [YearFinancials(year=y, revenue=r, ebitda=e, pat=p, operating_cash_flow=o,
                            total_borrowings=d, net_worth=n)
             for y, r, e, p, o, d, n in zip(F["years"], F["revenue"], F["ebitda"], F["pat"],
                                             F["operating_cash_flow"], F["total_borrowings"], F["net_worth"])]
    inputs = NoteInputs(
        issue=IssueInputs(price_band_low=300, price_band_high=315, lot_size=47,
                          fresh_issue_cr=200, ofs_cr=800, post_issue_shares=F["post_issue_shares"]),
        financials=years,
        peers=[PeerPE(name=k, pe=x) for k, x in F["peers_pe"].items()],
    )
    m = v.compute_metrics(inputs)
    assert m.issue_size_cr == 1000 and m.ofs_pct == pytest.approx(80.0)
    assert m.pe == pytest.approx(30.0) and m.market_cap_cr == pytest.approx(3150.0)
    assert m.min_investment == 315 * 47
    assert m.yearly[0].revenue_growth_pct is None
    assert m.yearly[-1].pat_growth_pct == pytest.approx(25.90, abs=0.01)


def test_post_issue_shares_from_fresh_issue() -> None:
    assert v.post_issue_shares_from_fresh(F["pre_issue_shares"], 200, 315) == pytest.approx(F["post_issue_shares"], abs=1)
