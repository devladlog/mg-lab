"""The flow's expressions and invoicekit.triage must decide the same way on the same extraction.

The flow runs in the flowkit simulator (episodes 1-9) with mocks for SharePoint and Outlook; the mock for the
duplicate query reads the $filter the flow built, so a wrong filter string would fail here too.
"""
import itertools
import re
from datetime import date, datetime, timezone

import pytest
from conftest import EXTRACTIONS, SOLUTION, load

from flowkit.lint import load_flow
from flowkit.sim import run_flow
from invoicekit.triage import Config, decide, dup_key

FLOW = load_flow(next((SOLUTION / "Workflows").glob("Triageinvoiceextraction-*.json")))
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
POSTED = [("Adatum Office Supplies", "INV-2026-0412"), ("O'Neil & Sons", "A-1")]
PARAMS = {"Minimum confidence (cts_MinConfidence)": "0.8", "Amount limit (cts_AmountLimit)": "5000",
          "Maximum invoice age in days (cts_MaxAgeDays)": "365",
          "Reviewer mailbox (cts_ReviewerMailbox)": "accounts@contoso.com"}


def _unquote(s: str) -> str:
    return s.replace("''", "'")


def duplicates(inputs):
    f = inputs["parameters"]["$filter"]
    m = re.fullmatch(r"VendorName eq '((?:[^']|'')*)' and InvoiceId eq '((?:[^']|'')*)'", f)
    assert m, f"the filter is not what we expect: {f}"
    vendor, inv = _unquote(m.group(1)), _unquote(m.group(2))
    hits = [{"VendorName": v, "InvoiceId": i} for v, i in POSTED if (v.lower(), i.lower()) == (vendor.lower(), inv.lower())]
    return {"status": "Succeeded", "body": {"value": hits}}


def run(row: dict):
    log = {"posted": [], "mails": [], "patched": []}
    mocks = {
        "Get_possible_duplicates": duplicates,
        "Record_decision": lambda i: log["patched"].append(i["parameters"]["item/Decision/Value"]) or {"status": "Succeeded", "body": {}},
        "Post_invoice": lambda i: log["posted"].append(i["parameters"]) or {"status": "Succeeded", "body": {}},
        "Ask_reviewer": lambda i: log["mails"].append(i["parameters"]) or {"status": "Succeeded", "body": {}},
    }
    r = run_flow(FLOW, {"ID": 7, **row}, mocks, now=NOW, parameters=PARAMS)
    assert r.status == "Succeeded", r.terminate_error
    return r.actions["Decision"].outputs, log


KNOWN = {dup_key(v, i) for v, i in POSTED}


def python_says(row):
    return decide(row, Config(), date(2026, 11, 10), KNOWN).action


FIXTURES = sorted(p.name for p in EXTRACTIONS.glob("*.json") if p.name != "known.json")


@pytest.mark.parametrize("name", FIXTURES)
def test_fixtures_get_the_same_decision(name):
    row = load(name)
    decision, _ = run(row)
    assert decision == python_says(row)


def test_each_decision_does_what_it_says():
    d, log = run(load("clean.json") | {"InvoiceId": "INV-NEW-1"})
    assert d == "auto-post" and log["patched"] == ["auto-post"] and len(log["posted"]) == 1 and log["mails"] == []
    assert log["posted"][0]["item/InvoiceTotal"] == 747.6 and log["posted"][0]["table"] == "Invoices"
    d, log = run(load("over-limit.json"))
    assert d == "review" and log["posted"] == [] and len(log["mails"]) == 1
    assert log["mails"][0]["emailMessage/To"] == "accounts@contoso.com"
    assert "INV-2026-0501" in log["mails"][0]["emailMessage/Subject"]
    d, log = run(load("duplicate-of-0412.json"))
    assert d == "reject" and log["posted"] == [] and log["mails"] == [] and log["patched"] == ["reject"]


def test_vendor_with_an_apostrophe_builds_a_valid_filter_and_is_found_as_duplicate():
    row = load("clean.json") | {"VendorName": "O'Neil & Sons", "InvoiceId": "a-1"}
    decision, _ = run(row)
    assert decision == "reject" == python_says(row)


def _grid():
    base = load("clean.json")
    axes = {
        "InvoiceTotalConf": [0.97, 0.80, 0.79, None],
        "InvoiceDate": ["2026-11-02", "2026-11-11", "2026-11-12", "2025-11-10", "2025-11-09", None],
        "DueDate": ["2026-12-02", "2026-10-01", None],
        "InvoiceTotal": [747.60, 5000.0, 5000.01, 748.0, None],
    }
    for combo in itertools.product(*axes.values()):
        yield base | dict(zip(axes, combo)) | {"InvoiceId": "INV-GRID"}


def test_grid_of_combinations_agrees():
    n = 0
    for row in _grid():
        decision, _ = run(row)
        assert decision == python_says(row), row
        n += 1
    assert n == 4 * 6 * 3 * 5


@pytest.mark.parametrize("conf,limit", [("0.9", "5000"), ("0.5", "100"), ("1", "1000000")])
def test_changing_the_environment_variables_changes_the_flow_like_the_config(conf, limit):
    row = load("clean.json") | {"InvoiceId": "INV-ENV"}
    params = PARAMS | {"Minimum confidence (cts_MinConfidence)": conf, "Amount limit (cts_AmountLimit)": limit}
    r = run_flow(FLOW, {"ID": 1, **row}, {"Get_possible_duplicates": duplicates,
                 "Record_decision": {"status": "Succeeded", "body": {}}, "Post_invoice": {"status": "Succeeded", "body": {}},
                 "Ask_reviewer": {"status": "Succeeded", "body": {}}}, now=NOW, parameters=params)
    assert r.actions["Decision"].outputs == decide(row, Config(min_confidence=float(conf), amount_limit=float(limit)),
                                                   date(2026, 11, 10), KNOWN).action


@pytest.mark.parametrize("total", [120.00, 120.01, 120.02, 119.98, 119.99])
def test_one_cent_boundary_is_the_same_in_the_flow_and_in_python(total):
    row = load("clean.json") | {"InvoiceId": "INV-CENT", "SubTotal": 100.0, "TotalTax": 20.0, "InvoiceTotal": total}
    decision, _ = run(row)
    assert decision == python_says(row) == ("auto-post" if abs(total - 120) < 0.015 else "review")
