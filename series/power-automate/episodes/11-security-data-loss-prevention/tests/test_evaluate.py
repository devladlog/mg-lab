"""The rules of a data policy, applied to connector sets and to the demo flows."""
import pytest
from conftest import FLOWS, POLICY

from dlpkit.connectors import HTTP, norm_id
from dlpkit.evaluate import connectors_of, evaluate
from dlpkit.model import BLOCKED, BUSINESS, NONBUSINESS, Policy, PolicyError, load_policies, policy_from_dict, validate
from flowkit.lint import load_flow


def pol(name="p", default=NONBUSINESS, business=(), blocked=(), nonbusiness=(), scope=None):
    groups = {**{c: BUSINESS for c in business}, **{c: BLOCKED for c in blocked}, **{c: NONBUSINESS for c in nonbusiness}}
    return Policy(display_name=name, default=default, groups=groups, **(scope or {}))


def test_ids_meet_whatever_way_they_are_written():
    assert norm_id("/providers/Microsoft.PowerApps/apis/shared_SharePointOnline") == "shared_sharepointonline"
    assert norm_id("shared_sharepointonline") == "shared_sharepointonline"


def test_business_and_non_business_can_not_be_mixed():
    p = pol(business=["shared_sharepointonline"])
    v = evaluate({"shared_sharepointonline", "shared_dropbox"}, [p])
    assert [x.kind for x in v] == ["mixed"]
    assert "Business" in v[0].message and "Non-business" in v[0].message


def test_connectors_in_the_same_group_mix_freely():
    p = pol(business=["shared_sharepointonline", "shared_office365"])
    assert evaluate({"shared_sharepointonline", "shared_office365"}, [p]) == []
    assert evaluate({"shared_dropbox", "shared_rss"}, [p]) == []   # both fall in the default group


def test_a_blocked_connector_can_not_be_used_even_alone():
    v = evaluate({"shared_msnweather"}, [pol(blocked=["shared_msnweather"])])
    assert [x.kind for x in v] == ["blocked"]


def test_connectors_that_are_in_no_list_go_to_the_default_group():
    p = pol(default=BUSINESS, nonbusiness=["shared_dropbox"])
    assert evaluate({"shared_sharepointonline", "shared_x"}, [p]) == []           # both default (Business)
    assert evaluate({"shared_sharepointonline", "shared_dropbox"}, [p])           # one explicit Non-business


def test_default_blocked_puts_unblockable_connectors_in_non_business():
    """Learn: unblockable connectors are mapped to Non-business when the default group is Blocked."""
    p = pol(default=BLOCKED)
    assert p.group("shared_sharepointonline") == NONBUSINESS
    assert p.group("shared_dropbox") == BLOCKED
    assert evaluate({"shared_sharepointonline"}, [p]) == []
    assert evaluate({"shared_dropbox"}, [p])


def test_the_admin_center_refuses_an_unblockable_connector_in_blocked():
    problems = validate(pol(blocked=["shared_sharepointonline"]))
    assert problems and "can't be blocked" in problems[0]


def test_what_if_tries_a_change_without_making_it():
    p = pol(business=["shared_sharepointonline"])
    assert evaluate({"shared_sharepointonline", HTTP}, [p])
    assert evaluate({"shared_sharepointonline", HTTP}, [p], what_if={HTTP: BUSINESS}) == []


def test_scope_only_except_and_all():
    only = pol(scope=dict(scope_mode="only", environments=("dev",)))
    exc = pol(scope=dict(scope_mode="except", environments=("dev",)))
    assert only.applies_to("DEV") and not only.applies_to("test")
    assert not exc.applies_to("dev") and exc.applies_to("test")
    assert pol().applies_to("anything")


def test_a_policy_that_does_not_apply_to_the_environment_is_ignored():
    p = pol(blocked=["shared_dropbox"], scope=dict(scope_mode="only", environments=("dev",)))
    assert evaluate({"shared_dropbox"}, [p], environment="test") == []
    assert evaluate({"shared_dropbox"}, [p], environment="dev")


def test_two_policies_a_block_in_either_wins():
    a = pol("a", business=["shared_dropbox"])
    b = pol("b", blocked=["shared_dropbox"])
    assert [v.kind for v in evaluate({"shared_dropbox"}, [a, b])] == ["blocked"]


# ---- the demo flows against the demo policies ----

def uses(name):
    return connectors_of(load_flow(FLOWS / name)).connectors


