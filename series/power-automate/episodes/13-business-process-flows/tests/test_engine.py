"""Walk instances through the process the way a user (or the Web API) would."""
import pytest

from bpfkit.engine import BpfError, GateError, Instance, evaluate
from bpfkit.webapi import ZERO, change_state, create_instance, move_stage, traversed_path

from conftest import sample

IDS = sample("stage-ids.json")


def test_small_request_skips_finance(process):
    i = Instance(process, sample("request-small.json"))
    assert i.active_path() == ["submit", "manager", "order", "close"]
    i.update(cts_ponumber="PO-1", cts_received="Yes")
    assert [i.next(), i.next(), i.next()] == ["manager", "order", "close"]
    i.finish()
    assert i.state == "Finished" and i.traversed == ["submit", "manager", "order", "close"]


def test_large_request_goes_through_finance(process):
    i = Instance(process, sample("request-large.json"))
    assert i.active_path() == ["submit", "manager", "finance", "order", "close"]
    for _ in range(4):
        i.next()
    assert i.active == "close"
    i.finish()


def test_the_branch_follows_the_values_not_the_history(process):
    i = Instance(process, {"cts_amount": 4999, "cts_justification": "x", "cts_managerdecision": "Approved"})
    i.next()
    assert i.next() == "order"
    j = Instance(process, {"cts_amount": 5000, "cts_justification": "x", "cts_managerdecision": "Approved"})
    j.next()
    assert j.next() == "finance"


def test_a_rejection_by_the_manager_does_not_reach_finance_even_for_large_amounts(process):
    i = Instance(process, {"cts_amount": 20000, "cts_justification": "x", "cts_managerdecision": "Rejected"})
    i.next()
    assert i.next() == "order"  # the branch is amount AND approved: the process then needs its own 'rejected' branch
    assert evaluate(process.stages["manager"].next["condition"], i.record) is False


def test_required_steps_gate_the_next_stage(process):
    i = Instance(process, sample("request-incomplete.json"))
    with pytest.raises(GateError) as e:
        i.next()
    assert e.value.missing == ["cts_justification"] and i.active == "submit"
    i.update(cts_justification="Laptops")
    assert i.next() == "manager"


def test_a_required_two_options_step_blocks_on_no():
    from bpfkit.engine import is_empty
    assert is_empty(False, "twoOptions") and is_empty(None, "twoOptions")
    assert not is_empty(True, "twoOptions")
    assert not is_empty(False, "text") and is_empty("  ", "text")


def test_previous_goes_back_and_the_branch_is_reevaluated(process):
    i = Instance(process, sample("request-large.json"))
    i.next(); i.next()
    assert i.active == "finance"
    assert i.previous() == "manager"
    i.update(cts_amount=100)
    assert i.next() == "order"
    assert i.traversed == ["submit", "manager", "order"]


def test_code_can_only_move_one_stage_at_a_time(process):
    i = Instance(process, sample("request-large.json"))
    with pytest.raises(BpfError, match="next or previous"):
        i.set_active("order")
    assert i.set_active("manager") == "manager"
    assert i.set_active("submit") == "submit"


def test_finish_only_at_the_last_stage_and_only_when_complete(process):
    i = Instance(process, sample("request-large.json"))
    with pytest.raises(BpfError, match="last stage"):
        i.finish()
    for _ in range(4):
        i.next()
    i.update(cts_received=None)
    with pytest.raises(GateError):
        i.finish()
    with pytest.raises(BpfError, match="finish the process"):
        i.next()


def test_abort_and_reactivate(process):
    i = Instance(process, sample("request-large.json"))
    i.next()
    i.abort()
    with pytest.raises(BpfError, match="Aborted"):
        i.next()
    i.reactivate()
    assert i.state == "Active" and i.active == "manager"
    with pytest.raises(BpfError):
        i.reactivate()


def test_webapi_payloads_follow_the_learn_examples(process):
    i = Instance(process, sample("request-large.json"))
    rec = "00000000-0000-0000-0000-0000000000f1"
    first = create_instance(i, IDS, "bpf_purchaserequestid", "cts_purchaserequests", rec)
    assert first == {"bpf_purchaserequestid@odata.bind": f"/cts_purchaserequests({rec})",
                     "activestageid@odata.bind": f"/processstages({IDS['submit']})"}  # no traversedpath for stage 1
    i.next(); i.next()
    body = move_stage(i, IDS)
    assert body["activestageid@odata.bind"] == f"/processstages({IDS['finance']})"
    assert body["traversedpath"] == ",".join(IDS[s] for s in ("submit", "manager", "finance"))
    later = create_instance(i, IDS, "bpf_purchaserequestid", "cts_purchaserequests", rec)
    assert later["traversedpath"] == traversed_path(i, IDS)  # required when not starting at the first stage
    assert change_state("abort") == {"statecode": 1, "statuscode": 3}
    assert change_state("reactivate") == {"statecode": 0, "statuscode": 1}
    assert change_state("finish") == {"statecode": 0, "statuscode": 2}
    assert ZERO.count("0") == 32
