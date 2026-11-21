import json

from conftest import SAMPLE, WF, FakeResponse, value
from flowkit import cli


def test_pull_saves_pretty_json_and_prints_a_summary(api, stub, cfg, tmp_path, good):
    stub.on("GET", r"^workflows\?", value({"workflowid": WF, "name": cfg["flow_name"], "statecode": 1,
                                          "modifiedon": "2027-01-15T09:00:00Z", "clientdata": json.dumps(good)}))
    lines = []
    out = tmp_path / "flow.json"
    cli.cmd_pull(api, cfg, out, out=lines.append)
    assert "clientdata" in stub.sent("GET")[0]["url"]
    assert json.loads(out.read_text()) == good
    assert out.read_text().startswith('{\n  "properties"')          # diffable in git
    assert lines[0] == "Notify high-risk project requests  (On, modified 2027-01-15T09:00:00)  -> flow.json"


def test_restart_turns_the_flow_off_then_on(api, stub, cfg):
    stub.on("GET", r"^workflows\?", value({"workflowid": WF, "name": cfg["flow_name"], "statecode": 1}))
    stub.on("PATCH", rf"^workflows\({WF}\)", FakeResponse(204))
    cli.cmd_restart(api, cfg, out=lambda s: None)
    assert [p["json"] for p in stub.sent("PATCH")] == [{"statecode": 0}, {"statecode": 1}]
    assert all(p["headers"]["If-Match"] == "*" for p in stub.sent("PATCH"))


def test_connrefs_flags_references_without_a_connection(api, stub):
    stub.on("GET", r"^connectionreferences\?", value(
        {"connectionreferencelogicalname": "mgl_sharedteams_00000", "connectorid": "/providers/Microsoft.PowerApps/apis/shared_teams",
         "connectionid": "0000000000000000000000000000c0de"},
        {"connectionreferencelogicalname": "mgl_sharedcommondataserviceforapps_00000",
         "connectorid": "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps", "connectionid": None}))
    lines = []
    assert cli.cmd_connrefs(api, out=lines.append) == 1
    assert lines[1].split() == ["mgl_sharedcommondataserviceforapps_00000", "shared_commondataserviceforapps", "NO", "CONNECTION"]
    assert lines[-1] == "2 connection reference(s), 1 without a connection"


def test_offline_commands_via_main(capsys, tmp_path):
    assert cli.main(["lint", "--file", str(SAMPLE)]) == 0
    assert capsys.readouterr().out.strip() == "0 error(s), 0 warning(s)"
    out = tmp_path / "settings.json"
    assert cli.main(["settings", "--file", str(SAMPLE), "--out", str(out)]) == 0
    assert cli.main(["settings", "--file", str(SAMPLE), "--check", str(out)]) == 1
    assert "4 problem(s)" in capsys.readouterr().out
    assert cli.main(["runs", "--from-json", str(SAMPLE.parent / "flowruns.json")]) == 0
    assert "5 run(s) in the last 7 day(s)" in capsys.readouterr().out
