"""The solution's flow with the real connector files, against the fake GitHub and the modelled platform."""
import json
import re

from connectorkit import load_connector
from flowkit import lint
from githubfake import scenario
from githubfake.scenario import REPO

from conftest import CONNECTOR, SOLUTION


def test_turning_the_flow_on_creates_one_webhook_and_github_pings_it(world):
    sub = world.platform.turn_on()
    assert sub.created.status == 201 and sub.created.body["events"] == ["issues"]
    assert sub.created.body["config"]["content_type"] == "json"
    assert [d.event for d in world.gh.deliveries] == ["ping"]
    assert len(world.gh.hooks) == 1


def test_the_ping_does_not_start_a_run_because_of_the_trigger_condition(world):
    world.platform.turn_on()
    assert world.platform.runs == [] and world.platform.ignored == 1
    assert world.sharepoint.items == []


def test_an_opened_issue_becomes_an_it_request_and_gets_a_comment(world):
    world.platform.turn_on()
    issue = world.gh.open_issue(REPO, "Need a second monitor", "For Lisbon.", "sam-demo", [])
    assert [r.status for r in world.platform.runs] == ["Succeeded"]
    (item,) = world.sharepoint.items
    assert item["Title"] == "[GitHub] Need a second monitor" and item["Priority"] == "Normal"
    assert item["Status"] == "New" and item["SourceLink"] == issue.html_url
    (user, text), = issue.comments
    assert user == "contoso-it-bot"
    assert text == ("Thanks, sam-demo. Contoso IT is tracking this as IT request #41: "
                    f"{scenario.SITE}/Lists/IT%20Requests/DispForm.aspx?ID=41")


def test_the_urgent_label_makes_the_request_high_priority(world):
    world.platform.turn_on()
    world.gh.open_issue(REPO, "Laptop won't boot", "", "alex-demo", ["hardware", "urgent"])
    world.gh.open_issue(REPO, "Mouse", "", "alex-demo", ["hardware"])
    assert [i["Priority"] for i in world.sharepoint.items] == ["High", "Normal"]


def test_edits_and_labels_arrive_as_issues_events_but_start_no_run(world):
    world.platform.turn_on()
    world.gh.open_issue(REPO, "Monitor", "", "sam-demo", [])
    world.gh.edit_issue(REPO, 1, "Monitor 27 inch", "sam-demo")
    world.gh.label_issue(REPO, 1, "urgent", "riley-demo")
    assert [(d.event, d.action) for d in world.gh.deliveries] == [("ping", None), ("issues", "opened"), ("issues", "edited"), ("issues", "labeled")]
    assert len(world.platform.runs) == 1 and world.platform.ignored == 3   # ping, edited, labeled
    assert len(world.sharepoint.items) == 1


def test_our_own_comment_does_not_start_another_run(world):
    world.platform.turn_on()
    world.gh.open_issue(REPO, "Monitor", "", "sam-demo", [])
    assert [d.event for d in world.gh.deliveries_of("issue_comment")] == []    # the hook only listens to issues
    assert len(world.platform.runs) == 1


def test_a_long_title_is_cut_to_the_255_characters_of_the_list_column(world):
    world.platform.turn_on()
    world.gh.open_issue(REPO, "x" * 400, "", "sam-demo", [])
    assert len(world.sharepoint.items[0]["Title"]) == 255


def test_turning_the_flow_off_deletes_the_webhook_and_github_stops_calling(world):
    world.platform.turn_on()
    world.platform.turn_off()
    assert world.gh.hooks == {}
    world.gh.open_issue(REPO, "After off", "", "riley-demo", [])
    assert [d.event for d in world.gh.deliveries] == ["ping"]
    assert world.sharepoint.items == []


