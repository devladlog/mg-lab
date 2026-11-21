import json
import re
import shutil
import subprocess

import build_flow
import pytest
from conftest import SRC
from openapi_spec_validator import validate

BICEP = shutil.which("bicep") or "/root/.local/bin/bicep"


def load(p):
    return json.loads((SRC / p).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["foundry", "anthropic"])
def test_connector_definitions_are_valid_swagger_2(name):
    validate(load(f"connectors/{name}/apiDefinition.swagger.json"))


def test_foundry_connector_uses_entra_oauth_on_the_cognitive_services_scope_and_holds_no_secret():
    d, p = load("connectors/foundry/apiDefinition.swagger.json"), load("connectors/foundry/apiProperties.json")
    assert d["securityDefinitions"]["oauth2-auth"]["type"] == "oauth2"
    oa = p["properties"]["connectionParameters"]["token"]["oAuthSettings"]
    assert oa["identityProvider"] == "aad" and oa["scopes"] == ["https://cognitiveservices.azure.com/.default"]
    assert "/openai/v1/chat/completions" in d["paths"]
    assert oa["clientId"].startswith("REPLACE"), "the app registration id is typed in the portal, never committed"
    assert "clientSecret" not in json.dumps(p) and "secret" not in oa


def test_foundry_host_is_a_placeholder_for_the_lab_resource():
    assert load("connectors/foundry/apiDefinition.swagger.json")["host"].startswith("REPLACE-WITH")


def test_claude_connector_has_no_connection_auth_and_takes_the_key_as_an_internal_header_parameter():
    d, p = load("connectors/anthropic/apiDefinition.swagger.json"), load("connectors/anthropic/apiProperties.json")
    assert d["securityDefinitions"] == {} and p["properties"]["connectionParameters"] == {}
    params = {x["name"]: x for x in d["paths"]["/v1/messages"]["post"]["parameters"]}
    assert params["x-api-key"]["in"] == "header" and params["x-api-key"]["x-ms-visibility"] == "internal" and "default" not in params["x-api-key"]
    assert params["anthropic-version"]["default"] == "2026-10-21"


def test_no_key_shaped_string_anywhere_in_src():
    pat = re.compile(r"sk-[A-Za-z0-9_-]{16,}|sk-ant-[A-Za-z0-9_-]{8,}|AIza[0-9A-Za-z_-]{20,}|Bearer [A-Za-z0-9._-]{20,}")
    for f in SRC.rglob("*"):
        if f.is_file() and f.suffix in {".json", ".md", ".py", ".bicep", ".yaml", ".yml", ".jsonl"}:
            assert not pat.search(f.read_text(encoding="utf-8")), f


def test_flow_file_is_what_the_generator_writes():
    assert json.loads(json.dumps(build_flow.build())) == load("flows/ClaudeTriage/workflow.json")


def test_flow_reads_the_secret_with_secure_outputs_and_hides_the_connector_inputs():
    w = load("flows/ClaudeTriage/workflow.json")["properties"]["definition"]
    k = w["actions"]["Get_key"]
    assert k["inputs"]["parameters"]["actionName"] == "RetrieveEnvironmentVariableSecretValue"
    assert k["inputs"]["parameters"]["item/EnvironmentVariableName"] == "cin_AnthropicApiKey"
    assert k["runtimeConfiguration"]["secureData"]["properties"] == ["outputs"]
    t = w["actions"]["Triage"]
    assert t["runtimeConfiguration"]["secureData"]["properties"] == ["inputs"], "the key is an input of the connector action"
    assert t["inputs"]["parameters"]["x-api-key"] == "@outputs('Get_key')?['body/EnvironmentVariableSecretValue']"


def test_flow_takes_notes_photo_model_and_answers_text_or_error_never_the_key():
    w = load("flows/ClaudeTriage/workflow.json")["properties"]["definition"]
    props = w["triggers"]["manual"]["inputs"]["schema"]["properties"]
    assert set(props) == {"notes", "photo", "model"} and w["triggers"]["manual"]["kind"] == "Button"
    for name in ("Respond_ok", "Respond_error"):
        a = w["actions"][name]
        assert a["type"] == "Response" and a["kind"] == "PowerApp" and set(a["inputs"]["body"]) == {"text", "error"}
    assert set(w["actions"]["Respond_error"]["runAfter"]) == {"Triage", "Get_key"}
    assert "EnvironmentVariableSecretValue" not in json.dumps(w["actions"]["Respond_ok"])


