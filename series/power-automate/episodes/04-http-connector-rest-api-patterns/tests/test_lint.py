"""Lint rules for HTTP actions, Until loops and secrets (limits from the Power Automate limits page)."""
import copy

from flowkit import lint

from conftest import actions, paging_block


def messages(flow, level=None):
    return [f.message for f in lint(flow) if level is None or f.level == level]


def test_the_solution_flow_is_clean(flow):
    assert lint(flow) == []


def test_retry_count_and_interval_limits(flow):
    bad = copy.deepcopy(flow)
    paging_block(bad)["Get_users_page"]["inputs"]["retryPolicy"].update(count=91, interval="PT2S")
    errs = messages(bad, "error")
    assert any("count 91 must be between 1 and 90" in m for m in errs)
    assert any("interval PT2S must be between PT5S and P1D" in m for m in errs)


def test_secret_from_an_expression_needs_secure_inputs(flow):
    bad = copy.deepcopy(flow)
    del paging_block(bad)["Get_users_page"]["runtimeConfiguration"]
    assert any("Secure inputs is off" in m for m in messages(bad, "warning"))


def test_secret_retrieval_needs_secure_outputs(flow):
    bad = copy.deepcopy(flow)
    del actions(bad)["Get_client_secret"]["runtimeConfiguration"]
    assert any("without Secure outputs" in m for m in messages(bad, "warning"))


def test_until_needs_an_explicit_limit(flow):
    bad = copy.deepcopy(flow)
    del actions(bad)["Get_all_pages"]["limit"]
    assert any("60 iterations by default" in m for m in messages(bad, "warning"))
    bad["properties"]["definition"]["actions"]["Get_all_pages"]["limit"] = {"count": 6000}
    assert any("maximum of 5000" in m for m in messages(bad, "error"))


def test_plain_http_endpoint_is_flagged(flow):
    bad = copy.deepcopy(flow)
    paging_block(bad)["Get_users_page"]["inputs"]["uri"] = "http://api.contoso.com/v1/users"
    assert any("plain http://" in m for m in messages(bad, "warning"))


def test_every_connector_is_solution_aware(flow):
    refs = flow["properties"]["connectionReferences"]
    assert set(refs) == {"shared_commondataserviceforapps", "shared_office365"}
    assert all(r["connection"]["connectionReferenceLogicalName"].startswith("cts_") for r in refs.values())
