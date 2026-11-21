"""'Enter approved purchase orders': every path, with the desktop flow mocked (no Windows session needed)."""
from flowkit import run_flow
from flowkit.lint import lint

from conftest import NOW, mocks


def test_the_flow_lints_clean(flow):
    assert [str(f) for f in lint(flow)] == []


def run(flow, item, m):
    return run_flow(flow, item, m, now=NOW)


def test_saved_order_comes_back_to_the_request(flow, item):
    r = run(flow, item, mocks())
    assert r.status == "Succeeded"
    call = r.actions["Run_desktop_flow"].inputs["parameters"]
    assert call["uiFlowId"] == "00000000-0000-0000-0000-000000000901"
    assert call["runMode"] == "attended"
    assert call["item/Supplier"] == "Fabrikam"
    assert call["item/Amount"] == "12500.00"        # text with a dot, whatever the machine culture is
    assert call["item/RequestId"] == "7"
    patch = r.actions["Mark_entered"].inputs["parameters"]
    assert patch["item/PONumber"] == "PO-2026-0003" and patch["item/RpaStatus"] == "Entered"
    assert r.actions["Tell_requester_entered"].inputs["parameters"]["emailMessage/To"] == "alex.demo@contoso.com"
    assert not r.ran("Mark_rejected") and r.status_of("Catch") == "Skipped"


def test_a_rejected_order_is_reported_not_retried(flow, item):
    m = mocks(Run_desktop_flow={"status": "Succeeded", "body": {"Status": "Rejected", "OrderNumber": "", "Errors": "Supplier is required"}})
    r = run(flow, item, m)
    assert r.status == "Succeeded"
    assert r.actions["Mark_rejected"].inputs["parameters"]["item/RpaStatus"] == "Rejected: Supplier is required"
    assert "Supplier is required" in r.actions["Tell_requester_rejected"].inputs["parameters"]["emailMessage/Body"]
    assert not r.ran("Mark_entered")


def test_a_failed_desktop_run_marks_the_item_and_tells_purchasing_why(flow, item):
    m = mocks(Run_desktop_flow={"status": "Failed", "error": "Order was not found in the ledger: ledger file not found"})
    r = run(flow, item, m)
    assert r.status == "Succeeded"  # handled: the Catch scope ran
    assert r.actions["Mark_failed"].inputs["parameters"]["item/RpaStatus"] == "Failed"
    mail = r.actions["Tell_purchasing_team"].inputs["parameters"]
    assert "ledger file not found" in mail["emailMessage/Body"]
    assert mail["emailMessage/Importance"] == "High"
    assert r.status_of("Order_saved") == "Skipped"


def test_a_timed_out_desktop_run_takes_the_same_path(flow, item):
    r = run(flow, item, mocks(Run_desktop_flow={"status": "TimedOut"}))
    assert r.status == "Succeeded"
    assert r.ran("Mark_failed") and r.ran("Tell_purchasing_team")
    assert flow["properties"]["definition"]["actions"]["Try"]["actions"]["Run_desktop_flow"]["limit"]["timeout"] == "PT30M"


def test_without_the_catch_scope_nobody_is_told(flow, item):
    """Negative control: take Catch away and the failed desktop run is silent. Nothing marks the item or mails anyone."""
    del flow["properties"]["definition"]["actions"]["Catch"]
    flow["properties"]["definition"]["actions"]["Result"]["runAfter"].pop("Catch")
    r = run(flow, item, mocks(Run_desktop_flow={"status": "Failed", "error": "boom"}))
    assert r.status_of("Try") == "Failed"
    assert not r.ran("Mark_failed") and not r.ran("Tell_purchasing_team") and not r.ran("Mark_entered")


def test_the_trigger_does_not_fire_again_after_the_flow_updates_the_item(flow, item):
    """The trigger fires on every modification; our own PatchItem is one. Without RpaStatus in the condition: a loop."""
    first = run(flow, item, mocks())
    assert first.status == "Succeeded"
    for done in ({"RpaStatus": "Entered", "PONumber": "PO-2026-0003"}, {"RpaStatus": "Failed"},
                 {"RpaStatus": "Rejected: Supplier is required"}):
        again = run(flow, {**item, **done}, mocks())
        assert again.status == "Skipped", done


def test_only_approved_requests_start_the_flow(flow, item):
    item["Status"] = {"Value": "Pending"}
    assert run(flow, item, mocks()).status == "Skipped"
