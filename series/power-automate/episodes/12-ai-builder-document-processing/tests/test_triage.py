"""Triage rules on the hand-written extraction fixtures (mocks of the staging list rows) and on edge cases."""
import json
import subprocess
import sys
from datetime import date

import pytest
from conftest import EXTRACTIONS, SRC, load

from invoicekit.triage import AUTO, REJECT, REVIEW, Config, decide, dup_key

TODAY = date(2026, 11, 10)
KNOWN = {dup_key("Adatum Office Supplies", "INV-2026-0412")}


@pytest.mark.parametrize("name,action,codes", [
    ("clean.json", REJECT, ["DUPLICATE"]),   # same invoice as the known one: see the next test for the clean case
    ("low-confidence-total.json", REJECT, ["DUPLICATE"]),
    ("total-mismatch.json", REVIEW, ["MISMATCH"]),
    ("over-limit.json", REVIEW, ["OVERLIMIT"]),
    ("missing-vendor.json", REVIEW, ["MISSING"]),
    ("due-before-invoice.json", REVIEW, ["DATE"]),
    ("not-an-invoice.json", REJECT, ["NOT_INVOICE"]),
    ("duplicate-of-0412.json", REJECT, ["DUPLICATE"]),
])
def test_fixtures_with_a_known_invoice(name, action, codes):
    d = decide(load(name), today=TODAY, known=KNOWN)
    assert (d.action, d.codes) == (action, codes)


@pytest.mark.parametrize("name,action,codes", [
    ("clean.json", AUTO, []),
    ("low-confidence-total.json", REVIEW, ["LOWCONF"]),
])
def test_fixtures_with_nothing_posted_yet(name, action, codes):
    d = decide(load(name), today=TODAY)
    assert (d.action, d.codes) == (action, codes)


def test_low_confidence_names_the_fields():
    d = decide(load("low-confidence-total.json"), today=TODAY)
    assert "InvoiceDate, InvoiceTotal" in d.reasons[0].text


def test_confidence_threshold_is_inclusive():
    x = load("clean.json")
    x["InvoiceTotalConf"] = 0.80
    assert decide(x, today=TODAY).action == AUTO
    x["InvoiceTotalConf"] = 0.79
    assert decide(x, today=TODAY).action == REVIEW
    assert decide(x, Config(min_confidence=0.75), today=TODAY).action == AUTO


def test_a_value_without_a_confidence_is_not_trusted():
    x = load("clean.json")
    del x["InvoiceIdConf"]
    assert decide(x, today=TODAY).codes == ["LOWCONF"]


def test_amount_limit_is_inclusive():
    x = load("clean.json") | {"SubTotal": 4166.67, "TotalTax": 833.33, "InvoiceTotal": 5000.00}
    assert decide(x, today=TODAY).action == AUTO
    x["InvoiceTotal"], x["TotalTax"] = 5000.01, 833.34
    assert decide(x, today=TODAY).codes == ["OVERLIMIT"]


def test_rounding_difference_of_one_cent_is_tolerated_two_cents_are_not():
    x = load("clean.json") | {"SubTotal": 100.00, "TotalTax": 20.00, "InvoiceTotal": 120.01}
    assert decide(x, today=TODAY).action == AUTO
    x["InvoiceTotal"] = 120.02
    assert decide(x, today=TODAY).codes == ["MISMATCH"]


def test_no_subtotal_means_no_arithmetic_check():
    x = load("clean.json") | {"SubTotal": None, "TotalTax": None, "InvoiceTotal": 999.0}
    assert decide(x, today=TODAY).action == AUTO


def test_future_and_old_dates():
    x = load("clean.json")
    assert decide(x | {"InvoiceDate": "2026-11-11", "DueDate": None}, today=TODAY).action == AUTO   # tomorrow is fine
    assert decide(x | {"InvoiceDate": "2026-11-12", "DueDate": None}, today=TODAY).codes == ["DATE"]
    assert decide(x | {"InvoiceDate": "2025-11-10", "DueDate": None}, today=TODAY).action == AUTO    # exactly 365 days
    assert decide(x | {"InvoiceDate": "2025-11-09", "DueDate": None}, today=TODAY).codes == ["DATE"]


def test_several_reasons_are_all_listed():
    x = load("total-mismatch.json") | {"InvoiceTotalConf": 0.4, "VendorName": None}
    assert decide(x, today=TODAY).codes == ["MISSING", "LOWCONF", "MISMATCH"]


def test_duplicate_match_ignores_case_and_outer_spaces_only():
    known = {dup_key("Adatum Office Supplies", "INV-2026-0412")}
    x = load("clean.json")
    assert decide(x | {"VendorName": " ADATUM office supplies ", "InvoiceId": "inv-2026-0412 "}, today=TODAY, known=known).codes == ["DUPLICATE"]
    # known limitation, stated in the README: a different way of writing the same number is not a duplicate
    assert decide(x | {"InvoiceId": "INV20260412"}, today=TODAY, known=known).action == AUTO


def test_all_fixtures_say_they_are_mocks():
    files = [p for p in EXTRACTIONS.glob("*.json") if p.name != "known.json"]
    assert len(files) == 8
    assert all("MOCK" in json.loads(p.read_text("utf-8"))["_note"] for p in files)


def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "invoicekit", *args], cwd=SRC, capture_output=True, text=True)


def test_cli_triage_output_and_exit_code():
    r = run_cli("triage", "extractions/clean.json", "extractions/over-limit.json", "--today", "2026-11-10")
    assert r.returncode == 1
    assert "AUTO-POST  clean.json" in r.stdout
    assert "REVIEW     over-limit.json" in r.stdout and "OVERLIMIT: total 7320 is over the limit 5000" in r.stdout


def test_cli_triage_all_clean_exits_zero_and_flags_change_the_verdict():
    assert run_cli("triage", "extractions/clean.json", "--today", "2026-11-10").returncode == 0
    r = run_cli("triage", "extractions/clean.json", "--today", "2026-11-10", "--amount-limit", "500")
    assert r.returncode == 1 and "OVERLIMIT" in r.stdout
    r = run_cli("triage", "extractions/clean.json", "--today", "2026-11-10", "--known", "extractions/known.json")
    assert "REJECT" in r.stdout and "DUPLICATE" in r.stdout
