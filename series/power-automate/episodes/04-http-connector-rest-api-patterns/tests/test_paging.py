"""Follow @odata.nextLink until it's gone, then report enabled users without a manager."""
from conftest import page_calls


def test_all_pages_are_read_and_only_enabled_users_without_a_manager_are_reported(flow, harness, graph):
    r = harness.run(flow)
    assert r.status == "Succeeded"
    assert r.actions["Get_all_pages"].iterations == 4          # 7 users, 2 per page
    assert r.variables["pages"] == 4
    assert len(graph.graph_calls()) == 4
    names = sorted(u["displayName"] for u in r.variables["usersWithoutManager"])
    assert names == ["Casey Demo", "Dana Director", "Riley Contractor"]   # Sam Service is disabled: not reported
    (mail,) = harness.mail
    assert mail["emailMessage/To"] == "purchasing-team@contoso.com"
    assert mail["emailMessage/Subject"] == "3 enabled users have no manager in Entra"
    assert "Checked 4 page(s) of users." in mail["emailMessage/Body"]
    assert mail["emailMessage/Body"].index("Casey Demo") < mail["emailMessage/Body"].index("Riley Contractor")  # sorted


def test_the_next_link_is_used_as_an_opaque_url(flow, harness, graph):
    harness.run(flow)
    calls = graph.graph_calls()
    first, rest = calls[0]["query"], [c["query"] for c in calls[1:]]
    assert first["$top"] == "2" and "$skiptoken" not in first
    assert all("$skiptoken" in q and "$skip" not in q for q in rest)
    # The original $select, $expand and $top travel inside every nextLink
    assert all(q["$select"] == first["$select"] and q["$expand"] == first["$expand"] and q["$top"] == "2" for q in rest)


def test_one_big_page_means_one_call(flow, harness, graph):
    r = harness.run(flow, page_size="999")    # Graph: default page 100, maximum 999 for /users
    assert r.actions["Get_all_pages"].iterations == 1
    assert len(graph.graph_calls()) == 1
    assert len(r.variables["usersWithoutManager"]) == 3


def test_every_call_sends_a_bearer_token_and_the_token_is_fetched_once(flow, harness, graph):
    harness.run(flow)
    assert all(c["auth"].startswith("Bearer mock-") for c in graph.graph_calls())
    token_calls = [c for c in graph.state.log if c["path"].endswith("/oauth2/v2.0/token")]
    assert len(token_calls) == 1
    assert token_calls[0]["query"]["grant_type"] == "client_credentials"
    assert token_calls[0]["query"]["scope"] == graph.url + "/.default"


def test_no_email_when_everyone_has_a_manager(flow, harness, graph):
    for u in graph.state.users:
        u["managerId"] = u["managerId"] or "00000000-0000-0000-0000-000000000401"
    r = harness.run(flow)
    assert r.status == "Succeeded"
    assert harness.mail == []
    assert r.status_of("Send_report") == "Skipped"


def test_null_and_missing_manager_are_treated_the_same(flow):
    from flowkit.expr import Context, evaluate
    where = flow["properties"]["definition"]["actions"]["Get_all_pages"]["actions"]["Without_manager_on_page"]["inputs"]["where"]
    for user in ({"accountEnabled": True}, {"accountEnabled": True, "manager": None}):
        ctx = Context()
        ctx.item_stack.append(user)
        assert evaluate(where, ctx) is True
    ctx = Context()
    ctx.item_stack.append({"accountEnabled": True, "manager": {"id": "00000000-0000-0000-0000-000000000401"}})
    assert evaluate(where, ctx) is False


def test_each_page_records_its_own_call(flow, harness):
    r = harness.run(flow)
    assert [c.outputs["statusCode"] for c in page_calls(r) if c.outputs != "<secured: hidden in run history>"] == [200] * 4
