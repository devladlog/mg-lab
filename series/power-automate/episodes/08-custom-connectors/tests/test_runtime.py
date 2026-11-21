"""The request the connector's files produce, operation by operation."""
import base64

import pytest

from connectorkit import Connection, Runtime, Response
from connectorkit.runtime import InputError

from conftest import mutate

CONN = Connection("contoso-it-bot", "ghp_demo_0000")


def build(connector, op, inputs, callback=None):
    return Runtime(connector, lambda r: Response(200)).build_request(op, inputs, CONN, callback)


def test_get_the_current_user_is_https_host_path(connector):
    r = build(connector, "GetAuthenticatedUser", {})
    assert (r.method, r.url, r.body) == ("GET", "https://api.github.com/user", None)


def test_basic_authentication_is_user_colon_token_in_base64(connector):
    r = build(connector, "GetAuthenticatedUser", {})
    assert r.headers["authorization"] == "Basic " + base64.b64encode(b"contoso-it-bot:ghp_demo_0000").decode()


def test_the_three_policies_set_the_headers(connector):
    h = build(connector, "GetAuthenticatedUser", {}).headers
    assert h["x-github-api-version"] == "2022-11-28"
    assert h["accept"] == "application/vnd.github+json"
    assert h["user-agent"] == "Contoso-IT-GitHub-connector"


def test_skip_keeps_a_header_that_is_already_there_and_override_replaces_it(connector):
    rt = Runtime(connector, lambda r: Response(200))
    headers = {"user-agent": "mine", "accept": "text/plain"}
    rt._policies(headers, "AddIssueComment")
    assert headers["user-agent"] == "mine" and headers["accept"] == "application/vnd.github+json"


def test_append_is_not_implemented_because_the_join_is_not_documented(connector):
    bad = mutate(connector, lambda d, p: p["properties"]["policyTemplateInstances"][1]["parameters"].update({"x-ms-apimTemplateParameter.existsAction": "append"}))
    with pytest.raises(NotImplementedError):
        build(bad, "GetAuthenticatedUser", {})


def test_a_policy_with_operation_names_runs_only_for_those(connector):
    c = mutate(connector, lambda d, p: p["properties"]["policyTemplateInstances"][0]["parameters"].update({"x-ms-apimTemplate-operationName": ["AddIssueComment"]}))
    assert "x-github-api-version" in build(c, "AddIssueComment", {"owner": "a", "repo": "b", "issue_number": 1, "body": {"body": "x"}}).headers
    assert "x-github-api-version" not in build(c, "GetAuthenticatedUser", {}).headers


def test_the_comment_operation_builds_the_documented_request(connector):
    r = build(connector, "AddIssueComment", {"owner": "contoso", "repo": "it-automation", "issue_number": 7, "body": {"body": "Hello"}})
    assert r.method == "POST"
    assert r.url == "https://api.github.com/repos/contoso/it-automation/issues/7/comments"
    assert r.body == {"body": "Hello"} and r.headers["content-type"] == "application/json"


def test_path_parameters_are_url_encoded_once_by_default(connector):
    r = build(connector, "AddIssueComment", {"owner": "con toso", "repo": "a/b", "issue_number": 1, "body": {"body": "x"}})
    assert r.url == "https://api.github.com/repos/con%20toso/a%2Fb/issues/1/comments"


def test_x_ms_url_encoding_double_encodes_twice(connector):
    c = mutate(connector, lambda d, p: d["paths"]["/repos/{owner}/{repo}/issues/{issue_number}/comments"]["post"]["parameters"][1].update({"x-ms-url-encoding": "double"}))
    r = build(c, "AddIssueComment", {"owner": "o", "repo": "a b", "issue_number": 1, "body": {"body": "x"}})
    assert "/repos/o/a%2520b/issues" in r.url


def test_missing_required_inputs_are_refused_before_any_call(connector):
    with pytest.raises(InputError, match="issue_number"):
        build(connector, "AddIssueComment", {"owner": "o", "repo": "r", "body": {"body": "x"}})
    with pytest.raises(InputError, match="body.body"):
        build(connector, "AddIssueComment", {"owner": "o", "repo": "r", "issue_number": 1, "body": {}})


def test_the_trigger_registers_issues_events_as_json_with_the_callback_url(connector):
    r = build(connector, "WhenAnIssueIsOpened", {"owner": "contoso", "repo": "it-automation"}, "https://flow.example.com/cb")
    assert r.url == "https://api.github.com/repos/contoso/it-automation/hooks"
    assert r.body == {"name": "web", "active": True, "events": ["issues"],
                      "config": {"url": "https://flow.example.com/cb", "content_type": "json", "insecure_ssl": "0"}}


def test_makers_cannot_override_internal_fields(connector):
    r = build(connector, "WhenAnIssueIsOpened", {"owner": "o", "repo": "r", "body": {"events": ["push"], "config": {"content_type": "form"}}}, "https://x.example/cb")
    assert r.body["events"] == ["issues"] and r.body["config"]["content_type"] == "json"


def test_testing_a_connection_calls_the_declared_operation(connector):
    seen = []
    rt = Runtime(connector, lambda r: (seen.append(r), Response(200, body={"login": "x"}))[1])
    rt.test_connection(CONN)
    assert [(r.method, r.url) for r in seen] == [("GET", "https://api.github.com/user")]


def test_unsubscribe_is_a_delete_on_the_location_header_with_the_same_connection(world):
    w = world
    sub = w.platform.turn_on()
    assert sub.location == "https://api.github.com/repos/contoso/it-automation/hooks/1"
    res = w.platform.turn_off()
    assert res.status == 204
    last = w.gh.requests[-1]
    assert (last.method, last.url) == ("DELETE", sub.location)
    assert last.headers["authorization"] == w.rt.sent[0].headers["authorization"]
    assert last.headers["user-agent"] == "Contoso-IT-GitHub-connector"   # policies apply to the delete as well
