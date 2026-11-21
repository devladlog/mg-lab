"""Each trap we fell into, as a test. They run the same flow and connector; one thing is different."""
from connectorkit import Connection, Runtime, validate
from connectorkit.definition import errors
from githubfake import scenario, variants
from githubfake.scenario import REPO

from conftest import mutate


def test_draft_1_without_body_defaults_github_uses_its_own_push_and_form(connector):
    w = scenario.make_world(variants.no_body_defaults(connector))
    sub = w.platform.turn_on()
    assert sub.created.body["events"] == ["push"] and sub.created.body["config"]["content_type"] == "form"
    w.gh.open_issue(REPO, "Monitor", "", "sam-demo", [])
    assert [d.event for d in w.gh.deliveries] == ["ping"]      # the ping is sent whatever the events are
    assert w.platform.runs == [] and w.sharepoint.items == []  # and nothing else ever arrives: green setup, silent flow
    assert w.gh.deliveries[0].content_type == "application/x-www-form-urlencoded"
    event, body = w.platform.received[0]
    assert list(body) == ["payload"]     # form post: the JSON sits in a field called payload


def test_draft_2_without_a_delete_operation_the_webhook_outlives_the_flow(connector):
    bad = variants.no_delete_operation(connector)
    assert any("no delete operation" in str(f) for f in errors(validate(bad)))
    w = scenario.make_world(bad)
    w.platform.turn_on()
    assert w.platform.turn_off() is None          # nothing to call
    assert len(w.gh.hooks) == 1                   # still registered on GitHub...
    w.gh.open_issue(REPO, "After off", "", "riley-demo", [])
    assert w.gh.deliveries[-1].status is None     # ...and delivering to a callback nobody listens to


def test_without_a_location_header_the_platform_cannot_remove_the_webhook(connector):
    w = scenario.make_world(send_location=False)
    sub = w.platform.turn_on()
    assert sub.location is None and w.platform.turn_off() is None and len(w.gh.hooks) == 1


def test_draft_3_without_a_trigger_condition_the_ping_creates_a_junk_request_and_fails(flow):
    w = scenario.make_world(flow=variants.no_trigger_condition(flow))
    w.platform.turn_on()
    (run,) = w.platform.runs
    assert run.status == "Failed" and run.status_of("Create_IT_request") == "Succeeded" and run.status_of("Comment_on_issue") == "Failed"
    assert [i["Title"] for i in w.sharepoint.items] == ["[GitHub] "]


def test_draft_3_also_runs_on_every_edit_and_creates_a_duplicate_request(flow):
    w = scenario.make_world(flow=variants.no_trigger_condition(flow))
    w.platform.turn_on()
    w.gh.open_issue(REPO, "Monitor", "", "sam-demo", [])
    w.gh.edit_issue(REPO, 1, "Monitor 27 inch", "sam-demo")
    titles = [i["Title"] for i in w.sharepoint.items]
    assert titles == ["[GitHub] ", "[GitHub] Monitor", "[GitHub] Monitor 27 inch"]
    assert len(w.gh.issues[REPO][1].comments) == 2     # the issue was told twice


def test_a_token_without_the_webhooks_permission_gets_404_when_the_flow_is_turned_on():
    w = scenario.make_world(permissions={"issues:write"})
    sub = w.platform.turn_on()
    assert sub.created.status == 404 and sub.location is None and w.gh.hooks == {}


def test_a_wrong_token_is_a_401_bad_credentials_at_connection_test(world):
    rt = Runtime(world.connector, world.gh.handle)
    res = rt.test_connection(Connection("contoso-it-bot", "wrong"))
    assert (res.status, res.body["message"]) == (401, "Bad credentials")
    assert rt.test_connection(Connection("contoso-it-bot", "ghp_demo_0000")).body["login"] == "contoso-it-bot"


def test_without_the_user_agent_policy_github_answers_403(connector):
    bad = mutate(connector, lambda d, p: p["properties"]["policyTemplateInstances"].pop())   # the User-Agent policy
    w = scenario.make_world(bad)
    res = w.rt.test_connection(w.platform.conn)
    assert res.status == 403 and "User-Agent" in res.body["message"]


def test_a_token_without_issues_write_creates_the_request_but_the_comment_fails():
    w = scenario.make_world(permissions=scenario.FULL - {"issues:write"})
    w.platform.turn_on()
    w.gh.open_issue(REPO, "Monitor", "", "sam-demo", [])
    (run,) = w.platform.runs
    assert run.status == "Failed" and run.status_of("Create_IT_request") == "Succeeded"
    assert run.actions["Comment_on_issue"].error == "Resource not accessible by personal access token"
    assert len(w.sharepoint.items) == 1


def test_resubmitting_that_failed_run_creates_the_request_a_second_time():
    """The flow isn't idempotent: after a failed comment, a resubmit repeats the whole run. README says what to do."""
    w = scenario.make_world(permissions=scenario.FULL - {"issues:write"})
    w.platform.turn_on()
    issue = w.gh.open_issue(REPO, "Monitor", "", "sam-demo", [])
    w.gh._issue_event(REPO, issue, "opened", "sam-demo")      # GitHub's redeliver button, or Resubmit in the flow
    assert len(w.sharepoint.items) == 2
