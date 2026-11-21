"""Dry-run the 'IT request intake' flow with mocked SharePoint and Outlook calls."""
import pytest

from flowkit import SimulationError, run_flow

from conftest import NOW, sample

OK = {"status": "Succeeded", "body": {}}


def mocks(**overrides):
    m = {"Alert_on_call_engineer": OK, "Mark_as_triaged": OK, "Acknowledge_requester": OK}
    m.update(overrides)
    return m


def test_high_priority_alerts_on_call_and_sets_a_4_hour_due_date(intake):
    run = run_flow(intake, sample("it-request-high.json"), mocks(), now=NOW)
    assert run.status == "Succeeded"
    assert run.ran("Alert_on_call_engineer")
    alert = run.actions["Alert_on_call_engineer"].inputs["parameters"]
    assert alert["emailMessage/Importance"] == "High"
    assert alert["emailMessage/Subject"] == "HIGH priority IT request #42: Laptop won't boot before a client demo"
    patch = run.actions["Mark_as_triaged"].inputs["parameters"]
    assert patch["id"] == 42
    assert patch["item/Status/Value"] == "Triaged"
    assert patch["item/DueDate"] == "2026-01-05T13:00:00.0000000Z"   # 09:00 + 4 h


def test_normal_priority_skips_the_alert_and_gets_24_hours(intake):
    run = run_flow(intake, sample("it-request-normal.json"), mocks(), now=NOW)
    assert run.status == "Succeeded"
    assert run.status_of("Alert_on_call_engineer") == "Skipped"
    assert run.variables["slaHours"] == 24
    ack = run.actions["Acknowledge_requester"].inputs["parameters"]
    assert ack["emailMessage/To"] == "alex.demo@contoso.com"
    assert "2026-01-06 09:00 UTC (24 hours)" in ack["emailMessage/Body"]


def test_test_items_never_start_a_run(intake):
    # Trigger condition is false: no run, nothing in the run history, no actions consumed.
    run = run_flow(intake, sample("it-request-test.json"), mocks(), now=NOW)
    assert run.status == "Skipped"
    assert run.actions == {}


def test_missing_title_and_priority_do_not_break_the_flow(intake):
    # coalesce() + the ?[ ] operator keep empty columns from failing the run.
    run = run_flow(intake, sample("it-request-no-priority.json"), mocks(), now=NOW)
    assert run.status == "Succeeded"
    assert run.variables["slaHours"] == 24


def test_failed_update_stops_the_acknowledgement(intake):
    failing = mocks(Mark_as_triaged={"status": "Failed", "statusCode": 400,
                                     "body": {"message": "Column 'DueDate' does not exist"}})
    run = run_flow(intake, sample("it-request-normal.json"), failing, now=NOW)
    assert run.status_of("Mark_as_triaged") == "Failed"
    assert run.status_of("Acknowledge_requester") == "Skipped"   # default run after: is successful
    assert run.status == "Failed"


def test_every_connector_call_needs_a_mock(intake):
    with pytest.raises(SimulationError, match="No mock"):
        run_flow(intake, sample("it-request-high.json"), {"Mark_as_triaged": OK}, now=NOW)