def test_flow_prompt_is_the_system_prompt_file():
    w = load("flows/ClaudeTriage/workflow.json")["properties"]["definition"]
    assert w["actions"]["System_prompt"]["inputs"] == (SRC / "prompts" / "system.md").read_text(encoding="utf-8").strip()


@pytest.fixture(scope="module")
def arm(tmp_path_factory):
    out = tmp_path_factory.mktemp("bicep") / "main.json"
    r = subprocess.run([BICEP, "build", str(SRC / "infra" / "main.bicep"), "--outfile", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "Warning" not in r.stderr, r.stderr
    return json.loads(out.read_text())


def test_bicep_lints_clean():
    r = subprocess.run([BICEP, "lint", str(SRC / "infra" / "main.bicep")], capture_output=True, text=True)
    assert r.returncode == 0 and "Warning" not in r.stdout + r.stderr, r.stdout + r.stderr


def _res(arm):
    return list(arm["resources"].values()) if isinstance(arm["resources"], dict) else arm["resources"]


def test_bicep_creates_an_account_a_deployment_a_vault_and_three_role_assignments(arm):
    types = sorted(r["type"] for r in _res(arm))
    assert types == ["Microsoft.Authorization/roleAssignments"] * 3 + ["Microsoft.CognitiveServices/accounts", "Microsoft.CognitiveServices/accounts/deployments", "Microsoft.KeyVault/vaults"]
    conditional = [r for r in _res(arm) if r["type"].endswith("roleAssignments") and "condition" in r]
    assert len(conditional) == 1 and "dataverseServicePrincipalId" in conditional[0]["condition"], "only the Dataverse grant is optional"


def test_bicep_account_is_s0_entra_only_with_a_custom_subdomain_in_sweden_central(arm):
    acc = next(r for r in _res(arm) if r["type"] == "Microsoft.CognitiveServices/accounts")
    assert acc["kind"] == "OpenAI" and acc["sku"]["name"] == "S0"
    assert acc["properties"]["disableLocalAuth"] is True and "customSubDomainName" in acc["properties"]
    assert arm["parameters"]["location"]["defaultValue"] == "swedencentral"


def test_bicep_deployment_is_standard_and_the_model_is_a_parameter(arm):
    dep = next(r for r in _res(arm) if r["type"].endswith("/deployments"))
    assert dep["sku"]["name"] == "Standard"
    assert dep["properties"]["model"]["name"] == "[parameters('modelName')]"
    assert arm["parameters"]["capacityK"]["maxValue"] <= 50


def test_bicep_vault_uses_rbac_standard_sku_and_soft_delete_as_learn_recommends(arm):
    kv = next(r for r in _res(arm) if r["type"] == "Microsoft.KeyVault/vaults")
    p = kv["properties"]
    assert p["enableRbacAuthorization"] is True and p["sku"]["name"] == "standard" and p["enableSoftDelete"] is True
    assert "purge" in kv["tags"]["teardown"]


def test_bicep_roles_are_the_named_built_ins(arm):
    v = arm["variables"]
    assert v["openAiUserRoleId"] == "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"
    assert v["keyVaultSecretsUserRoleId"] == "4633458b-17de-408a-b874-0445c86b69e6" and v["keyVaultSecretsOfficerRoleId"] == "b86a8fe4-44ce-4948-aee5-eccb2c155cd7"
    for r in _res(arm):
        if r["type"].endswith("roleAssignments"):
            assert r["properties"]["principalType"] in {"User", "ServicePrincipal"}


def test_bicep_names_get_a_unique_suffix_and_there_are_no_secrets(arm):
    assert "uniqueString" in arm["parameters"]["accountName"]["defaultValue"] and "uniqueString" in arm["parameters"]["keyVaultName"]["defaultValue"]
    text = json.dumps(arm)
    assert "listKeys" not in text and "apiKey" not in text
    assert "resource group" in next(r for r in _res(arm) if r["type"] == "Microsoft.CognitiveServices/accounts")["tags"]["teardown"]