def test_the_connector_calls_github_with_the_policy_headers_every_time(world):
    world.platform.turn_on()
    world.gh.open_issue(REPO, "Monitor", "", "sam-demo", [])
    world.platform.turn_off()
    assert len(world.gh.requests) == 3     # create hook, comment, delete hook
    for r in world.gh.requests:
        assert r.headers["accept"] == "application/vnd.github+json" and r.headers["x-github-api-version"] == "2022-11-28"
        assert r.headers["user-agent"] and r.headers["authorization"].startswith("Basic ")


# ---- the flow, the connector and the solution agree with each other
def test_flow_lint_is_clean(flow):
    assert [str(f) for f in lint(flow)] == []


def test_the_trigger_is_a_webhook_trigger_with_a_condition(flow):
    (name, trig), = flow["properties"]["definition"]["triggers"].items()
    assert trig["type"] == "OpenApiConnectionWebhook" and trig["inputs"]["host"]["operationId"] == "WhenAnIssueIsOpened"
    assert trig["conditions"] == [{"expression": "@equals(triggerBody()?['action'], 'opened')"}]


def test_every_connector_operation_and_input_the_flow_uses_exists_in_the_definition(flow):
    c = load_connector(CONNECTOR)
    ops = c.operations
    d = flow["properties"]["definition"]
    nodes = list(d["triggers"].values()) + list(d["actions"].values())
    custom = [(n["inputs"]["host"]["operationId"], n["inputs"]["parameters"]) for n in nodes
              if "host" in (n.get("inputs") or {}) and "contoso-5fit-5fgithub" in n["inputs"]["host"]["apiId"]]
    assert {o for o, _ in custom} == {"WhenAnIssueIsOpened", "AddIssueComment"}
    for oid, params in custom:
        assert oid in ops
        _, _, op = ops[oid]
        top = {p["name"] for p in op["parameters"] if p["in"] != "body"}
        body = {p["name"] for p in op["parameters"] if p["in"] == "body"}
        for key in params:
            if key == "authentication":
                continue
            head = key.split("/")[0]
            assert head in top | body, (oid, key)
        required = {p["name"] for p in op["parameters"] if p.get("required") and p["in"] != "body"}
        assert required <= set(params), (oid, required - set(params))


def test_the_flows_body_fields_are_fields_of_the_comment_schema(flow, connector):
    a = flow["properties"]["definition"]["actions"]["Comment_on_issue"]["inputs"]["parameters"]
    schema = connector.definition["definitions"]["CommentRequest"]
    assert "body/body" in a and set(schema["properties"]) == {"body"} and schema["required"] == ["body"]


def test_the_expressions_read_fields_the_trigger_schema_declares(flow, connector):
    text = json.dumps(flow)
    ev = connector.definition["definitions"]["IssuesEvent"]["properties"]
    issue = ev["issue"]["properties"]
    for path in re.findall(r"triggerBody\(\)\?\['(\w+)'\](?:\?\['(\w+)'\])?(?:\?\['(\w+)'\])?", text):
        top, second, third = path
        assert top in ev, top
        if top == "issue" and second:
            assert second in issue, second
            if third and second == "user":
                assert third in issue["user"]["properties"]
        if top == "repository" and second:
            assert second in ev["repository"]["properties"]


def test_the_solution_declares_what_the_flow_uses(flow):
    cust = (SOLUTION / "Other" / "Customizations.xml").read_text(encoding="utf-8-sig")
    refs = flow["properties"]["connectionReferences"]
    for api, ref in refs.items():
        assert f"/providers/Microsoft.PowerApps/apis/{api}</connectorid>" in cust
        assert ref["connection"]["connectionReferenceLogicalName"] in cust
    text = json.dumps(flow)
    for schema in re.findall(r"\((cts_\w+)\)", text):
        assert (SOLUTION / "environmentvariabledefinitions" / schema).is_dir()
    sol = (SOLUTION / "Other" / "Solution.xml").read_text(encoding="utf-8-sig")
    assert "<UniqueName>GitHubIntake</UniqueName>" in sol and "000000000801" in sol