def test_flows_use_the_connectors_we_think_they_use():
    assert uses("acknowledge-it-request.json") == {"shared_sharepointonline", "shared_office365"}
    assert uses("request-weather-note.json") == {"shared_sharepointonline", "shared_msnweather", "shared_office365"}
    assert uses("request-asset-lookup.json") == {"shared_sharepointonline", HTTP}   # the HTTP action isn't a connection reference


@pytest.mark.parametrize("flow,kinds", [
    ("acknowledge-it-request.json", []),
    ("request-external-copy.json", []),              # a data policy can't see where the email goes
    ("request-asset-lookup.json", ["mixed"]),
    ("request-weather-note.json", ["mixed"]),
])
def test_dev_policy_verdicts(flow, kinds):
    dev = load_policies(POLICY / "it-dev.json")
    assert [v.kind for v in evaluate(uses(flow), dev, "dev")] == kinds


def test_with_the_baseline_the_weather_flow_becomes_blocked_instead_of_mixed():
    both = load_policies(POLICY / "it-dev.json", POLICY / "baseline.json")
    assert [v.kind for v in evaluate(uses("request-weather-note.json"), both, "dev")] == ["blocked"]


def test_http_in_business_fixes_the_asset_flow_and_changes_nothing_else():
    dev = load_policies(POLICY / "it-dev.json")
    assert evaluate(uses("request-asset-lookup.json"), dev, "dev", what_if={HTTP: BUSINESS}) == []
    assert evaluate(uses("request-weather-note.json"), dev, "dev", what_if={HTTP: BUSINESS})


def test_the_dev_policy_does_not_touch_other_environments():
    dev = load_policies(POLICY / "it-dev.json")
    assert evaluate(uses("request-weather-note.json"), dev, "test") == []


def test_flows_that_dlpkit_can_not_resolve_are_reported_not_guessed():
    flow = {"properties": {"definition": {"triggers": {"manual": {"type": "Request", "kind": "Http"}},
                                          "actions": {"Child": {"type": "Workflow", "inputs": {}},
                                                      "Hook": {"type": "HttpWebhook", "inputs": {}}}}}}
    use = connectors_of(flow)
    assert use.connectors == set()
    assert len(use.not_evaluated) == 3


def test_a_connector_in_a_nested_scope_is_found():
    flow = {"properties": {"connectionReferences": {"shared_dropbox": {"api": {"name": "shared_dropbox"}}},
                           "definition": {"triggers": {}, "actions": {"S": {"type": "Scope", "actions": {
                               "If1": {"type": "If", "actions": {"D": {"type": "OpenApiConnection", "inputs": {
                                   "host": {"connectionName": "shared_dropbox", "operationId": "x"}}}}, "else": {"actions": {}}}}}}}}}
    assert connectors_of(flow).connectors == {"shared_dropbox"}


# ---- policy files ----

def test_policy_files_have_no_problems_and_unique_groups():
    for f in POLICY.glob("*.json"):
        for p in load_policies(f):
            assert validate(p) == []


def test_get_dlppolicy_output_shape_is_read():
    """`Get-DlpPolicy | ConvertTo-Json` returns {value: [...]} with connectorGroups (Learn: PowerShell scripts)."""
    sample = {"value": [{"name": "00000000-0000-0000-0000-000000000001", "displayName": "x",
                         "defaultConnectorsClassification": "General",
                         "connectorGroups": [
                             {"classification": "Confidential", "connectors": [{"id": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline", "name": "SharePoint"}]},
                             {"classification": "Blocked", "connectors": [{"id": "/providers/Microsoft.PowerApps/apis/shared_dropbox", "name": "Dropbox"}]}]}]}
    import json, tempfile, pathlib
    f = pathlib.Path(tempfile.mkdtemp()) / "p.json"
    f.write_text(json.dumps(sample))
    (p,) = load_policies(f)
    assert p.groups == {"shared_sharepointonline": BUSINESS, "shared_dropbox": BLOCKED}
    assert p.scope_mode == "all"


def test_unknown_classification_and_double_membership_are_errors():
    with pytest.raises(PolicyError):
        policy_from_dict({"displayName": "x", "connectorGroups": [{"classification": "Secret", "connectors": []}]})
    with pytest.raises(PolicyError, match="two groups"):
        policy_from_dict({"displayName": "x", "connectorGroups": [
            {"classification": "Confidential", "connectors": [{"id": "shared_a"}]},
            {"classification": "General", "connectors": [{"id": "shared_a"}]}]})
