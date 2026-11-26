"""Grounding check tests."""
from ipodesk.grounding import ground_model, numbers_in_text, value_in_text
from ipodesk.pdf_extract import ExtractedDoc
from ipodesk.schemas import RisksOut, Sourced, SourcedText, YearRow, FinancialsOut

DOC = ExtractedDoc("x", [
    "Revenue from operations  820.40   1,010.25   1,240.60\nNet cash from operating activities (12.60)",
    "Equity shares after the Offer: 10,00,00,000. Promoter holding 72.40%.",
])


def test_number_parsing_handles_indian_commas_and_brackets() -> None:
    nums = numbers_in_text(DOC.page(1) + DOC.page(2))
    assert 1240.60 in nums and 12.60 in nums and 100000000 in nums
    assert value_in_text(-12.6, DOC.page(1))      # bracketed negative
    assert value_in_text(72.4, DOC.page(2))        # 72.40 printed


def test_llm_figure_not_in_source_is_flagged_verify_manually() -> None:
    model = FinancialsOut(years=[YearRow(year="FY2026", revenue=Sourced(value=1300.55, unit="crore", page=1))])
    [result] = ground_model("financials", model, DOC, [1, 2])
    assert result.status == "verify manually"
    assert "Verify manually" in result.message


def test_correct_figure_is_ok_and_wrong_page_is_corrected() -> None:
    model = FinancialsOut(years=[YearRow(year="FY2026", revenue=Sourced(value=1240.60, unit="crore", page=1),
                                         net_worth=Sourced(value=72.40, unit="crore", page=1))])
    by_field = {r.field.split(".")[-1]: r for r in ground_model("financials", model, DOC, [1, 2])}
    assert by_field["revenue"].status == "ok"
    assert by_field["net_worth"].status == "page corrected" and by_field["net_worth"].found_on == [2]


def test_numbers_inside_sentences_are_checked() -> None:
    model = RisksOut(top_risks=[SourcedText(text="Revenue was 1,240.60 crore, up 99%.", page=1)])
    statuses = sorted(r.status for r in ground_model("risks", model, DOC, [1]))
    assert statuses == ["ok", "verify manually"]  # 1240.60 found, 99 not found
