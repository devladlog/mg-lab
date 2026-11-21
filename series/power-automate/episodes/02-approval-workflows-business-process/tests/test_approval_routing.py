"""Every path through 'Purchase request approval', dry-run with mocked Approvals, Users, SharePoint, Outlook."""
import pytest

from flowkit import run_flow

from conftest import NOW, TIMED_OUT, approved, mocks, sample


def run(flow, item, m):
    return run_flow(flow, sample(item), m, now=NOW)


def test_under_500_is_auto_approved_without_asking_anyone(approval_flow):
    r = run(approval_flow, "purchase-small.json", mocks())
    assert r.status == "Succeeded"
    assert not r.ran("Get_manager") and not r.ran("Manager_approval") and not r.ran("Finance_approval")
    patch = r.actions["Mark_approved"].inputs["parameters"]
    assert patch["item/Status/Value"] == "Approved"
    assert patch["item/DecisionBy"] == "Policy: under 500 EUR"


def test_medium_amount_needs_only_the_manager(approval_flow):
    r = run(approval_flow, "purchase-medium.json", mocks())
    assert r.status == "Succeeded"
    req = r.actions["Manager_approval"].inputs["parameters"]
    assert req["approvalType"] == "Basic"
    assert req["WebhookApprovalCreationInput/assignedTo"] == "morgan.manager@contoso.com"
    assert req["WebhookApprovalCreationInput/title"] == "Manager approval: Ergonomic chairs for the support team (1800 EUR)"
    assert req["WebhookApprovalCreationInput/requestor"] == "alex.demo@contoso.com"
    assert r.status_of("Finance_approval") == "Skipped"
    patch = r.actions["Mark_approved"].inputs["parameters"]
    assert patch["item/DecisionBy"] == "Morgan Manager (manager)"
    assert patch["item/DecisionComments"] == "Within the team budget"


def test_manager_rejection_reaches_the_requester_with_the_reason(approval_flow):
    r = run(approval_flow, "purchase-medium.json", mocks(manager=approved("manager_rejects")))
    assert r.status == "Succeeded"
    assert r.ran("Mark_rejected") and not r.ran("Mark_approved")
    email = r.actions["Notify_requester_rejected"].inputs["parameters"]
    assert email["emailMessage/To"] == "alex.demo@contoso.com"
    assert "Reason: Not this quarter" in email["emailMessage/Body"]


def test_5000_and_above_goes_to_finance_after_the_manager(approval_flow):
    r = run(approval_flow, "purchase-large.json", mocks())
    assert r.status == "Succeeded"
    assert r.order.index("Manager_approval") < r.order.index("Finance_approval")   # sequential, not parallel
    fin = r.actions["Finance_approval"].inputs["parameters"]
    assert fin["WebhookApprovalCreationInput/assignedTo"] == "finance-approvers@contoso.com"
    assert r.actions["Mark_approved"].inputs["parameters"]["item/DecisionBy"] == "Fran Finance (finance)"


def test_finance_can_still_reject(approval_flow):
    r = run(approval_flow, "purchase-large.json", mocks(finance=approved("finance_rejects")))
    assert r.ran("Mark_rejected")
    assert r.actions["Mark_rejected"].inputs["parameters"]["item/DecisionComments"] == "Use the framework supplier"


def test_manager_rejection_never_bothers_finance(approval_flow):
    r = run(approval_flow, "purchase-large.json", mocks(manager=approved("manager_rejects")))
    assert r.status_of("Finance_approval") == "Skipped"
    assert r.ran("Mark_rejected")


@pytest.mark.parametrize("item, m, who", [
    ("purchase-medium.json", mocks(manager=TIMED_OUT), "Manager: no response within 3 days"),
    ("purchase-large.json", mocks(finance=TIMED_OUT), "Finance: no response within 3 days"),
])
def test_no_response_in_three_days_escalates(approval_flow, item, m, who):
    r = run(approval_flow, item, m)
    assert r.status == "Succeeded"            # the timeout is handled, so the run isn't Failed
    assert r.ran("Mark_escalated")
    assert r.actions["Mark_escalated"].inputs["parameters"]["item/DecisionBy"] == who
    email = r.actions["Notify_purchasing_team"].inputs["parameters"]
    assert email["emailMessage/To"] == "purchasing-team@contoso.com"
    assert email["emailMessage/Importance"] == "High"


def test_no_manager_in_entra_falls_back_to_the_purchasing_team(approval_flow):
    no_manager = {"status": "Failed", "statusCode": 404,
                  "body": {"error": {"message": "No manager found for the specified user."}}}
    r = run(approval_flow, "purchase-medium.json", mocks(get_manager=no_manager))
    assert r.status_of("Get_manager") == "Failed"
    req = r.actions["Manager_approval"].inputs["parameters"]
    assert req["WebhookApprovalCreationInput/assignedTo"] == "purchasing-team@contoso.com"
    assert r.status == "Succeeded"            # Manager_email runs after Failed, so that branch ends well


def test_a_broken_approval_fails_loudly(approval_flow):
    broken = {"status": "Failed", "statusCode": 500, "body": {"error": {"message": "Approval creation failed"}}}
    r = run(approval_flow, "purchase-medium.json", mocks(manager=broken))
    assert r.ran("Unexpected_outcome")
    assert r.status == "Failed"
    assert "'Pending' isn't handled" in r.terminate_error["message"]


def test_only_pending_items_start_a_run(approval_flow):
    item = sample("purchase-medium.json")
    item["Status"] = dict(item["Status"], Value="Approved")
    r = run_flow(approval_flow, item, mocks(), now=NOW)
    assert r.status == "Skipped" and r.actions == {}


def test_flowkit_refuses_an_empty_amount(approval_flow):
    # Amount is required in the list. If it ever arrives empty, less(null, 500) can't be evaluated:
    # flowkit fails the condition instead of guessing (the list setting is what really prevents it).
    item = sample("purchase-medium.json")
    item["Amount"] = None
    r = run_flow(approval_flow, item, mocks(), now=NOW)
    assert r.status_of("Is_small_amount") == "Failed"
    assert r.status == "Failed"
