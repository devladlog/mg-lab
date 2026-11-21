"""Compile infra/main.bicep and check the policy assignments and the compliant-by-construction resources."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("bicep") is None, reason="Bicep CLI not installed")


@pytest.fixture(scope="module")
def arm(tmp_path_factory):
    infra = Path(__file__).resolve().parents[1] / "infra"
    out = tmp_path_factory.mktemp("arm") / "main.json"
    subprocess.run(["bicep", "build", str(infra / "main.bicep"), "--outfile", str(out)], check=True,
                   capture_output=True, text=True)
    t = json.loads(out.read_text())
    res = t["resources"]
    return t, list(res.values()) if isinstance(res, dict) else res


def of_type(resources, type_):
    return [r for r in resources if r["type"] == type_]


def test_three_builtin_policy_assignments_with_effects(arm):
    t, resources = arm
    assignments = {a["name"]: a["properties"] for a in of_type(resources, "Microsoft.Authorization/policyAssignments")}
    assert set(assignments) == {"ai-keyless-deny", "ai-approved-models-deny", "ai-diagnostic-logs-audit"}
    ids = t["variables"]["builtIn"]
    assert ids == {"keyless": "71ef260a-8f18-47b7-abcb-62d0673d94dc",
                   "approvedModels": "aafe3651-cb78-4f68-9f81-e7e41509110f",
                   "diagnosticLogs": "1b4d1c4e-934c-4703-944c-27c82c06bebb"}
    assert assignments["ai-keyless-deny"]["parameters"]["effect"]["value"] == "Deny"
    assert assignments["ai-diagnostic-logs-audit"]["parameters"]["effect"]["value"] == "AuditIfNotExists"
    models = assignments["ai-approved-models-deny"]["parameters"]
    assert models["effect"]["value"] == "Deny" and models["allowedPublishers"]["value"] == []
    assert all(a["properties"]["enforcementMode"] == "Default"
               for a in of_type(resources, "Microsoft.Authorization/policyAssignments"))
    assert "nonComplianceMessages" in assignments["ai-keyless-deny"]


def test_allowed_asset_ids_are_exact_versions(arm):
    t, _ = arm
    ids = t["parameters"]["allowedAssetIds"]["defaultValue"]
    # "contains" matching: without /versions/... gpt-5-mini would also match any model whose id starts the same
    assert all("/versions/" in i for i in ids)
    assert "azureml://registries/azure-openai/models/gpt-5-mini/versions/2025-08-07" in ids


def test_hr_bot_account_is_compliant_by_construction(arm):
    t, resources = arm
    accounts = of_type(resources, "Microsoft.CognitiveServices/accounts")
    assert len(accounts) == 2 and all(a["properties"]["disableLocalAuth"] is True for a in accounts)
    hr = next(a for a in accounts if "tags" in a)
    assert hr["tags"] == "[variables('tags')]" and t["variables"]["tags"]["ai-system-id"] == "[parameters('systemId')]"
    shadow = next(a for a in accounts if "tags" not in a)
    assert shadow["condition"] == "[parameters('deployShadowAccount')]"
    (dep,) = of_type(resources, "Microsoft.CognitiveServices/accounts/deployments")
    assert dep["properties"]["versionUpgradeOption"] == "NoAutoUpgrade"
    assert t["parameters"]["chatSku"]["defaultValue"] == "DataZoneStandard"


def test_audit_logs_go_to_the_workspace(arm):
    _, resources = arm
    (diag,) = of_type(resources, "Microsoft.Insights/diagnosticSettings")
    cats = {l["category"] for l in diag["properties"]["logs"] if l["enabled"]}
    assert {"Audit", "RequestResponse", "AzureOpenAIRequestUsage"} <= cats
    assert "workspaceId" in diag["properties"]


def test_guardrail_has_both_prompt_shields(arm):
    t, _ = arm
    on = {f["name"] for f in t["variables"]["contentFilters"] if f["enabled"] and f["blocking"]}
    assert {"Jailbreak", "Indirect Attack"} <= on
