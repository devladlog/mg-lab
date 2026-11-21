"""Compile infra/main.bicep and check the guardrail policy, its link to the deployment, keyless accounts and roles."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("bicep") is None, reason="Bicep CLI not installed")

COGNITIVE_SERVICES_USER = "a97b65f3-24c7-4388-baec-2e87135dc908"
OPENAI_USER = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"


@pytest.fixture(scope="module")
def arm(tmp_path_factory):
    infra = Path(__file__).resolve().parents[1] / "infra"
    out = tmp_path_factory.mktemp("arm") / "main.json"
    subprocess.run(["bicep", "build", str(infra / "main.bicep"), "--outfile", str(out)], check=True,
                   capture_output=True, text=True)
    template = json.loads(out.read_text())
    res = template["resources"]
    return template, list(res.values()) if isinstance(res, dict) else res


def of_type(resources, type_):
    return [r for r in resources if r["type"] == type_]


def test_both_accounts_are_keyless_with_custom_subdomains(arm):
    template, resources = arm
    accounts = {a["kind"]: a for a in of_type(resources, "Microsoft.CognitiveServices/accounts")}
    assert set(accounts) == {"ContentSafety", "OpenAI"}
    for a in accounts.values():
        assert a["properties"]["disableLocalAuth"] is True and a["properties"]["customSubDomainName"]
    assert template["parameters"]["contentSafetySku"]["defaultValue"] == "F0"


def test_policy_blocks_core_harms_at_medium_on_input_and_output(arm):
    template, _ = arm
    filters = template["variables"]["contentFilters"]
    for source in ("Prompt", "Completion"):
        harms = {f["name"]: f for f in filters if f["source"] == source and "severityThreshold" in f}
        assert set(harms) == {"Hate", "Sexual", "Violence", "Selfharm"}
        assert all(f["severityThreshold"] == "Medium" and f["blocking"] and f["enabled"] for f in harms.values())


def test_policy_turns_on_both_prompt_shields_and_protected_material(arm):
    template, _ = arm
    by = {(f["name"], f["source"]): f for f in template["variables"]["contentFilters"]}
    assert by[("Jailbreak", "Prompt")]["blocking"] is True
    assert by[("Indirect Attack", "Prompt")]["enabled"] is True     # document attacks are off by default
    assert by[("Protected Material Text", "Completion")]["blocking"] is True
    assert by[("Protected Material Code", "Completion")]["enabled"] is True


def test_deployment_uses_the_custom_policy_and_a_pinned_model(arm):
    template, resources = arm
    (policy,) = of_type(resources, "Microsoft.CognitiveServices/accounts/raiPolicies")
    assert policy["properties"]["basePolicyName"] == "Microsoft.DefaultV2"
    (dep,) = of_type(resources, "Microsoft.CognitiveServices/accounts/deployments")
    assert dep["properties"]["raiPolicyName"] == "[parameters('policyName')]"   # = the policy resource's name
    assert dep["properties"]["versionUpgradeOption"] == "NoAutoUpgrade"
    assert template["parameters"]["policyName"]["defaultValue"] == "contoso-hr-strict"
    assert template["parameters"]["chatModel"]["defaultValue"] == "gpt-5-mini"


def test_developer_roles_are_data_plane_only(arm):
    template, resources = arm
    assignments = of_type(resources, "Microsoft.Authorization/roleAssignments")
    assert len(assignments) == 2
    assert set(template["variables"]["roles"].values()) == {COGNITIVE_SERVICES_USER, OPENAI_USER}
    assert all(a["properties"]["principalType"] == "[parameters('developerPrincipalType')]" for a in assignments)
