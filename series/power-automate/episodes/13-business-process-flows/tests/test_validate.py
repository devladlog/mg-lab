"""Every design rule is proven twice: the real definition passes, a broken copy trips exactly that rule."""
import copy

from bpfkit.model import Process
from bpfkit.validate import MAX_STAGES, MAX_STEPS, validate, validate_set


def codes(d):
    return sorted(f.code for f in validate(Process.from_dict(d)))


def test_the_purchase_process_is_clean(process):
    assert validate(process) == []


def test_more_than_30_stages_is_an_error(definition):
    d = copy.deepcopy(definition)
    prev = "close"
    for i in range(MAX_STAGES):
        sid = f"extra{i}"
        d["stages"][prev]["next"] = sid
        d["stages"][sid] = {"name": sid, "table": "cts_purchaserequest", "steps": [], "next": None}
        prev = sid
    assert "BPF001" in codes(d)


def test_more_than_30_steps_in_a_stage_is_an_error(definition):
    d = copy.deepcopy(definition)
    d["stages"]["order"]["steps"] = [{"column": f"c{i}", "type": "text"} for i in range(MAX_STEPS + 1)]
    assert "BPF002" in codes(d)


def test_more_than_five_tables_is_an_error(definition):
    d = copy.deepcopy(definition)
    for i, sid in enumerate(["manager", "finance", "order", "close"], start=1):
        d["stages"][sid]["table"] = f"cts_table{i}"
    assert "BPF003" not in codes(d)  # the primary table plus four others: five is allowed
    d["stages"]["close"]["next"] = "extra"
    d["stages"]["extra"] = {"name": "Extra", "table": "cts_table6", "steps": [], "next": None}
    assert "BPF003" in codes(d)


def test_the_first_stage_must_be_on_the_primary_table(definition):
    d = copy.deepcopy(definition)
    d["primaryTable"] = "account"
    assert "BPF012" in codes(d)


def test_branch_rule_must_use_a_step_of_the_preceding_stage(definition):
    """The gotcha: amount is entered in 'Submit', but the condition sits after 'Manager review'."""
    d = copy.deepcopy(definition)
    d["stages"]["manager"]["steps"] = [s for s in d["stages"]["manager"]["steps"] if s["column"] != "cts_amount"]
    findings = validate(Process.from_dict(d))
    (f,) = [x for x in findings if x.code == "BPF006"]
    assert "cts_amount" in f.message and "immediately precedes" in f.message


def test_and_or_cannot_be_mixed(definition):
    d = copy.deepcopy(definition)
    d["stages"]["manager"]["next"]["condition"]["rules"][1]["join"] = "or"
    assert "BPF005" in codes(d)


def test_peer_branches_must_merge_in_one_stage(definition):
    """'No' goes to order, 'Yes' goes to finance which now ends the process: merge and end at the same time."""
    d = copy.deepcopy(definition)
    d["stages"]["finance"]["next"] = None
    assert "BPF007" not in codes(d)  # both branches end the process or only one reaches 'order': fine
    d = copy.deepcopy(definition)
    d["stages"]["finance"]["next"] = {"condition": {"op": "and", "rules": [
        {"column": "cts_financedecision", "operator": "eq", "value": "Approved"}]}, "yes": "order", "no": "reject"}
    d["stages"]["reject"] = {"name": "Reject", "table": "cts_purchaserequest", "steps": [], "next": None}
    assert "BPF007" in codes(d)


def test_unreachable_and_unknown_stages(definition):
    d = copy.deepcopy(definition)
    d["stages"]["orphan"] = {"name": "Orphan", "table": "cts_purchaserequest", "steps": [], "next": None}
    d["stages"]["order"]["next"] = "nowhere"
    c = codes(d)
    assert c.count("BPF009") >= 2


def test_forward_loops_are_rejected(definition):
    d = copy.deepcopy(definition)
    d["stages"]["close"]["next"] = "submit"
    assert "BPF010" in codes(d)


def test_required_two_options_warns(definition):
    d = copy.deepcopy(definition)
    d["stages"]["close"]["steps"] = [{"column": "cts_received", "type": "twoOptions", "required": True}]
    (f,) = [x for x in validate(Process.from_dict(d)) if x.code == "BPF008"]
    assert f.level == "warning" and "Choice" in f.message


def test_stage_exit_workflow_on_last_stage_warns(definition):
    d = copy.deepcopy(definition)
    d["stages"]["close"]["exitWorkflows"] = ["Notify requester"]
    (f,) = [x for x in validate(Process.from_dict(d)) if x.code == "BPF011"]
    assert "global workflow" in f.message


def test_more_than_ten_active_processes_per_table(process):
    assert validate_set([process] * 10) == []
    (f,) = validate_set([process] * 11)
    assert f.code == "BPF015" and "10" in f.message
