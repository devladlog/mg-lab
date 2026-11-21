import pytest

from conftest import (APPROVE, CLOSE, FINANCE, INST, REC, SUBMIT, WF, FakeResponse, bpf_environment, created,
                      value, with_instance)
from bpfkit import backfill, cli, definition, instances, path
from bpfkit.webapi import DataverseError


def load(api, cfg):
    return definition.load(api, cfg["bpf"], cfg["table"])


def test_definition_reads_table_entity_set_lookup_and_stages(api, stub, cfg):
    bpf_environment(stub)
    d = load(api, cfg)
    assert (d.unique_name, d.entity_set, d.lookup, d.nav) == ("mgl_projectapproval", "mgl_projectapprovals",
                                                              "bpf_mgl_projectrequestid", "bpf_mgl_projectrequestid")
    assert d.lookup_value == "_bpf_mgl_projectrequestid_value"
    assert d.stage_id("finance review") == FINANCE and d.stage_name(f"{{{CLOSE.upper()}}}") == "Close"
    (wf,) = stub.sent("GET", "^workflows")
    assert "category eq 4 and name eq 'Project Approval'" in wf["url"]
    (ps,) = stub.sent("GET", "^processstages")
    assert f"processid/workflowid eq {WF}" in ps["url"]       # the filter from Learn's example


def test_draft_bpf_is_refused_with_a_hint(api, stub, cfg):
    bpf_environment(stub, statecode=0)
    with pytest.raises(DataverseError, match="activate it first"):
        load(api, cfg)


def test_unknown_bpf_and_unknown_stage(api, stub, cfg):
    stub.on("GET", r"^workflows\?", value())
    with pytest.raises(DataverseError, match="no business process flow named"):
        load(api, cfg)
    bpf_environment(stub)
    with pytest.raises(KeyError, match="Submit, Close, Approve, Finance Review"):
        load(api, cfg).stage_id("Deliver")


def test_status_shows_all_processes_and_the_active_path(api, stub, cfg):
    bpf_environment(stub)
    with_instance(stub, stage_id=FINANCE, traversed=f"{SUBMIT},{FINANCE}")
    stub.on("GET", r"^RetrieveProcessInstances\(", value({"name": "Project Approval", "processstageid": FINANCE}))
    lines = []
    assert cli.cmd_status(api, load(api, cfg), cfg, "PR-0004", out=lines.append) == 0
    (rpi,) = stub.sent("GET", "^RetrieveProcessInstances")
    assert rpi["url"] == f"RetrieveProcessInstances(EntityLogicalName=@p1,EntityId=@p2)?@p1='mgl_projectrequest'&@p2={REC}"
    (rap,) = stub.sent("GET", "^RetrieveActivePath")
    assert rap["url"] == f"RetrieveActivePath(ProcessInstanceId=@p1)?@p1={INST}"
    assert lines[1] == "  process instance: Project Approval  active stage Finance Review"
    assert lines[-1] == "  active path: [x] Submit  [>] Finance Review  [ ] Approve  [ ] Close"


def test_status_without_instance_suggests_backfill(api, stub, cfg):
    bpf_environment(stub)
    stub.on("GET", r"^RetrieveProcessInstances\(", value())
    stub.on("GET", r"^mgl_projectapprovals\?", value())
    lines = []
    assert cli.cmd_status(api, load(api, cfg), cfg, "PR-0004", out=lines.append) == 1
    assert "backfill" in lines[-1]


def test_next_patches_active_stage_and_traversed_path(api, stub, cfg):
    bpf_environment(stub)
    with_instance(stub)
    d = load(api, cfg)
    inst = instances.instances_for(api, d, REC)[0]
    mv = instances.move(api, d, inst, "next")
    (patch,) = stub.sent("PATCH")
    assert patch["url"] == f"mgl_projectapprovals({INST})" and patch["headers"]["If-Match"] == "*"
    assert patch["json"] == {"activestageid@odata.bind": f"/processstages({FINANCE})",
                             "traversedpath": f"{SUBMIT},{FINANCE}"}
    assert "MSCRM.SolutionUniqueName" not in patch["headers"]      # instances are data, not solution components
    assert mv.target == FINANCE


def test_next_under_threshold_skips_finance_review(api, stub, cfg):
    bpf_environment(stub)
    with_instance(stub, path=(SUBMIT, APPROVE, CLOSE))            # server-evaluated branch: budget < 50,000
    d = load(api, cfg)
    instances.move(api, d, instances.instances_for(api, d, REC)[0], "next")
    assert stub.sent("PATCH")[0]["json"]["activestageid@odata.bind"] == f"/processstages({APPROVE})"


def test_dry_run_sends_nothing(api, stub, cfg):
    bpf_environment(stub)
    with_instance(stub)
    lines = []
    cli.cmd_move(api, load(api, cfg), cfg, "PR-0004", "next", True, out=lines.append)
    assert not stub.sent("PATCH") and lines[0] == "PR-0004: would move Submit -> Finance Review"


