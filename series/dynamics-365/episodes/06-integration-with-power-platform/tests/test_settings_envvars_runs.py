import json
from datetime import datetime, timezone

import pytest

from conftest import WF, FakeResponse, created, flow, value
from flowkit import envvars, runs, settings


def test_settings_skeleton_matches_learn_shape(good, cfg):
    body = settings.build(flow(good), cfg)
    assert list(body) == ["EnvironmentVariables", "ConnectionReferences"]
    assert body["EnvironmentVariables"] == [{"SchemaName": "mgl_AlertTeamId", "Value": ""},
                                            {"SchemaName": "mgl_AlertChannelId", "Value": ""}]
    assert body["ConnectionReferences"][1] == {"LogicalName": "mgl_sharedteams_00000", "ConnectionId": "",
                                               "ConnectorId": "/providers/Microsoft.PowerApps/apis/shared_teams"}


def test_settings_check_refuses_empty_and_missing_values(good, cfg):
    f = flow(good)
    body = settings.build(f, cfg)
    problems = settings.check(body, f, cfg)
    assert len(problems) == 4 and "mgl_AlertTeamId: empty Value" in problems[0]
    for ev in body["EnvironmentVariables"]:
        ev["Value"] = "x"
    for cr in body["ConnectionReferences"]:
        cr["ConnectionId"] = "0000000000000000000000000000c0de"
    assert settings.check(body, f, cfg) == []
    body["ConnectionReferences"].pop()
    body["EnvironmentVariables"].pop()
    assert settings.check(body, f, cfg) == ["mgl_sharedteams_00000: used by the flow but missing from the settings file",
                                            "mgl_AlertChannelId: missing from the settings file"]


def test_envvars_definition_in_solution_value_outside(api, stub, cfg):
    stub.on("GET", r"^environmentvariabledefinitions\?", value())
    stub.on("GET", r"^environmentvariablevalues\?", value())
    stub.on("POST", r"^environmentvariabledefinitions$", created("environmentvariabledefinitions", "00000000-0000-0000-0000-0000000000d1"))
    stub.on("POST", r"^environmentvariablevalues$", created("environmentvariablevalues"))
    lines = []
    envvars.ensure(api, cfg, {"mgl_AlertTeamId": "team-guid"}, out=lines.append)
    defs = stub.sent("POST", "^environmentvariabledefinitions")
    assert len(defs) == 2 and all(r["headers"]["MSCRM.SolutionUniqueName"] == "MGLabDataverse" for r in defs)
    assert defs[0]["json"] == {"schemaname": "mgl_AlertTeamId", "displayname": "Alert Team Id", "type": 100000000,
                               "description": cfg["environment_variables"][0]["description"]}
    (val,) = stub.sent("POST", "^environmentvariablevalues")
    assert "MSCRM.SolutionUniqueName" not in val["headers"]                 # value not shipped with the solution
    assert val["json"]["EnvironmentVariableDefinitionId@odata.bind"] == "/environmentvariabledefinitions(00000000-0000-0000-0000-0000000000d1)"
    assert lines == ["+ definition mgl_AlertTeamId (String) in MGLabDataverse", "+ value mgl_AlertTeamId (not in the solution)",
                     "+ definition mgl_AlertChannelId (String) in MGLabDataverse"]


def test_changing_a_value_reminds_you_to_restart_the_flow(api, stub, cfg):
    stub.on("GET", r"^environmentvariabledefinitions\?", value({"environmentvariabledefinitionid": "d1", "type": 100000000}))
    stub.on("GET", r"^environmentvariablevalues\?", value({"environmentvariablevalueid": "v1", "value": "old"}))
    stub.on("PATCH", r"^environmentvariablevalues\(v1\)", FakeResponse(204))
    lines = []
    envvars.ensure(api, cfg, {"mgl_AlertChannelId": "new"}, out=lines.append)
    (patch,) = stub.sent("PATCH")
    assert patch["json"] == {"value": "new"} and "MSCRM.SolutionUniqueName" not in patch["headers"]
    assert "flowkit restart" in lines[-1]
    assert stub.sent("POST") == []


def test_envvars_rejects_unknown_names_and_bad_assignments(api, cfg):
    with pytest.raises(ValueError, match="not in flow.json: mgl_Nope"):
        envvars.ensure(api, cfg, {"mgl_Nope": "1"})
    assert envvars.parse_assignments(["a=b=c"]) == {"a": "b=c"}
    with pytest.raises(ValueError, match="NAME=VALUE"):
        envvars.parse_assignments(["oops"])


def test_find_flow_is_by_name_in_category_5(api, stub):
    stub.on("GET", r"^workflows\?", value())
    with pytest.raises(LookupError, match="My Flows"):
        runs.find_flow(api, "Notify high-risk project requests")
    (q,) = stub.sent("GET")
    assert "category eq 5 and name eq 'Notify high-risk project requests'" in q["url"]


def test_run_history_query_and_report(api, stub, cfg):
    sample = json.loads((__import__("conftest").ROOT / "sample" / "flowruns.json").read_text())["value"]
    stub.on("GET", r"^flowruns\?", value(*sample))
    rows = runs.fetch(api, WF, days=7, now=datetime(2027, 1, 15, 12, 0, tzinfo=timezone.utc))
    (q,) = stub.sent("GET", "^flowruns")
    assert f"_workflow_value eq {WF} and starttime ge 2027-01-08T12:00:00Z" in q["url"]
    assert q["headers"]["Prefer"] == "odata.maxpagesize=500"
    s = runs.summarize(rows)
    assert (s["runs"], s["by_status"], s["avg_ms"], s["max_ms"], s["errors"]) == \
        (5, {"Cancelled": 1, "Failed": 1, "Success": 3}, 2546, 4410, {"NotFound": 1})
    lines = runs.report(cfg["flow_name"], rows, 7)
    assert lines[1] == "  Cancelled 1  Failed 1  Success 3"
    assert lines[2] == "  duration avg 2.5 s, max 4.4 s"
    assert lines[-1].startswith("  last failure 2027-01-14T09:02:13: Team not found")


def test_no_runs_explains_why(cfg):
    assert "FlowRunTimeToLiveInSeconds" in runs.report(cfg["flow_name"], [], 7)[1]
