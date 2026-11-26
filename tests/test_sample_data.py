"""Tests that the synthetic data is well-formed, fake, and repeatable."""
import datetime as dt

import pymupdf as fitz

from ipodesk import sample_data as sd

TODAY = dt.date(2026, 11, 26)


def test_eight_ipos_within_30_days() -> None:
    ipos = sd.sample_ipos(TODAY)
    assert len(ipos) == 8
    offsets = [(d - TODAY).days for d in ipos["open_date"]]
    assert min(offsets) >= -30 and max(offsets) <= 31
    assert (ipos["close_date"] > ipos["open_date"]).all()
    assert all(d.weekday() < 5 for d in ipos["open_date"]) and all(d.weekday() < 5 for d in ipos["close_date"])


def test_subscription_for_three_ipos_and_total_is_weighted() -> None:
    sub = sd.sample_subscription(TODAY)
    assert sub["company"].nunique() == 3
    total = sub[sub["category"] == "total"].iloc[0]
    day = sub[(sub["company"] == total["company"]) & (sub["day"] == total["day"]) & (sub["category"] != "total")]
    assert total["shares_bid"] == day["shares_bid"].sum()
    assert total["subscription_x"] == round(total["shares_bid"] / total["shares_offered"], 2)


def test_500_bids_masked_and_consistent() -> None:
    bids = sd.sample_bids(500, TODAY)
    assert len(bids) == 500
    assert bids["pan_masked"].str.fullmatch(r"[A-Z]{2}\*{6}[0-9][A-Z]").all()
    retail = bids[bids["category"] == "retail"]
    assert (retail["amount"] <= sd.RETAIL_MAX_AMOUNT).all()
    # A bid without an approved mandate can never be allotted.
    assert not ((bids["mandate_status"] != "approved") & (bids["allotment_status"] == "allotted")).any()
    assert set(bids["allotment_status"]) <= {"pending", "allotted", "not_allotted", "rejected"}
    # Bids fall on working days, inside the issue window, never in the future.
    ipos = sd.sample_ipos(TODAY).set_index("company")
    merged = bids.join(ipos[["open_date", "close_date"]], on="company")
    assert (merged["bid_date"] >= merged["open_date"]).all()
    assert (merged["bid_date"] <= merged["close_date"]).all()
    assert (bids["bid_date"] <= TODAY).all() and all(d.weekday() < 5 for d in bids["bid_date"])


def test_data_is_repeatable() -> None:
    assert sd.sample_bids(50, TODAY).equals(sd.sample_bids(50, TODAY))


def test_sample_rhp_pdf_has_headings_on_expected_pages(tmp_path) -> None:
    pdf = sd.make_sample_rhp_pdf(tmp_path / "rhp.pdf")
    expected = sd.sample_rhp_expected_pages()
    with fitz.open(pdf) as doc:
        for key, page_no in expected.items():
            assert sd.SAMPLE_RHP_HEADINGS[key] in doc[page_no - 1].get_text(), key
