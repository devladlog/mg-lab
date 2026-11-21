from datetime import date
from decimal import Decimal

import pytest

from fixtures import analyze_result, sample
from invoice_intake.decide import decide, normalise_tax_id
from invoice_intake.fields import to_invoice
from invoice_intake.process import route_all


def test_mapping_types_and_confidence():
    inv = to_invoice(analyze_result(sample("01"), conf=0.97))
    assert inv.value("InvoiceTotal") == Decimal("576.87") and inv.currency == "EUR"
    assert inv.value("InvoiceDate") == date(2026, 11, 2)
    assert inv.value("VendorTaxId") == "PT 111 111 111"
    assert inv.confidence("InvoiceTotal") == pytest.approx(0.97)
    assert [i.amount for i in inv.items] == [Decimal("378.00"), Decimal("91.00")]
    assert inv.items[0].quantity == Decimal("2")


def test_missing_confidence_counts_as_zero_and_missing_field_as_none():
    result = analyze_result(sample("01"), drop=("DueDate",))
    del result["documents"][0]["fields"]["VendorName"]["confidence"]
    inv = to_invoice(result)
    assert inv.confidence("VendorName") == 0.0 and inv.value("DueDate") is None


def test_no_document_is_an_error_not_an_empty_invoice():
    with pytest.raises(ValueError, match="no document"):
        to_invoice({"documents": []})


def test_sdk_result_object_maps_the_same_way():
    from azure.ai.documentintelligence.models import AnalyzeResult

    inv = to_invoice(AnalyzeResult(analyze_result(sample("01"))))
    assert inv.value("InvoiceTotal") == Decimal("576.87")


def test_clean_invoice_is_approved():
    assert decide(to_invoice(analyze_result(sample("01")))).outcome == "approve"


def test_totals_that_dont_add_up_go_to_review_not_reject():
    d = decide(to_invoice(analyze_result(sample("02"))))
    assert d.outcome == "review" and "subtotal 200.00 + tax 46.00 != total 256.00" in d.reasons


def test_confidently_read_foreign_vat_is_rejected():
    d = decide(to_invoice(analyze_result(sample("03"))))
    assert d.outcome == "reject" and "not Contoso" in d.reasons[0]


def test_uncertain_foreign_vat_is_reviewed_not_rejected():
    # a misread digit must never auto-reject a valid supplier invoice
    d = decide(to_invoice(analyze_result(sample("03"), overrides={"CustomerTaxId": 0.55})))
    assert d.outcome == "review" and any("CustomerTaxId confidence 0.55" in r for r in d.reasons)


def test_low_confidence_total_goes_to_review():
    d = decide(to_invoice(analyze_result(sample("04"), overrides={"InvoiceTotal": 0.62})))
    assert d.outcome == "review" and d.reasons == ["InvoiceTotal confidence 0.62 < 0.90"]


def test_missing_required_policy_field_goes_to_review():
    d = decide(to_invoice(analyze_result(sample("01"), drop=("CustomerTaxId",))))
    assert d.outcome == "review" and "CustomerTaxId not found" in d.reasons


def test_duplicate_in_the_same_batch_is_rejected():
    rows = route_all([("01.png", analyze_result(sample("01"))), ("05.png", analyze_result(sample("05")))])
    assert [d.outcome for *_, d in rows] == ["approve", "reject"]
    assert rows[1][2].reasons == ["duplicate of invoice FAB-2026-0412 from PT111111111"]


def test_all_five_samples_route_as_designed_with_a_perfect_read():
    rows = route_all([(s, analyze_result(sample(s))) for s in ("01", "02", "03", "04", "05")])
    assert [d.outcome for *_, d in rows] == ["approve", "review", "reject", "approve", "reject"]


def test_date_order_line_items_and_currency_rules():
    result = analyze_result(sample("01"))
    f = result["documents"][0]["fields"]
    f["DueDate"]["valueDate"] = "2026-10-01"
    f["Items"]["valueArray"][0]["valueObject"]["Amount"]["valueCurrency"]["amount"] = 300.0
    for name in ("SubTotal", "TotalTax", "InvoiceTotal"):
        f[name]["valueCurrency"]["currencyCode"] = "USD"
    reasons = decide(to_invoice(result)).reasons
    assert "due date before invoice date" in reasons
    assert any(r.startswith("line items sum to 391.00") for r in reasons)
    assert "currency USD, expected EUR" in reasons


def test_tax_ids_are_compared_normalised():
    assert normalise_tax_id("pt 000.000-000") == "PT000000000"
    assert normalise_tax_id(None) is None