def test_moving_a_finished_instance_is_refused(api, stub, cfg):
    bpf_environment(stub)
    with_instance(stub, stage_id=CLOSE, traversed=f"{SUBMIT},{APPROVE},{CLOSE}", statuscode=2)
    d = load(api, cfg)
    with pytest.raises(path.StageMoveError, match="Finished"):
        instances.move(api, d, instances.instances_for(api, d, REC)[0], "back")


def test_finish_only_at_last_stage(api, stub, cfg):
    bpf_environment(stub)
    with_instance(stub, stage_id=APPROVE, traversed=f"{SUBMIT},{APPROVE}", path=(SUBMIT, APPROVE, CLOSE))
    d = load(api, cfg)
    with pytest.raises(path.StageMoveError, match="last stage \\(Close\\)"):
        instances.finish(api, d, instances.instances_for(api, d, REC)[0])
    with_instance(stub, stage_id=CLOSE, traversed=f"{SUBMIT},{APPROVE},{CLOSE}", path=(SUBMIT, APPROVE, CLOSE))
    instances.finish(api, d, instances.instances_for(api, d, REC)[0])
    assert stub.sent("PATCH")[-1]["json"] == {"statecode": 0, "statuscode": 2}


def test_abandon_and_reactivate_payloads(api, stub, cfg):
    bpf_environment(stub)
    with_instance(stub)
    d = load(api, cfg)
    inst = instances.instances_for(api, d, REC)[0]
    instances.abandon(api, d, inst)
    instances.reactivate(api, d, inst)
    assert [p["json"] for p in stub.sent("PATCH")] == [{"statecode": 1, "statuscode": 3}, {"statecode": 0, "statuscode": 1}]


def test_unknown_request_code(api, stub, cfg):
    bpf_environment(stub)
    with pytest.raises(DataverseError, match="no mgl_projectrequest with mgl_requestcode = PR-9999"):
        instances.find_record(api, "mgl_projectrequests", "mgl_requestcode", "PR-9999", "mgl_projectrequest")


def records(*pairs):
    return value(*[{"mgl_projectrequestid": rid, "mgl_requestcode": code} for rid, code in pairs])


def test_backfill_plans_only_records_without_an_instance(api, stub, cfg):
    bpf_environment(stub)
    stub.on("GET", r"^mgl_projectapprovals\?\$select=_bpf_mgl_projectrequestid_value,traversedpath$",
            value({"_bpf_mgl_projectrequestid_value": "r1", "traversedpath": f"{SUBMIT},{APPROVE}"}))
    stub.on("GET", r"^mgl_projectrequests\?", records(("r1", "PR-0001"), ("r2", "PR-0002"), ("r3", "PR-0003")))
    plan = backfill.plan(api, load(api, cfg), cfg)
    assert plan.first_stage_id == SUBMIT and [m["code"] for m in plan.missing] == ["PR-0002", "PR-0003"]


def test_backfill_apply_creates_at_first_stage_and_continues_after_a_failure(api, stub, cfg):
    bpf_environment(stub)
    stub.on("GET", r"^mgl_projectapprovals\?\$select=_bpf", value())
    stub.on("GET", r"^mgl_projectrequests\?", records(("r2", "PR-0002"), ("r3", "PR-0003")))
    calls = {"n": 0}

    def post(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(403, {"error": {"code": "0x80040220", "message": "missing prvCreatemgl_projectapproval"}})
        return created("mgl_projectapprovals")
    stub.on("POST", r"^mgl_projectapprovals$", post)
    d = load(api, cfg)
    plan = backfill.apply(api, d, cfg, backfill.plan(api, d, cfg), out=lambda s: None)
    assert plan.failed == ["PR-0002"] and plan.created == ["PR-0003"]
    body = stub.sent("POST", "^mgl_projectapprovals$")[1]["json"]
    assert body == {"bpf_mgl_projectrequestid@odata.bind": "/mgl_projectrequests(r3)",
                    "activestageid@odata.bind": f"/processstages({SUBMIT})"}


def test_backfill_refuses_a_first_stage_that_contradicts_existing_instances(api, stub, cfg):
    bpf_environment(stub)
    stub.on("GET", r"^mgl_projectapprovals\?\$select=_bpf", value({"_bpf_mgl_projectrequestid_value": "r1",
                                                                    "traversedpath": f"{APPROVE},{CLOSE}"}))
    with pytest.raises(ValueError, match="existing instances start at: Approve"):
        backfill.plan(api, load(api, cfg), cfg)


def test_report_from_sample_json_and_fail_on_stuck(capsys):
    from conftest import ROOT
    sample = str(ROOT / "sample" / "project-approval-instances.json")
    assert cli.main(["report", "--from-json", sample, "--now", "2027-01-15"]) == 0
    out = capsys.readouterr().out
    assert "Project Approval: 18 instances (1 aborted, 15 active, 2 finished)" in out
    assert "Finance Review        3     10d    6.0  2 over 3 d" in out
    assert cli.main(["report", "--from-json", sample, "--now", "2027-01-15", "--fail-on-stuck"]) == 1
