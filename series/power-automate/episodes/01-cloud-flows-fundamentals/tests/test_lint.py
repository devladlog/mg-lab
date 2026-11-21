"""The linter: our two flows are clean, and each rule catches the mistake it was written for."""
import copy

import pytest

from flowkit.lint import iso_duration_seconds, lint


def errors(flow):
    return [f.message for f in lint(flow) if f.level == "error"]


def test_solution_flows_are_clean(intake, digest):
    assert lint(intake) == []
    assert lint(digest) == []


def actions(flow):
    return flow["properties"]["definition"]["actions"]


def test_run_after_must_point_to_an_existing_action(intake):
    bad = copy.deepcopy(intake)
    actions(bad)["Mark_as_triaged"]["runAfter"] = {"Is_high_prio": ["Succeeded"]}
    assert any("isn't an action in the same scope" in m for m in errors(bad))


def test_run_after_status_spelling(intake):
    bad = copy.deepcopy(intake)
    actions(bad)["Mark_as_triaged"]["runAfter"] = {"Is_high_priority": ["Success"]}
    assert any("isn't one of" in m for m in errors(bad))


def test_variable_must_be_initialized_at_top_level(intake):
    bad = copy.deepcopy(intake)
    init = actions(bad).pop("Initialize_SLA_hours")
    actions(bad)["Due_date"]["runAfter"] = {}
    actions(bad)["Is_high_priority"]["actions"]["Initialize_SLA_hours"] = init
    msgs = errors(bad)
    assert any("only allowed at the top level" in m for m in msgs)


def test_unknown_variable_and_unknown_action_references(intake):
    bad = copy.deepcopy(intake)
    actions(bad)["Due_date"]["inputs"] = "@addHours(utcNow(), variables('sla'))"
    actions(bad)["Mark_as_triaged"]["inputs"]["parameters"]["item/DueDate"] = "@outputs('Due')"
    msgs = errors(bad)
    assert any("variables('sla')" in m for m in msgs)
    assert any("outputs('Due')" in m for m in msgs)


def test_connection_must_be_declared(intake):
    bad = copy.deepcopy(intake)
    del bad["properties"]["connectionReferences"]["shared_office365"]
    assert any("isn't declared in properties.connectionReferences" in m for m in errors(bad))


def test_embedded_connection_is_a_warning(intake):
    bad = copy.deepcopy(intake)
    bad["properties"]["connectionReferences"]["shared_office365"]["connection"] = {"name": "shared-office365-1"}
    warnings = [f.message for f in lint(bad) if f.level == "warning"]
    assert any("not solution-aware" in m for m in warnings)


def test_trigger_condition_must_start_with_at(intake):
    bad = copy.deepcopy(intake)
    trig = bad["properties"]["definition"]["triggers"]["When_an_IT_request_is_created"]
    trig["conditions"][0]["expression"] = "not(startsWith(triggerBody()?['Title'], '[test]'))"
    assert any("must start with '@'" in m for m in errors(bad))


def test_trigger_condition_cannot_use_actions_or_variables(intake):
    bad = copy.deepcopy(intake)
    trig = bad["properties"]["definition"]["triggers"]["When_an_IT_request_is_created"]
    trig["conditions"].append({"expression": "@equals(variables('slaHours'), 4)"})
    assert any("can't be used in a trigger condition" in m for m in errors(bad))


def test_cycles_are_detected(intake):
    bad = copy.deepcopy(intake)
    actions(bad)["Initialize_SLA_hours"]["runAfter"] = {"Acknowledge_requester": ["Succeeded"]}
    msgs = errors(bad)
    assert any("no action in this scope starts first" in m for m in msgs)
    assert any("cycle" in m for m in msgs)


def test_items_outside_its_loop(digest):
    bad = copy.deepcopy(digest)
    actions(bad)["Get_open_requests"]["inputs"]["parameters"]["$top"] = "@items('Loop')"
    assert any("outside the loop" in m for m in errors(bad))


def test_timeout_longer_than_thirty_days(intake):
    bad = copy.deepcopy(intake)
    actions(bad)["Mark_as_triaged"]["limit"] = {"timeout": "P45D"}
    assert any("30-day" in m for m in errors(bad))


def test_recurrence_minimum_interval(digest):
    bad = copy.deepcopy(digest)
    trig = bad["properties"]["definition"]["triggers"]["Every_weekday_at_8"]
    trig["recurrence"] = {"frequency": "Second", "interval": 30}
    assert any("60 seconds" in m for m in errors(bad))


@pytest.mark.parametrize("text, seconds", [("PT10S", 10), ("PT5M", 300), ("P3D", 259200), ("P1DT12H", 129600)])
def test_iso_durations(text, seconds):
    assert iso_duration_seconds(text) == seconds


def test_bad_duration():
    with pytest.raises(ValueError):
        iso_duration_seconds("3 days")
