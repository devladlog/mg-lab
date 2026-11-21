"""Compile infra/main.bicep with the Bicep CLI and check what the agent code depends on."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("bicep") is None, reason="Bicep CLI not installed")

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


def test_account_is_keyless_with_custom_subdomain(arm):
    _, resources = arm
    (account,) = of_type(resources, "Microsoft.CognitiveServices/accounts")
    assert account["kind"] == "OpenAI"
    assert account["properties"]["disableLocalAuth"] is True
    assert account["properties"]["customSubDomainName"]


def test_model_is_pinned_and_supports_the_responses_api(arm):
    template, resources = arm
    (dep,) = of_type(resources, "Microsoft.CognitiveServices/accounts/deployments")
    assert dep["properties"]["versionUpgradeOption"] == "NoAutoUpgrade"
    p = template["parameters"]
    assert (p["chatModel"]["defaultValue"], p["chatVersion"]["defaultValue"]) == ("gpt-5-mini", "2025-08-07")
    assert p["chatSku"]["defaultValue"] == "DataZoneStandard"


def test_developer_gets_only_openai_user_with_principal_type(arm):
    template, resources = arm
    (ra,) = of_type(resources, "Microsoft.Authorization/roleAssignments")
    assert template["variables"]["openAiUserRole"] == OPENAI_USER
    assert "openAiUserRole" in ra["properties"]["roleDefinitionId"]
    assert ra["properties"]["principalType"] == "[parameters('developerPrincipalType')]"
    assert "condition" in ra  # skipped when no developer object id is given


def test_params_file_compiles_with_zero_guid_only():
    infra = Path(__file__).resolve().parents[1] / "infra"
    out = subprocess.run(["bicep", "build-params", str(infra / "main.bicepparam"), "--stdout"], check=True,
                         capture_output=True, text=True).stdout
    params = json.loads(json.loads(out)["parametersJson"])["parameters"]
    assert params["developerPrincipalId"]["value"] == "00000000-0000-0000-0000-000000000000"
