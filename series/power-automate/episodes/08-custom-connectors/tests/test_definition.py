"""The three connector files: valid, and the validator really catches what it claims to."""
import json

import pytest

from connectorkit import load_connector, validate
from connectorkit.definition import errors

from conftest import CONNECTOR, mutate


def msgs(findings, severity="error"):
    return [str(f) for f in findings if f.severity == severity]


def test_the_connector_files_have_no_errors_and_no_warnings(connector):
    assert msgs(validate(connector), "error") == []
    assert msgs(validate(connector), "warning") == []


def test_settings_json_points_at_the_files_that_exist():
    s = json.loads((CONNECTOR / "settings.json").read_text())
    assert (CONNECTOR / s["apiDefinition"]).exists() and (CONNECTOR / s["apiProperties"]).exists()
    assert s["connectorId"] is None and s["environment"] is None   # filled in by `pac connector create`, never committed


def test_the_connector_has_one_trigger_two_actions_and_two_internal_operations(connector):
    ops = {k: (v[1], v[2].get("x-ms-visibility")) for k, v in connector.operations.items()}
    assert ops == {"WhenAnIssueIsOpened": ("post", "important"), "AddIssueComment": ("post", "important"),
                   "DeleteIssueWebhook": ("delete", "internal"), "GetAuthenticatedUser": ("get", "internal")}
    assert list(connector.triggers) == ["WhenAnIssueIsOpened"]
    assert connector.triggers["WhenAnIssueIsOpened"][2]["x-ms-trigger"] == "single"


def test_the_definition_is_small_and_https_only(connector):
    assert connector.size_bytes < 1024 * 1024 and connector.definition["schemes"] == ["https"]
    assert connector.definition["host"] == "api.github.com"


def test_basic_authentication_matches_the_documented_connection_parameters(connector):
    conn = connector.properties["properties"]["connectionParameters"]
    assert set(conn) == {"username", "password"}
    assert conn["password"]["uiDefinition"]["constraints"]["clearText"] is False
    assert connector.definition["securityDefinitions"] == {"basic_auth": {"type": "basic"}}


def test_no_stackowner_so_paconn_update_works(connector):
    assert "stackOwner" not in connector.properties["properties"]


def test_the_policies_are_three_setheader_templates_on_requests(connector):
    pols = connector.properties["properties"]["policyTemplateInstances"]
    got = {p["parameters"]["x-ms-apimTemplateParameter.name"]: p["parameters"]["x-ms-apimTemplateParameter.existsAction"] for p in pols}
    assert got == {"X-GitHub-Api-Version": "override", "Accept": "override", "User-Agent": "skip"}
    assert all(p["templateId"] == "setheader" and p["parameters"]["x-ms-apimTemplate-policySection"] == "Request" for p in pols)


# ---- negative cases: the validator catches each of these
@pytest.mark.parametrize("name, change, expected", [
    ("title too long", lambda d, p: d["info"].update(title="Contoso IT GitHub issues to requests"), "info.title"),
    ("API in the title", lambda d, p: d["info"].update(title="Contoso GitHub API"), "info.title"),
    ("short description", lambda d, p: d["info"].update(description="Too short."), "info.description"),
    ("hyphen in a summary", lambda d, p: d["paths"]["/user"]["get"].update(summary="Get the signed-in user"), "summary"),
    ("summary equals description", lambda d, p: d["paths"]["/user"]["get"].update(summary="Same.", description="Same."), "summary and description"),
    ("no visibility", lambda d, p: d["paths"]["/user"]["get"].pop("x-ms-visibility"), "x-ms-visibility"),
    ("bad visibility", lambda d, p: d["paths"]["/user"]["get"].update({"x-ms-visibility": "hidden"}), "x-ms-visibility"),
    ("OpenAPI 3", lambda d, p: d.update(swagger="3.0.0"), "only OpenAPI 2.0"),
    ("http scheme", lambda d, p: d.update(schemes=["http"]), "https"),
    ("no delete operation", lambda d, p: d["paths"].pop("/repos/{owner}/{repo}/hooks/{hook_id}"), "no delete operation"),
    ("no notification url", lambda d, p: d["definitions"]["HookRequest"]["properties"]["config"]["properties"]["url"].pop("x-ms-notification-url"), "x-ms-notification-url"),
    ("no notification content", lambda d, p: d["paths"]["/repos/{owner}/{repo}/hooks"].pop("x-ms-notification-content"), "no x-ms-notification-content"),
    ("201 without schema", lambda d, p: d["paths"]["/repos/{owner}/{repo}/hooks"]["post"]["responses"]["201"].pop("schema"), "201 response has no schema"),
    ("default response with schema", lambda d, p: d["paths"]["/user"]["get"]["responses"]["default"].update(schema={"type": "object"}), "default response"),
    ("path parameter without x-ms-summary", lambda d, p: d["paths"]["/repos/{owner}/{repo}/issues/{issue_number}/comments"]["post"]["parameters"][0].pop("x-ms-summary"), "x-ms-summary"),
    ("stackOwner", lambda d, p: p["properties"].update(stackOwner="GitHub"), "stackOwner"),
    ("password in clear text", lambda d, p: p["properties"]["connectionParameters"]["password"]["uiDefinition"]["constraints"].update(clearText=True), "clear text"),
    ("only a username", lambda d, p: p["properties"]["connectionParameters"].pop("password"), "username and password"),
    ("unknown policy key", lambda d, p: p["properties"]["policyTemplateInstances"][0]["parameters"].update({"x-ms-apimTemplateParameter.nme": "x"}), "unknown setheader keys"),
    ("policy for an operation that doesn't exist", lambda d, p: p["properties"]["policyTemplateInstances"][0]["parameters"].update({"x-ms-apimTemplate-operationName": ["Nope"]}), "operationName"),
    ("testConnection points nowhere", lambda d, p: d["x-ms-capabilities"]["testConnection"].update(operationId="Nope"), "testConnection"),
    ("internal required without default", lambda d, p: d["definitions"]["HookRequest"]["properties"]["config"]["properties"]["content_type"].pop("default"), "no default"),
])
def test_the_validator_catches(connector, name, change, expected):
    bad = mutate(connector, change)
    errs = msgs(validate(bad))
    assert any(expected in e for e in errs), (name, errs)


def test_a_definition_over_1_mb_is_refused(connector):
    big = mutate(connector, lambda d, p: d["info"].update(**{"x-ms-padding": "x" * 1_100_000}))
    assert any("1 MB" in str(f) for f in errors(validate(big)))
