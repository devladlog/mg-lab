"""Compile infra/main.bicep with the Bicep CLI and check the properties the code depends on."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("bicep") is None, reason="Bicep CLI not installed")

OPENAI_USER = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"
SEARCH_ROLES = {"7ca78c08-252a-4471-8644-bb5ff32d4ba0", "8ebe5a00-799e-43f5-93ac-243d3dce84a7",
                "1407120a-92aa-4202-b7e9-c0e197c71c8f"}


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


def test_search_is_keyless_with_identity_and_free_semantic_plan(arm):
    _, resources = arm
    (search,) = of_type(resources, "Microsoft.Search/searchServices")
    assert search["identity"]["type"] == "SystemAssigned"
    assert search["properties"]["disableLocalAuth"] is True
    assert search["properties"]["semanticSearch"] == "free"


def test_openai_is_keyless_and_models_are_pinned(arm):
    template, resources = arm
    (account,) = of_type(resources, "Microsoft.CognitiveServices/accounts")
    assert account["properties"]["disableLocalAuth"] is True and account["properties"]["customSubDomainName"]
    deployments = of_type(resources, "Microsoft.CognitiveServices/accounts/deployments")
    assert len(deployments) == 2
    assert all(d["properties"]["versionUpgradeOption"] == "NoAutoUpgrade" for d in deployments)
    assert template["parameters"]["embeddingModel"]["defaultValue"] == "text-embedding-3-small"


def test_search_identity_can_call_the_embedding_model(arm):
    template, resources = arm
    assignments = of_type(resources, "Microsoft.Authorization/roleAssignments")
    search_to_aoai = [a for a in assignments if "search" in a["properties"]["principalId"].lower()
                      and "identity" in a["properties"]["principalId"].lower()]
    assert len(search_to_aoai) == 1
    a = search_to_aoai[0]["properties"]
    assert "variables('roles').openAiUser" in a["roleDefinitionId"] and template["variables"]["roles"]["openAiUser"] == OPENAI_USER
    assert a["principalType"] == "ServicePrincipal"
    assert "Microsoft.CognitiveServices/accounts" in search_to_aoai[0]["scope"]


def test_developer_gets_the_three_search_roles(arm):
    _, resources = arm
    loop = [a for a in of_type(resources, "Microsoft.Authorization/roleAssignments") if "copy" in a]
    assert len(loop) == 1
    template, _ = arm
    roles = set(template["variables"]["roles"].values())
    assert SEARCH_ROLES <= roles
