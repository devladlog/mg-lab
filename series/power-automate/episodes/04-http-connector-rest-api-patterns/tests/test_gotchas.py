"""Mistakes this episode is about, reproduced on purpose."""
import copy

from flowkit import lint
from mockgraph import Fault

from conftest import actions, page_calls, paging_block


def test_without_a_retry_policy_an_outage_takes_hours_to_surface(flow, harness, graph):
    bad = copy.deepcopy(flow)
    del paging_block(bad)["Get_users_page"]["inputs"]["retryPolicy"]
    graph.state.faults.append(Fault(503, page=1, times=99))
    r = harness.run(bad)
    attempts = page_calls(r)[0].attempts
    assert len(attempts) == 13                       # Power Automate default: up to 12 retries (Medium/High)
    assert max(harness.waits) == 3600                # last intervals around an hour (flowkit's model of the curve)
    assert sum(harness.waits) / 3600 > 3             # hours before anyone hears about it
    assert any("no retryPolicy" in f.message for f in lint(bad))


def test_rebuilding_the_next_page_url_with_skip_breaks(flow, harness, graph):
    # Tempting: compute page N yourself. /users doesn't support $skip; the nextLink is opaque.
    bad = copy.deepcopy(flow)
    paging_block(bad)["Set_next_link"]["inputs"]["value"] = (
        "@{if(empty(body('Get_users_page')?['@odata.nextLink']), '', "
        "concat(first(split(variables('nextLink'), '&$skip=')), '&$skip=', string(mul(variables('pages'), 2))))}")
    r = harness.run(bad)
    assert r.variables["graphError"]["status"] == 400
    assert "$skip isn't supported" in r.variables["graphError"]["message"]
    assert r.status == "Failed"


def test_a_handled_failure_still_fails_the_loop_without_the_join(flow, harness, graph):
    # Episode 2's lesson inside a loop: remove Page_done and the iteration ends on a skipped Set_next_link.
    bad = copy.deepcopy(flow)
    del paging_block(bad)["Page_done"]
    graph.state.faults.append(Fault(400, page=1))
    r = harness.run(bad)
    assert r.status_of("Get_all_pages") == "Failed"
    assert any("marks the scope Failed" in f.message for f in lint(bad))


def test_hard_coded_secret_is_an_error(flow):
    bad = copy.deepcopy(flow)
    paging_block(bad)["Get_users_page"]["inputs"]["authentication"]["secret"] = "abc~123"
    assert any(f.level == "error" and "hard-coded credential" in f.message for f in lint(bad))
