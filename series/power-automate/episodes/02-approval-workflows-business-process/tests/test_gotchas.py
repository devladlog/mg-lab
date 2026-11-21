"""The two mistakes this episode is about, reproduced on purpose."""
import copy

from flowkit import lint, run_flow

from conftest import NOW, TIMED_OUT, actions, finance_block, mocks, sample


def test_handled_timeout_can_still_fail_the_run_without_a_join(approval_flow):
    # Remove the 'Finance_result' join: Record_finance_response is now the last action of a branch,
    # it's skipped when finance times out, and that branch "ends in failure" (documented rule).
    bad = copy.deepcopy(approval_flow)
    del finance_block(bad)["Finance_result"]
    r = run_flow(bad, sample("purchase-large.json"), mocks(finance=TIMED_OUT), now=NOW)
    assert r.status_of("Record_finance_timeout") == "Succeeded"     # the handler ran...
    assert r.status_of("Needs_finance_approval") == "Failed"        # ...but the condition is Failed
    assert r.status_of("Route_decision") == "Skipped"               # so nobody is ever told
    assert r.status == "Failed"
    warnings = [f.message for f in lint(bad) if f.level == "warning"]
    assert any("marks the scope Failed" in m for m in warnings)


def test_with_the_join_the_same_timeout_escalates(approval_flow):
    r = run_flow(approval_flow, sample("purchase-large.json"), mocks(finance=TIMED_OUT), now=NOW)
    assert r.status_of("Finance_result") == "Succeeded"
    assert r.ran("Notify_purchasing_team")


def test_approved_is_not_an_approval_outcome(approval_flow):
    # Valid responses to a Basic approval are "Approve" and "Reject" (case-sensitive).
    bad = copy.deepcopy(approval_flow)
    actions(bad)["Route_decision"]["cases"]["Approved"]["case"] = "Approved"
    r = run_flow(bad, sample("purchase-medium.json"), mocks(), now=NOW)
    assert r.ran("Unexpected_outcome") and not r.ran("Mark_approved")
    assert r.status == "Failed"
    assert any("'Approve' and 'Reject'" in f.message for f in lint(bad))
