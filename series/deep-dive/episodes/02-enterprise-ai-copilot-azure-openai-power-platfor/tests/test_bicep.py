"""Compile infra/main.bicep and check the security-relevant settings in the ARM output (needs the Bicep CLI)."""
import json
import shutil
import subprocess

import pytest
from conftest import ROOT

pytestmark = pytest.mark.skipif(shutil.which("bicep") is None, reason="Bicep CLI not installed")


@pytest.fixture(scope="module")
def arm():
    out = subprocess.run(["bicep", "build", str(ROOT / "infra" / "main.bicep"), "--stdout"],
                         capture_output=True, text=True, check=True, timeout=120)
    t = json.loads(out.stdout)
    res = t["resources"]
    return {"list": list(res.values()) if isinstance(res, dict) else res, "roles": t["variables"]["roles"]}


def of_type(arm, t):
    return [r for r in arm["list"] if r["type"] == t]


def test_openai_and_search_have_keys_disabled(arm):
    (aoai,) = of_type(arm, "Microsoft.CognitiveServices/accounts")
    assert aoai["properties"]["disableLocalAuth"] is True and "customSubDomainName" in aoai["properties"]
    (srch,) = of_type(arm, "Microsoft.Search/searchServices")
    assert srch["properties"]["disableLocalAuth"] is True
    assert srch["identity"]["type"] == "SystemAssigned"


def test_model_versions_are_pinned(arm):
    deps = {d["name"].split("'")[-2] if "'" in d["name"] else d["name"]: d
            for d in of_type(arm, "Microsoft.CognitiveServices/accounts/deployments")}
    assert len(deps) == 2
    for d in deps.values():
        assert d["properties"]["versionUpgradeOption"] == "NoAutoUpgrade"


def test_role_assignments_are_least_privilege(arm):
    expected = {"openAiUser": "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd",
                "searchIndexDataReader": "1407120a-92aa-4202-b7e9-c0e197c71c8f",
                "searchIndexDataContributor": "8ebe5a00-799e-43f5-93ac-243d3dce84a7",
                "searchServiceContributor": "7ca78c08-252a-4471-8644-bb5ff32d4ba0"}
    for k, v in expected.items():
        assert arm["roles"][k] == v
    # no Owner / Contributor / User Access Administrator in the role table
    for broad in ("8e3af657-a8ff-443c-a75c-2fe8c4bcb635", "b24988ac-6180-42a0-ab88-20f7382dd24c",
                  "18d7d88d-d35e-4fb5-a5c3-7773c20a72d9"):
        assert broad not in arm["roles"].values()
    assigns = of_type(arm, "Microsoft.Authorization/roleAssignments")
    used = " ".join(r["properties"]["roleDefinitionId"] for r in assigns)
    for k in expected:
        assert k in used, k
    assert all("principalType" in r["properties"] for r in assigns)


def test_easy_auth_requires_a_token_for_the_api(arm):
    (auth,) = [r for r in of_type(arm, "Microsoft.Web/sites/config") if "authsettingsV2" in r["name"]]
    p = auth["properties"]
    assert p["platform"]["enabled"] is True
    assert p["globalValidation"] == {"requireAuthentication": True, "unauthenticatedClientAction": "Return401"}
    aad = p["identityProviders"]["azureActiveDirectory"]
    assert aad["enabled"] is True and "allowedAudiences" in aad["validation"]


def test_function_points_at_the_index_the_indexer_creates(arm):
    (settings,) = [r for r in of_type(arm, "Microsoft.Web/sites/config") if "appsettings" in r["name"]]
    idx = json.loads((ROOT / "index" / "policies-index.json").read_text(encoding="utf-8"))
    assert settings["properties"]["SEARCH_INDEX"] == idx["name"]
    assert "CHAT_DEPLOYMENT" in settings["properties"] and "AZURE_CLIENT_ID" in settings["properties"]
