"""The what-if gate, against what-if documents shaped like the Learn schema (WhatIfOperationResult)."""
import json
import subprocess
import sys

import pytest

from conftest import EP, FIXTURES
from whatif_gate import Policy, WhatIfFormatError, evaluate, to_markdown
from whatif_gate.gate import flatten, logging_commands, resource_type


def test_first_deploy_is_all_creates_and_goes(whatif, policy):
    r = evaluate(whatif("first-deploy"), policy)
    assert not r.blocked
    assert r.counts["Create"] == 7 and sum(r.counts.values()) == 7


def test_tag_change_goes_and_nochange_is_not_listed(whatif, policy):
    r = evaluate(whatif("tags-only"), policy)
    assert not r.blocked and r.findings == []
    assert r.resources == [("Modify", "Microsoft.Storage/storageAccounts/stcontosolab0000")]


def test_drift_on_protected_property_blocks(whatif, policy):
    r = evaluate(whatif("drift-public-access"), policy)
    assert r.blocked
    paths = sorted(f.message.split(":")[0] for f in r.findings)
    assert paths == ["protected change properties.networkAcls.defaultAction",
                     "protected change properties.publicNetworkAccess"]
    assert '"Enabled" -> "Disabled"' in r.findings[1].message or '"Enabled" -> "Disabled"' in r.findings[0].message


def test_accept_protected_lets_it_through_but_records_it(whatif, policy):
    r = evaluate(whatif("drift-public-access"), policy, accept_protected=True)
    assert not r.blocked
    assert len(r.accepted) == 2
    assert "Protected changes accepted for this run" in to_markdown(r, "lab")


def test_array_children_are_walked(whatif, policy):
    r = evaluate(whatif("nsg-rules"), policy)
    assert r.blocked
    assert r.findings[0].message.startswith("protected change properties.securityRules.1")


def test_delete_blocks_even_with_accept_protected_and_rest_shape_is_read(whatif, policy):
    r = evaluate(whatif("delete-rest-shape"), policy, accept_protected=True)
    assert r.blocked
    assert r.findings[0].message == "Delete is never done by this pipeline"


def test_unsupported_and_unevaluated_expressions_warn_only(whatif, policy):
    r = evaluate(whatif("unsupported"), policy)
    assert not r.blocked
    assert [f.level for f in r.findings] == ["warn", "warn"]
    assert any("[utcNow()]" in f.message for f in r.findings)


def test_failed_whatif_is_unusable(whatif, policy):
    with pytest.raises(WhatIfFormatError, match="InvalidTemplateDeployment"):
        evaluate(whatif("failed"), policy)


@pytest.mark.parametrize("doc", [[], {"status": "Succeeded"}, {"changes": [{"changeType": "Explode", "resourceId": "/x"}]},
                                 {"changes": [{"changeType": "Create"}]}])
def test_malformed_input_is_rejected(doc, policy):
    with pytest.raises(WhatIfFormatError):
        evaluate(doc, policy)


def test_ignore_paths_silence_known_noise(whatif):
    base = json.loads((EP / "pipelines" / "gate-policy.json").read_text())
    base["ignore_paths"] = ["properties.networkAcls"]
    r = evaluate(whatif("drift-public-access"), Policy.from_dict(base))
    assert [f.message.split(":")[0] for f in r.findings] == ["protected change properties.publicNetworkAccess"]


def test_policy_rejects_typos():
    with pytest.raises(ValueError, match="unknown policy keys"):
        Policy.from_dict({"protect": []})
    with pytest.raises(ValueError, match="unknown change types"):
        Policy.from_dict({"protected": [{"resource_type": "x", "paths": ["y"], "change_types": ["Modifed"]}]})


@pytest.mark.parametrize("rid,expected", [
    ("/subscriptions/0/resourceGroups/rg/providers/Microsoft.Web/sites/app-1", "Microsoft.Web/sites"),
    ("/subscriptions/0/resourceGroups/rg/providers/Microsoft.Web/sites/app-1/config/web", "Microsoft.Web/sites/config"),
    ("/subscriptions/0/resourceGroups/rg/providers/Microsoft.Network/privateEndpoints/pe/providers/"
     "Microsoft.Authorization/roleAssignments/1", "Microsoft.Authorization/roleAssignments"),
    ("/subscriptions/0/resourceGroups/rg", "Microsoft.Resources/resourceGroups"),
])
def test_resource_type(rid, expected):
    assert resource_type(rid) == expected


def test_flatten_builds_full_paths():
    delta = [{"path": "a", "propertyChangeType": "Array", "children": [{"path": "0", "propertyChangeType": "Create", "after": 1}]}]
    assert list(flatten(delta)) == [("a.0", "Create", None, 1)]


def test_logging_commands_are_single_line_and_escaped(whatif, policy):
    r = evaluate(whatif("drift-public-access"), policy)
    lines = logging_commands(r)
    assert all(l.startswith("##vso[task.logissue type=error]") for l in lines)
    assert all("\n" not in l and ";" not in l.split("]", 1)[1] for l in lines)


def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "whatif_gate", *args], cwd=EP / "src",
                          capture_output=True, text=True)


def test_cli_exit_codes_and_summary(tmp_path):
    pol = str(EP / "pipelines" / "gate-policy.json")
    ok = run_cli("--whatif", str(FIXTURES / "whatif-tags-only.json"), "--policy", pol)
    blocked = run_cli("--whatif", str(FIXTURES / "whatif-drift-public-access.json"), "--policy", pol,
                      "--summary", str(tmp_path / "s.md"), "--azure-devops")
    broken = run_cli("--whatif", str(FIXTURES / "whatif-failed.json"), "--policy", pol)
    assert (ok.returncode, blocked.returncode, broken.returncode) == (0, 1, 2)
    assert "## What-if gate: BLOCKED" in (tmp_path / "s.md").read_text()
    assert f"##vso[task.uploadsummary]{tmp_path / 's.md'}" in blocked.stdout
