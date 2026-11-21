from conftest import FakeResponse, value
from apikit import ops

REC = "00000000-0000-0000-0000-00000000a004"
STEP = "00000000-0000-0000-0000-0000000005e1"


def test_call_resolves_the_alternate_key_then_posts_the_bound_action(api, stub, cfg):
    stub.on("GET", r"^mgl_projectrequests\(mgl_requestcode='PR-0004'\)",
            FakeResponse(200, {"mgl_projectrequestid": REC, "mgl_name": "Warehouse IoT sensors", "mgl_riskscore": None}))
    stub.on("POST", r"^mgl_projectrequests\(", FakeResponse(200, {
        "@odata.context": "...$metadata#Microsoft.Dynamics.CRM.mgl_AssessProjectRequestResponse",
        "RiskScore": 75, "RiskLevel": "High",
        "Reasons": "Budget 75,000 is at or over 50,000; No business justification for a large budget; Due in 10 day(s)"}))
    lines = []
    res = ops.cmd_call(api, cfg, "PR-0004", out=lines.append)
    (post,) = stub.sent("POST")
    assert post["url"] == f"mgl_projectrequests({REC})/Microsoft.Dynamics.CRM.mgl_AssessProjectRequest"
    assert post["json"] == {}
    assert res == {"RiskScore": 75, "RiskLevel": "High", "Reasons": res["Reasons"]}   # annotations dropped
    assert lines == ["PR-0004  Warehouse IoT sensors", "  RiskScore 75  RiskLevel High",
                     "   - Budget 75,000 is at or over 50,000", "   - No business justification for a large budget",
                     "   - Due in 10 day(s)", "  stored mgl_riskscore: (empty)"]


def test_unknown_code_is_a_clear_error(api, stub, cfg):
    import pytest
    from apikit.webapi import DataverseError
    with pytest.raises(DataverseError, match="no mgl_projectrequest with mgl_requestcode = PR-9999"):
        ops.find_request(api, cfg, "PR-9999")


def test_backfill_dry_run_then_apply(api, stub, cfg):
    stub.on("GET", r"^mgl_projectrequests\?", value({"mgl_projectrequestid": REC, "mgl_requestcode": "PR-0004"},
                                                    {"mgl_projectrequestid": "bad", "mgl_requestcode": "PR-0005"}))
    stub.on("POST", rf"^mgl_projectrequests\({REC}\)", FakeResponse(200, {"RiskScore": 75, "RiskLevel": "High", "Reasons": "x"}))
    stub.on("POST", r"^mgl_projectrequests\(bad\)", FakeResponse(400, {"error": {"code": "0x80040203", "message": "boom"}}))
    stub.on("PATCH", r"^mgl_projectrequests\(", FakeResponse(204))
    lines = []
    assert ops.cmd_backfill(api, cfg, apply=False, out=lines.append) == 1     # one failure -> exit 1
    assert stub.sent("PATCH") == []
    assert "mgl_riskscore eq null" in stub.sent("GET")[0]["url"] and "statecode eq 0" in stub.sent("GET")[0]["url"]
    assert lines[-1] == "dry run: add --apply to write the scores"
    lines.clear()
    ops.cmd_backfill(api, cfg, apply=True, out=lines.append)
    (patch,) = stub.sent("PATCH")
    assert patch["json"] == {"mgl_riskscore": 75} and patch["headers"]["If-Match"] == "*"
    assert "  + PR-0004   75  High" in lines and any("! PR-0005" in line for line in lines)


def registered(stub):
    stub.on("GET", r"^pluginassemblies\?", value({"pluginassemblyid": "a1"}))
    stub.on("GET", r"^plugintypes\?", value({"plugintypeid": "t1"}))
    stub.on("GET", r"^sdkmessageprocessingsteps\?", value(
        {"sdkmessageprocessingstepid": STEP, "name": "RiskScoreRefreshPlugin: Update", "asyncautodelete": True}))


