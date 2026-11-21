import pytest

from docintel.mapping import dedup_key, extract, to_columns
from docintel.rules import Policy, decide


def test_clean_invoice_is_ready(invoice_result):
    d = decide(extract(invoice_result))
    assert d.status == "Ready"
    assert d.reasons == []
    assert d.columns["InvStatus"] == "Ready" and d.columns["InvReasons"] == ""


def test_columns_are_mapped(invoice_result):
    c = to_columns(extract(invoice_result))
    assert c["InvVendor"] == "Fabrikam Office Supplies"
    assert c["InvNumber"] == "INV-2026-0417"
    assert (c["InvDate"], c["InvDueDate"]) == ("2026-10-31", "2026-11-30")
    assert (c["InvSubTotal"], c["InvTax"], c["InvTotal"], c["InvCurrency"]) == (1200.0, 276.0, 1476.0, "EUR")
    assert c["InvPO"] == "PO-7781"
    assert c["InvConfidence"] == 0.948          # lowest of the four required fields (VendorName)
    assert c["InvDedupKey"] == "fabrikamofficesupplies|INV20260417"


def test_low_confidence_on_a_required_field_needs_review(invoice_result, fields):
    fields["InvoiceTotal"]["confidence"] = 0.61
    d = decide(extract(invoice_result))
    assert d.status == "Needs review"
    assert d.reasons == ["Low confidence on InvoiceTotal (0.61 < 0.80)."]


def test_low_confidence_on_an_optional_field_is_fine(invoice_result, fields):
    fields["PurchaseOrder"]["confidence"] = 0.2
    assert decide(extract(invoice_result)).status == "Ready"


def test_threshold_comes_from_policy(invoice_result, fields):
    fields["VendorName"]["confidence"] = 0.85
    assert decide(extract(invoice_result), Policy(min_confidence=0.80)).status == "Ready"
    assert decide(extract(invoice_result), Policy(min_confidence=0.90)).status == "Needs review"


def test_missing_required_field(invoice_result, fields):
    del fields["InvoiceId"]
    d = decide(extract(invoice_result))
    assert d.status == "Needs review"
    assert "Missing InvoiceId." in d.reasons
    assert d.columns["InvDedupKey"] == ""        # no key without an invoice number


def test_totals_must_add_up(invoice_result, fields):
    fields["TotalTax"]["valueCurrency"]["amount"] = 267.0   # transposed digits
    d = decide(extract(invoice_result))
    assert d.status == "Needs review"
    assert d.reasons == ["Subtotal + tax (1467.00) does not match total (1476.00)."]


def test_rounding_within_tolerance_is_fine(invoice_result, fields):
    fields["TotalTax"]["valueCurrency"]["amount"] = 275.995
    assert decide(extract(invoice_result)).status == "Ready"


def test_over_the_approval_limit_always_goes_to_a_person(invoice_result, fields):
    for f, a in (("SubTotal", 20000.0), ("TotalTax", 4600.0), ("InvoiceTotal", 24600.0)):
        fields[f]["valueCurrency"]["amount"] = a
    d = decide(extract(invoice_result))
    assert d.status == "Needs review"
    assert d.reasons == ["Total above the approval limit (10,000)."]


def test_dollar_sign_alone_is_ambiguous(invoice_result, fields):
    for f in ("SubTotal", "TotalTax", "InvoiceTotal"):
        fields[f]["valueCurrency"] = {"amount": fields[f]["valueCurrency"]["amount"], "currencySymbol": "$"}
    d = decide(extract(invoice_result))
    assert d.columns["InvCurrency"] is None
    assert "Currency is ambiguous or missing." in d.reasons


def test_euro_symbol_without_code_is_mapped(invoice_result, fields):
    fields["InvoiceTotal"]["valueCurrency"] = {"amount": 1476.0, "currencySymbol": "€"}
    d = decide(extract(invoice_result))
    assert d.columns["InvCurrency"] == "EUR" and d.status == "Ready"


def test_currency_not_accepted(invoice_result, fields):
    fields["InvoiceTotal"]["valueCurrency"]["currencyCode"] = "CHF"
    d = decide(extract(invoice_result))
    assert d.reasons == ["Currency CHF is not accepted."]


def test_due_date_before_invoice_date(invoice_result, fields):
    fields["DueDate"]["valueDate"] = "2026-10-01"
    assert decide(extract(invoice_result)).reasons == ["Due date is before the invoice date."]


def test_credit_note_is_flagged(invoice_result, fields):
    for f, a in (("SubTotal", -100.0), ("TotalTax", -23.0), ("InvoiceTotal", -123.0)):
        fields[f]["valueCurrency"]["amount"] = a
    assert "Total is zero or negative (credit note?)." in decide(extract(invoice_result)).reasons


def test_no_documents_is_rejected(invoice_result):
    invoice_result["documents"] = []
    d = decide(extract(invoice_result))
    assert d.status == "Rejected"
    assert d.columns["InvStatus"] == "Rejected"


def test_two_invoices_in_one_file(invoice_result):
    invoice_result["documents"].append(invoice_result["documents"][0])
    d = decide(extract(invoice_result))
    assert d.status == "Needs review"
    assert d.reasons == ["2 invoices in one file; only the first was read."]


def test_several_problems_are_all_reported(invoice_result, fields):
    del fields["VendorName"]
    fields["DueDate"]["valueDate"] = "2026-01-01"
    d = decide(extract(invoice_result))
    assert d.reasons == ["Missing VendorName.", "Due date is before the invoice date."]


@pytest.mark.parametrize("a,b", [
    (("Fabrikam Office Supplies", "INV-2026-0417"), ("FABRIKAM OFFICE SUPPLIES ", "inv 2026 0417")),
    (("Fabrikam, Lda.", "A/17"), ("fabrikam lda", "a17")),
])
def test_dedup_key_ignores_case_spacing_and_punctuation(a, b):
    assert dedup_key(*a) == dedup_key(*b) != ""


def test_policy_from_app_settings():
    p = Policy.from_env({"MIN_CONFIDENCE": "0.9", "APPROVAL_LIMIT": "5000", "ALLOWED_CURRENCIES": "eur, usd"})
    assert p == Policy(min_confidence=0.9, approval_limit=5000.0, allowed_currencies=("EUR", "USD"))
