"""Throttling, outages and bad requests: what is retried, how long it waits, and how the run fails loudly."""
from mockgraph import Fault

from conftest import page_calls


def test_429_waits_for_retry_after_then_continues(flow, harness, graph):
    graph.state.faults.append(Fault(429, page=2, retry_after=3))
    r = harness.run(flow)
    assert r.status == "Succeeded"
    assert harness.waits == [3.0]                                  # Retry-After wins over the policy interval
    second = page_calls(r)[1]
    assert second.attempts == [(429, 3.0), (200, None)]
    assert len(r.variables["usersWithoutManager"]) == 3


def test_503_without_retry_after_uses_the_exponential_policy(flow, harness, graph):
    graph.state.faults.append(Fault(503, page=1, times=2))
    r = harness.run(flow)
    assert r.status == "Succeeded"
    assert harness.waits == [10.0, 20.0]       # interval PT10S, doubling (flowkit's deterministic model)


def test_a_persistent_outage_fails_loudly_after_the_retries(flow, harness, graph):
    graph.state.faults.append(Fault(503, page=3, times=99))
    r = harness.run(flow)
    third = page_calls(r)[2]
    assert [s for s, _ in third.attempts] == [503] * 5               # 1 call + 4 retries (count: 4)
    assert harness.waits == [10.0, 20.0, 40.0, 80.0]
    assert r.variables["graphError"]["status"] == 503
    assert r.status_of("Get_all_pages") == "Succeeded"               # the loop ends cleanly (Page_done joins)
    assert r.status_of("Send_report") == "Skipped"                   # no half report
    (mail,) = harness.mail
    assert mail["emailMessage/To"] == "automation-admins@contoso.com"
    assert mail["emailMessage/Subject"] == "Directory check failed: Graph returned 503"
    assert "Page 3 of GET /users failed" in mail["emailMessage/Body"]
    assert r.status == "Failed" and r.terminate_error["code"] == "GraphCallFailed"


def test_a_400_is_not_retried(flow, harness, graph):
    r = harness.run(flow, page_size="1000")     # above Graph's maximum page size for /users
    first = page_calls(r)[0]
    assert first.attempts == [(400, None)]
    assert harness.waits == []
    assert r.variables["graphError"]["status"] == 400
    assert "between 1 and 999" in r.variables["graphError"]["message"]
    assert r.status == "Failed"


def test_a_wrong_secret_fails_at_the_token_and_never_calls_graph(flow, harness, graph):
    r = harness.run(flow, secret="wrong-secret")
    assert graph.graph_calls() == []
    assert r.variables["graphError"]["status"] == 401
    assert r.variables["graphError"]["message"] == "mock: wrong client id or secret"
    assert harness.waits == []                   # 401 isn't 408, 429 or 5xx: no retry
    assert r.status == "Failed"
