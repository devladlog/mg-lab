"""Compile main.bicep with the Bicep CLI and assert the security-relevant properties of the ARM output."""
import json
import re
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(shutil.which("bicep") is None, reason="Bicep CLI not installed")

OPENAI_USER = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"


@pytest.fixture(scope="module")
def arm(tmp_path_factory):
    from pathlib import Path

    infra = Path(__file__).resolve().parents[1] / "infra"
    out = tmp_path_factory.mktemp("arm") / "main.json"
    subprocess.run(["bicep", "build", str(infra / "main.bicep"), "--outfile", str(out)], check=True,
                   capture_output=True, text=True)
    return json.loads(out.read_text())


def all_resources(template):
    resources = template["resources"]
    for r in resources.values() if isinstance(resources, dict) else resources:
        yield r
        if r["type"] == "Microsoft.Resources/deployments":
            yield from all_resources(r["properties"]["template"])


def of_type(arm, type_):
    return [r for r in all_resources(arm) if r["type"] == type_]


def resolve(arm, value):
    """Bicep moves shared values (and loadTextContent) into variables: "[variables('x')]" -> the value."""
    m = re.fullmatch(r"\[variables\('([^']+)'\)\]", value) if isinstance(value, str) else None
    return arm["variables"][m.group(1)] if m else value


def test_openai_accounts_are_keyless(arm):
    accounts = of_type(arm, "Microsoft.CognitiveServices/accounts")   # one per module call: primary, secondary
    assert len(accounts) == 2
    for account in accounts:
        assert account["properties"]["disableLocalAuth"] is True
        assert "customSubDomainName" in account["properties"]


def test_deployment_pins_the_model_version(arm):
    for dep in of_type(arm, "Microsoft.CognitiveServices/accounts/deployments"):
        assert dep["properties"]["versionUpgradeOption"] == "NoAutoUpgrade"


def test_role_is_openai_user_with_principal_type(arm):
    modules = of_type(arm, "Microsoft.Resources/deployments")
    assert len(modules) == 2
    for module in modules:
        template = module["properties"]["template"]
        (ra,) = [r for r in template["resources"] if r["type"] == "Microsoft.Authorization/roleAssignments"]
        assert "variables('openAiUserRoleId')" in ra["properties"]["roleDefinitionId"]
        assert template["variables"]["openAiUserRoleId"] == OPENAI_USER
        assert "principalType" in ra["properties"]
        # the gateway's managed identity is always the first principal, typed as ServicePrincipal
        principals = module["properties"]["parameters"]["inferencePrincipals"]["value"]
        assert "ServicePrincipal" in json.dumps(principals)


def test_gateway_is_basic_v2_with_managed_identity(arm):
    (apim,) = of_type(arm, "Microsoft.ApiManagement/service")
    assert apim["sku"]["name"] == "BasicV2"
    assert apim["identity"]["type"] == "SystemAssigned"


def test_backends_have_breakers_and_a_priority_pool(arm):
    backends = of_type(arm, "Microsoft.ApiManagement/service/backends")
    singles = [b for b in backends if b["properties"].get("type") != "Pool"]
    (pool,) = [b for b in backends if b["properties"].get("type") == "Pool"]
    assert len(singles) == 2
    for b in singles:
        rule = resolve(arm, b["properties"]["circuitBreaker"])["rules"][0]
        assert rule["acceptRetryAfter"] is True
        assert {"min": 429, "max": 429} in rule["failureCondition"]["statusCodeRanges"]
    assert [s["priority"] for s in pool["properties"]["pool"]["services"]] == [1, 2]


def test_api_uses_api_key_header_and_loads_the_policy_file(arm):
    (api,) = of_type(arm, "Microsoft.ApiManagement/service/apis")
    assert api["properties"]["subscriptionKeyParameterNames"]["header"] == "api-key"
    (policy,) = of_type(arm, "Microsoft.ApiManagement/service/apis/policies")
    assert "<llm-token-limit" in resolve(arm, policy["properties"]["value"])


def test_custom_metrics_are_enabled_for_token_metrics(arm):
    (diag,) = of_type(arm, "Microsoft.ApiManagement/service/diagnostics")
    assert diag["properties"]["metrics"] is True


def test_one_subscription_per_team(arm):
    (subs,) = of_type(arm, "Microsoft.ApiManagement/service/subscriptions")
    assert subs["copy"]["count"] == "[length(parameters('teams'))]"
