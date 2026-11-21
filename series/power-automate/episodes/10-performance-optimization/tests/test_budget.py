import pytest
from conftest import FAST, SLOW
from perfkit import budget
from perfkit.sharepoint import ThrottledError, make_list


@pytest.mark.parametrize("n", [100, 1000, 2000, 4000])
def test_formulas(n):
    d = int(n * 0.4)
    slow = budget.measure(SLOW, n)
    fast = budget.measure(FAST, n)
    assert slow.to_archive == fast.to_archive == d
    assert slow.actions == 6 + 2 * n + 2 * d
    assert fast.actions == 6 + d  # trigger, Cutoff, Get, If, Apply to each, Send summary + one patch per item
    assert slow.archived == fast.archived == d
    assert slow.status == fast.status == "Succeeded"


def test_exact_numbers_used_in_the_video():
    got = {n: (budget.measure(SLOW, n), budget.measure(FAST, n)) for n in (1000, 2000, 4000)}
    assert [(s.actions, s.sharepoint_calls, f.actions, f.sharepoint_calls) for s, f in got.values()] == [
        (2806, 1401, 406, 401), (5606, 2801, 806, 801), (11206, 5601, 1606, 1601)]


def test_low_profile_limit():
    assert budget.measure(SLOW, 4000).over("Low")
    assert not budget.measure(SLOW, 2000).over("Low")
    assert not budget.measure(FAST, 4000).over("Low")
    assert not budget.measure(SLOW, 4000).over("Medium")


def test_throttle_floor():
    c = budget.measure(SLOW, 4000)
    assert c.throttle_floor_minutes == pytest.approx(5601 / 600)
    assert budget.measure(FAST, 4000).throttle_floor_minutes < c.throttle_floor_minutes / 3


def test_pagination_off_silently_misses_items():
    """Learn, known limitation: with pagination off and 6,000 items, a filtered Get items only looks at the first 5,000.
    Here the old Done items sit at the end, so the flow succeeds and archives nothing."""
    lst = make_list(6000, done_old_fraction=0.0)
    for i in lst.items[5500:]:
        i["Status"] = {"Value": "Done"}
        i["DoneOn"] = "2026-01-01T00:00:00Z"
    flow = __import__("json").loads(FAST.read_text())
    loop_pag = flow["properties"]["definition"]["actions"]["Get_done_requests"]
    del loop_pag["runtimeConfiguration"]
    loop_pag["inputs"]["parameters"]["$top"] = 5000
    c = budget.measure(flow, lst, name="no-pagination")
    assert c.status == "Succeeded" and c.archived == 0 and c.to_archive == 500
    # with pagination on, the same list is archived
    lst2 = make_list(6000, done_old_fraction=0.0)
    for i in lst2.items[5500:]:
        i["Status"] = {"Value": "Done"}
        i["DoneOn"] = "2026-01-01T00:00:00Z"
    assert budget.measure(FAST, lst2).archived == 500


def test_unindexed_filter_over_5000_items_is_throttled():
    lst = make_list(6000)
    lst.indexed = {"Status"}
    with pytest.raises(Exception) as e:
        budget.measure(FAST, lst)
    assert "threshold" in str(e.value) or isinstance(e.value, ThrottledError)


def test_small_list_does_not_need_indexes():
    lst = make_list(1000)
    lst.indexed = set()
    assert budget.measure(FAST, lst).archived == 400