def test_jobs_filters_by_step_and_shows_failures(api, stub, cfg):
    registered(stub)
    stub.on("GET", r"^asyncoperations\?", value(
        {"createdon": "2027-01-15T10:00:02Z", "statuscode": 31, "friendlymessage": "Plug-in failed",
         "message": "InvalidPluginExecutionException: RiskScoreRefreshPlugin failed. See the plug-in trace log.\n at ..."},
        {"createdon": "2027-01-15T09:59:00Z", "statuscode": 10, "friendlymessage": None}))
    lines = []
    assert ops.cmd_jobs(api, cfg, failed_only=False, out=lines.append) == 1
    (q,) = stub.sent("GET", "^asyncoperations")
    assert f"_owningextensionid_value eq {STEP}" in q["url"] and "statuscode eq 31" not in q["url"]
    assert lines[0] == "RiskScoreRefreshPlugin: Update [auto-delete on success]: 2 job(s)"
    assert lines[1].startswith("  2027-01-15T10:00:02  Failed") and "RiskScoreRefreshPlugin failed" in lines[2]
    assert "Waiting" in lines[3]
    ops.cmd_jobs(api, cfg, failed_only=True, out=lambda s: None)
    assert "statuscode eq 31" in stub.sent("GET", "^asyncoperations")[-1]["url"]


def test_jobs_without_registration(api, stub, cfg):
    stub.on("GET", r"^pluginassemblies\?", value())
    lines = []
    assert ops.cmd_jobs(api, cfg, failed_only=False, out=lines.append) == 1
    assert lines == ["no steps registered: run deploy first"]


def test_trace_prints_last_lines_and_explains_empty_results(api, stub, cfg):
    stub.on("GET", r"^plugintracelogs\?", value())
    lines = []
    assert ops.cmd_trace(api, cfg, out=lines.append) == 1 and "Rows are deleted after 24 hours" in lines[0]
    stub.on("GET", r"^plugintracelogs\?", value({
        "createdon": "2027-01-15T10:00:01Z", "typename": "MGLab.D365.Plugins.RiskScoreRefreshPlugin, MGLab.D365.Plugins",
        "messagename": "Update", "mode": 1, "depth": 1, "performanceexecutionduration": 41,
        "messageblock": "RiskScoreRefreshPlugin: Update mgl_projectrequest stage 40 mode 1 depth 1\nRisk score 30 -> 75 (High)."}))
    lines.clear()
    assert ops.cmd_trace(api, cfg, out=lines.append) == 0
    assert "startswith(typename,'MGLab.D365.Plugins.')" in stub.sent("GET")[-1]["url"]
    assert lines[0].split() == ["2027-01-15T10:00:01", "RiskScoreRefreshPlugin", "Update", "async", "depth", "1", "41", "ms"]
    assert lines[-1] == "    Risk score 30 -> 75 (High)."


def test_migration_hints():
    assert ops.migration_hint({"category": 3}).startswith("custom API")
    assert ops.migration_hint({"category": 0, "mode": 1}).startswith("real-time: a synchronous plug-in")
    assert ops.migration_hint({"category": 0, "mode": 0, "triggeroncreate": True,
                               "triggeronupdateattributelist": "mgl_budget"}) == \
        "cloud flow, Dataverse trigger on create/update (columns mgl_budget)"
    assert ops.migration_hint({"category": 0, "mode": 0, "ondemand": True}) == \
        "cloud flow with 'When a row is selected' (on demand)"


def test_workflow_inventory_excludes_managed_unless_asked(api, stub):
    stub.on("GET", r"^workflows\?", value({"name": "Notify on large budget", "category": 0, "mode": 0,
                                          "primaryentity": "mgl_projectrequest", "statecode": 1,
                                          "triggeroncreate": True, "triggeronupdateattributelist": None}))
    lines = []
    ops.cmd_workflows(api, include_managed=False, table=None, out=lines.append)
    q = stub.sent("GET")[-1]["url"]
    assert "(category eq 0 or category eq 3) and type eq 1 and ismanaged eq false" in q
    assert lines[0] == "1 classic workflow(s)/action(s) (unmanaged only; --all for managed)"
    assert lines[1].split("->")[1].strip() == "cloud flow, Dataverse trigger on create"
    ops.cmd_workflows(api, include_managed=True, table="account", out=lambda s: None)
    q = stub.sent("GET")[-1]["url"]
    assert "ismanaged eq" not in q and "primaryentity eq 'account'" in q
