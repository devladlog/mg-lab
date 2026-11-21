"""Lint rules that matter for approval flows."""
import copy

from flowkit import lint

from conftest import actions, finance_block


def messages(flow, level):
    return [f.message for f in lint(flow) if f.level == level]


def test_the_solution_flow_is_clean(approval_flow):
    assert lint(approval_flow) == []


def test_approval_without_timeout_is_flagged(approval_flow):
    bad = copy.deepcopy(approval_flow)
    del finance_block(bad)["Finance_approval"]["limit"]
    assert any("without a timeout" in m for m in messages(bad, "warning"))


def test_timeout_without_a_handler_is_flagged(approval_flow):
    bad = copy.deepcopy(approval_flow)
    block = finance_block(bad)
    del block["Record_finance_timeout"]
    block["Finance_result"]["runAfter"] = {"Record_finance_response": ["Succeeded", "Skipped"]}
    assert any("nothing runs after it 'has timed out'" in m for m in messages(bad, "warning"))


def test_timeout_over_thirty_days_is_an_error(approval_flow):
    bad = copy.deepcopy(approval_flow)
    finance_block(bad)["Finance_approval"]["limit"]["timeout"] = "P31D"
    assert any("30-day" in m for m in messages(bad, "error"))


def test_set_variable_needs_an_initialized_variable(approval_flow):
    bad = copy.deepcopy(approval_flow)
    del actions(bad)["Initialize_decision"]
    actions(bad)["Is_small_amount"]["runAfter"] = {"Initialize_fallback_approver": ["Succeeded"]}
    assert any("no Initialize variable declares" in m for m in messages(bad, "error"))


def test_every_connector_is_solution_aware(approval_flow):
    refs = approval_flow["properties"]["connectionReferences"]
    assert set(refs) == {"shared_sharepointonline", "shared_office365", "shared_office365users", "shared_approvals"}
    assert all(r["connection"]["connectionReferenceLogicalName"].startswith("cts_") for r in refs.values())
