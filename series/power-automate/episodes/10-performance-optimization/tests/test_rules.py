from conftest import actions, clone, codes, loop_of
from perfkit.rules import analyze


def test_slow_draft_findings(slow):
    assert codes(analyze(slow)) == ["P01", "P02", "P03", "P05"]


def test_tuned_flow_is_clean(fast):
    assert analyze(fast) == []


def test_p01_goes_away_with_concurrency(slow):
    loop_of(slow)["runtimeConfiguration"] = {"concurrency": {"repetitions": 10}}
    got = codes(analyze(slow))
    assert "P01" not in got
    assert "P04" in got  # the counter variable is now shared by 10 iterations


def test_p02_needs_a_filter_missing(slow):
    slow["properties"]["definition"]["actions"]["Get_all_requests"]["inputs"]["parameters"]["$filter"] = "Status eq 'Done'"
    assert "P02" not in codes(analyze(slow))


def test_p03_only_when_same_list(slow):
    loop = loop_of(slow)
    loop["actions"]["Get_item_again"]["inputs"]["parameters"]["table"] = "other list"
    assert "P03" not in codes(analyze(slow))


def test_p04_is_an_error_p05_a_warning(slow, fast):
    assert {f.level for f in analyze(slow) if f.code == "P05"} == {"warning"}
    loop = loop_of(fast)
    loop["actions"]["Count"] = {"type": "IncrementVariable", "runAfter": {}, "inputs": {"name": "n", "value": 1}}
    errs = [f for f in analyze(fast) if f.code == "P04"]
    assert errs and errs[0].level == "error"


def test_p06_loop_that_only_appends(fast):
    loop = loop_of(fast)
    loop["actions"] = {"Add": {"type": "AppendToArrayVariable", "runAfter": {}, "inputs": {"name": "a", "value": "@item()"}}}
    got = codes(analyze(fast))
    assert "P06" in got


def test_p07_concurrency_out_of_range(fast):
    for bad in (51, 100):
        f = clone(fast)
        loop_of(f)["runtimeConfiguration"]["concurrency"]["repetitions"] = bad
        assert "P07" in codes(analyze(f), "error")
    f = clone(fast)
    loop_of(f)["runtimeConfiguration"]["concurrency"]["repetitions"] = 50
    assert "P07" not in codes(analyze(f))


def test_p08_no_pagination_no_top(fast):
    g = actions(fast)["Get_done_requests"]
    del g["runtimeConfiguration"]
    assert "P08" not in codes(analyze(fast))  # $top still there
    del g["inputs"]["parameters"]["$top"]
    assert "P08" in codes(analyze(fast))


def test_p09_threshold_above_5000(fast):
    actions(fast)["Get_done_requests"]["runtimeConfiguration"]["paginationPolicy"]["minimumItemCount"] = 10000
    assert "P09" in codes(analyze(fast))


def test_p10_trigger_condition():
    flow = {"properties": {"definition": {"triggers": {"When_an_item_is_created": {
        "type": "OpenApiConnectionNotification",
        "inputs": {"host": {"operationId": "GetOnNewItems"}}}}, "actions": {}}}}
    assert codes(analyze(flow)) == ["P10"]
    flow["properties"]["definition"]["triggers"]["When_an_item_is_created"]["conditions"] = [{"expression": "@true"}]
    assert analyze(flow) == []


def test_nested_loops_not_flagged_for_concurrency():
    inner = {"type": "Foreach", "runAfter": {}, "foreach": "@variables('x')", "actions": {
        "Call": {"type": "OpenApiConnection", "runAfter": {}, "inputs": {"host": {"operationId": "PatchItem"}, "parameters": {}}}}}
    flow = {"properties": {"definition": {"triggers": {}, "actions": {"Outer": {
        "type": "Foreach", "runAfter": {}, "foreach": "@variables('y')", "runtimeConfiguration": {"concurrency": {"repetitions": 5}},
        "actions": {"Inner": inner}}}}}}
    assert "P01" not in codes(analyze(flow))
