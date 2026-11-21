"""The two flows of the PurchaseBpf solution: lint, dry runs, and the trigger gotchas."""
import pytest

from flowkit import run_flow
from flowkit.lint import lint

from conftest import NOW, load_flow, sample

STEP = "Financereviewstep"
COPY = "Copyactivestagetorequest"


def mocks(**over):
    m = sample("mocks-finance-approves.json")
    m.update(over)
    return m


@pytest.mark.parametrize("prefix", [STEP, COPY])
def test_flows_lint_clean(prefix):
    assert [str(f) for f in lint(load_flow(prefix))] == []


def run_step(m):
    return run_flow(load_flow(STEP), sample("step-payload.json"), m, now=NOW)


def test_finance_approves_records_the_decision_and_completes_the_step():
    r = run_step(mocks())
    assert r.status == "Succeeded"
    rec = r.actions["Record_approval"].inputs["parameters"]
    assert rec["entityName"] == "cts_purchaserequests"
    assert rec["recordId"] == "00000000-0000-0000-0000-0000000000f1"
    assert rec["item/cts_financedecision"] == 444460000
    done = r.actions["Complete_flow_step"].inputs["parameters"]
    assert done["entityName"] == "processsessions"
    assert done["recordId"] == "00000000-0000-0000-0000-0000000000c1"  # FlowsWorkflowLogId
    assert (done["item/statecode"], done["item/statuscode"]) == (1, 4)


def test_finance_rejects_and_the_step_still_completes():
    r = run_step(mocks(Finance_approval={"status": "Succeeded", "body": {"outcome": "Reject"}}))
    assert r.status == "Succeeded"
    assert r.ran("Record_rejection") and not r.ran("Record_approval")
    assert r.actions["Record_rejection"].inputs["parameters"]["item/cts_financedecision"] == 444460001
    assert r.ran("Complete_flow_step_rejected")


def test_a_timed_out_approval_fails_the_step_instead_of_leaving_it_processing():
    r = run_step(mocks(Finance_approval={"status": "TimedOut"}))
    assert r.status == "Succeeded"  # the handled timeout does not fail the run (Step_result joins the paths)
    done = r.actions["Fail_flow_step_on_timeout"].inputs["parameters"]
    assert (done["item/statecode"], done["item/statuscode"]) == (1, 6)
    assert r.status_of("Finance_decision") == "Skipped"
    assert r.actions["Step_result"].outputs == "TimedOut"


def test_without_the_join_the_handled_timeout_fails_the_run():
    flow = load_flow(STEP)
    del flow["properties"]["definition"]["actions"]["Step_result"]
    r = run_flow(flow, sample("step-payload.json"), mocks(Finance_approval={"status": "TimedOut"}), now=NOW)
    assert r.status == "Failed"


def test_the_approval_has_a_timeout():
    a = load_flow(STEP)["properties"]["definition"]["actions"]["Finance_approval"]
    assert a["limit"]["timeout"] == "P3D"


def test_copy_flow_does_not_filter_on_the_lookup_column():
    """Learn: lookup columns aren't supported in 'Select columns', so activestageid can't be the filter."""
    trig = load_flow(COPY)["properties"]["definition"]["triggers"]["When_the_process_instance_moves"]
    cols = trig["inputs"]["parameters"]["subscriptionRequest/filteringattributes"].split(",")
    assert "activestageid" not in cols and "_activestageid_value" not in cols
    assert cols == ["traversedpath", "statecode"]


def test_copy_flow_writes_the_stage_name_to_the_request():
    row = {"_activestageid_value": "00000000-0000-0000-0000-0000000000a3",
           "_bpf_purchaserequestid_value": "00000000-0000-0000-0000-0000000000f1"}
    m = {"Get_active_stage": {"status": "Succeeded", "body": {"stagename": "Finance review"}},
         "Copy_stage_to_request": {"status": "Succeeded", "body": {}}}
    r = run_flow(load_flow(COPY), row, m, now=NOW)
    assert r.status == "Succeeded"
    p = r.actions["Copy_stage_to_request"].inputs["parameters"]
    assert p["item/cts_activestage"] == "Finance review"
    assert p["recordId"] == row["_bpf_purchaserequestid_value"]
