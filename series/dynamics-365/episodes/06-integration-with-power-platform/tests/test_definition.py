import copy
import json

import pytest

from conftest import flow
from flowkit import definition

TRIGGER = "When_a_row_is_added,_modified_or_deleted"


def codes(findings):
    return sorted(f.code for f in findings)


def tparams(data):
    return data["properties"]["definition"]["triggers"][TRIGGER]["inputs"]["parameters"]


def test_sample_flow_is_clean(good, cfg):
    assert definition.lint(flow(good), cfg) == []


def test_clientdata_can_be_the_string_stored_in_the_workflow_row(good):
    f = definition.Flow(definition.load_clientdata(json.dumps(good)))
    name, p = f.row_trigger()
    assert name == TRIGGER
    assert (p["entityname"], p["filteringattributes"], p["filterexpression"]) == \
        ("mgl_projectrequest", "mgl_riskscore", "mgl_riskscore ge 70")   # prefix 'subscriptionRequest/' stripped
    with pytest.raises(ValueError, match="properties.definition"):
        definition.load_clientdata({"properties": {}})


def test_the_bad_fixture_trips_every_rule(bad, cfg):
    findings = definition.lint(flow(bad), cfg)
    assert codes(findings) == ["F011", "F012", "F020", "F030", "F040", "F050", "F051", "F060"]
    assert definition.has_errors(findings)
    loop = next(f for f in findings if f.code == "F020")
    assert loop.message.startswith("Condition/else/Mark_as_notified updates mgl_riskscore")   # found inside If/else


def test_missing_select_columns_is_a_warning(good, cfg):
    tparams(good).pop("subscriptionRequest/filteringattributes")
    (f,) = definition.lint(flow(good), cfg)
    assert (f.level, f.code) == ("warning", "F010")


def test_bare_connector_keys_work_too(good, cfg):
    p = tparams(good)
    for k in list(p):
        p[k.split("/")[-1]] = p.pop(k)
    assert flow(good).row_trigger()[1]["filteringattributes"] == "mgl_riskscore"
    assert definition.lint(flow(good), cfg) == []


def test_update_of_another_column_or_table_is_not_a_loop(good, cfg):
    acts = good["properties"]["definition"]["actions"]
    acts["Stamp"] = {"runAfter": {}, "type": "OpenApiConnection", "inputs": {
        "host": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps", "operationId": "UpdateOnlyRecord"},
        "parameters": {"entityName": "mgl_projectrequests", "recordId": "x", "item/mgl_name": "y"}}}
    acts["Touch_account"] = copy.deepcopy(acts["Stamp"])
    acts["Touch_account"]["inputs"]["parameters"] = {"entityName": "accounts", "recordId": "x", "item/mgl_riskscore": 1}
    assert definition.lint(flow(good), cfg) == []


def test_wrong_bound_action_and_table(good, cfg):
    p = good["properties"]["definition"]["actions"]["Assess_the_request"]["inputs"]["parameters"]
    p["actionName"], p["entityName"] = "Microsoft.Dynamics.CRM.mgl_Other", "accounts"
    assert codes(definition.lint(flow(good), cfg)) == ["F070", "F071"]


def test_trigger_on_another_table_and_unknown_connector(good, cfg):
    tparams(good)["subscriptionRequest/entityname"] = "account"
    good["properties"]["connectionReferences"]["shared_office365"] = {
        "connection": {"connectionReferenceLogicalName": "mgl_sharedoffice365_00000"}, "api": {"name": "shared_office365"}}
    assert codes(definition.lint(flow(good), cfg)) == ["F002", "F041"]


def test_walk_actions_reaches_switch_cases_default_and_scopes():
    actions = {"Scope": {"type": "Scope", "actions": {"A": {}}},
               "Switch": {"type": "Switch", "cases": {"Case": {"actions": {"B": {}}}}, "default": {"actions": {"C": {}}}}}
    assert [n for n, _ in definition.walk_actions(actions)] == ["Scope", "Scope/A", "Switch", "Switch/Case/B", "Switch/default/C"]


def test_env_var_schema_from_metadata_or_name():
    assert definition.env_var_schema("Alert Team Id (mgl_AlertTeamId)", {}) == "mgl_AlertTeamId"
    assert definition.env_var_schema("x", {"metadata": {"schemaName": "mgl_X"}}) == "mgl_X"
    assert definition.env_var_schema("plain", {}) is None


def test_summary_lists_trigger_actions_and_connection_references(good):
    lines = flow(good).summary()
    assert lines[0] == ("trigger  When_a_row_is_added,_modified_or_deleted: table mgl_projectrequest, select columns "
                        "mgl_riskscore, filter rows mgl_riskscore ge 70")
    assert "action   Assess_the_request: PerformBoundAction [shared_commondataserviceforapps]" in lines
    assert "action   Post_to_the_risk_channel: PostMessageToConversation [shared_teams]" in lines
    assert "connref  shared_teams -> mgl_sharedteams_00000" in lines
