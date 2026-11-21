"""Identity guardrails on the COMPILED Graph Bicep template (bicep build), no tenant needed."""
import json
import re

from conftest import bicep


def props(resources, name):
    return resources[name]["properties"]


def test_build_has_no_warnings(compiled):
    # A misplaced Graph property (e.g. requestedAccessTokenVersion at the top level instead of under api)
    # is only warning BCP037 and the build still succeeds, so warnings fail here.
    _, stderr = compiled
    assert stderr.strip() == ""


def test_params_file_builds():
    out, stderr = bicep("build-params", "env/lab.bicepparam")
    assert stderr.strip() == ""
    params = json.loads(out["parametersJson"])["parameters"]
    assert params["readerPrincipalIds"]["value"] == [] and params["ownerObjectIds"]["value"] == []  # none committed


def test_api_uses_v2_tokens_and_a_secure_app_id_uri(resources):
    app = props(resources, "api")
    assert app["api"]["requestedAccessTokenVersion"] == 2
    assert app["signInAudience"] == "AzureADMyOrg"
    [uri] = app["identifierUris"]
    # api://{tenantId}/{string} is one of the secure patterns; the tenant ID comes from tenant() at deploy time
    assert uri == "[format('api://{0}/{1}-orders', tenant().tenantId, parameters('workload'))]"


def test_no_secrets_or_certificates_on_the_app(resources):
    for name in ("api", "apiSp"):
        p = props(resources, name)
        assert "passwordCredentials" not in p and "keyCredentials" not in p


def test_app_roles_are_split_by_member_type(resources):
    roles = {r["value"]: r for r in props(resources, "api")["appRoles"]}
    assert roles["Orders.ReadWrite.All"]["allowedMemberTypes"] == ["Application"]
    assert roles["Orders.Reader"]["allowedMemberTypes"] == ["User"]
    assert all(r["isEnabled"] for r in roles.values())


def test_delegated_scope_is_read_only(resources):
    scopes = props(resources, "api")["api"]["oauth2PermissionScopes"]
    assert [s["value"] for s in scopes] == ["Orders.Read"]


def test_idtyp_optional_claim_on_access_tokens(resources):
    claims = props(resources, "api")["optionalClaims"]["accessToken"]
    assert {"name": "idtyp", "essential": False} in claims


def test_assignment_is_required(resources):
    assert props(resources, "apiSp")["appRoleAssignmentRequired"] is True


def test_ids_are_stable_guids(resources, template):
    # guid(...) over constant inputs: the same IDs on every deployment
    ids = template["variables"]["ids"]
    assert set(ids) == {"readScope", "writeRole", "readerRole"}
    assert all(v.startswith("[guid(parameters('workload'), 'orders-api'") for v in ids.values())


def test_processor_identity_gets_only_the_write_role(resources):
    a = props(resources, "processorCanWrite")
    assert a["appRoleId"] == "[variables('ids').writeRole]"
    assert "processor" in a["principalId"] and "apiSp" in a["resourceId"]


def test_readers_get_the_user_role_only(resources):
    r = resources["readers"]
    assert r["copy"]["count"] == "[length(parameters('readerPrincipalIds'))]"
    assert r["properties"]["appRoleId"] == "[variables('ids').readerRole]"


def test_outputs_expose_ids_not_secrets(template):
    outs = template["outputs"]
    assert set(outs) == {"tenantId", "apiClientId", "apiAppIdUri", "readScope", "processorClientId",
                         "processorPrincipalId", "processorResourceId"}
    assert not any(re.search(r"(?i)secret|password|key", n) for n in outs)
