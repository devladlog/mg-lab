"""
Architecture guardrails as tests. They read the COMPILED template (bicep build), so they check what
Azure Resource Manager will actually receive, not what the author meant to write.
Run: python -m pytest tests/guardrails -q
"""
import json
import re

# Types that can't carry tags (or are child settings of a tagged parent)
UNTAGGABLE = {
    "microsoft.authorization/roleassignments",
    "microsoft.insights/diagnosticsettings",
    "microsoft.storage/storageaccounts/blobservices",
    "microsoft.storage/storageaccounts/blobservices/containers",
    "microsoft.network/privateendpoints/privatednszonegroups",
    "microsoft.web/sites/basicpublishingcredentialspolicies",
}

ALLOWED_ROLES = {
    "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1": "Storage Blob Data Reader",
    "4633458b-17de-408a-b874-0445c86b69e6": "Key Vault Secrets User",
}
BROAD_ROLES = {  # never assigned by this workload
    "8e3af657-a8ff-443c-a75c-2fe8c4bcb635": "Owner",
    "b24988ac-6180-42a0-ab88-20f7382dd24c": "Contributor",
}


def module(main_template: dict, name: str) -> dict:
    """The compiled template of one Bicep module (a nested deployment)."""
    return next(r["properties"]["template"] for r in main_template["resources"]
                if r["type"] == "Microsoft.Resources/deployments" and r["name"] == name)


def is_expression(value) -> bool:
    return isinstance(value, str) and value.startswith("[") and value.endswith("]")


def test_every_taggable_resource_has_tags(resources):
    missing = [f"{m}/{s} ({r['type']})" for m, s, r in resources
               if r["type"].lower() not in UNTAGGABLE and "tags" not in r]
    assert missing == []


def test_no_hardcoded_locations(resources):
    bad = [f"{m}/{s}: {r['location']}" for m, s, r in resources
           if "location" in r and not is_expression(r["location"]) and r["location"] != "global"]
    assert bad == []


def test_storage_is_private_and_keyless(of_type):
    [st] = of_type("Microsoft.Storage/storageAccounts")
    p = st["properties"]
    assert p["publicNetworkAccess"] == "Disabled"
    assert p["allowSharedKeyAccess"] is False
    assert p["allowBlobPublicAccess"] is False
    assert p["minimumTlsVersion"] == "TLS1_2"
    assert p["networkAcls"]["defaultAction"] == "Deny"


def test_key_vault_is_private_and_uses_rbac(of_type):
    [kv] = of_type("Microsoft.KeyVault/vaults")
    p = kv["properties"]
    assert p["enableRbacAuthorization"] is True
    assert p["publicNetworkAccess"] == "Disabled"
    assert p["networkAcls"]["defaultAction"] == "Deny"
    assert p["enableSoftDelete"] is True


def test_web_app_baseline(of_type):
    [app] = of_type("Microsoft.Web/sites")
    p, cfg = app["properties"], app["properties"]["siteConfig"]
    assert p["httpsOnly"] is True
    assert p["clientAffinityEnabled"] is False
    assert is_expression(p["virtualNetworkSubnetId"])
    assert cfg["linuxFxVersion"] == "DOTNETCORE|10.0"
    assert cfg["minTlsVersion"] == "1.2"
    assert cfg["ftpsState"] == "Disabled"
    assert cfg["healthCheckPath"] == "/healthz"
    assert app["identity"]["type"] == "UserAssigned"


def test_app_settings_hold_no_secrets(of_type):
    [app] = of_type("Microsoft.Web/sites")
    names = {s["name"] for s in app["properties"]["siteConfig"]["appSettings"]}
    assert names == {"AZURE_CLIENT_ID", "Probe__BlobContainerUri", "Probe__KeyVaultUri"}
    assert not any(re.search(r"password|secret|connectionstring|accountkey", n, re.I) for n in names)
    assert all(is_expression(s["value"]) for s in app["properties"]["siteConfig"]["appSettings"])


def test_every_data_service_has_a_private_endpoint(of_type):
    groups = sorted(g for pe in of_type("Microsoft.Network/privateEndpoints")
                    for c in pe["properties"]["privateLinkServiceConnections"]
                    for g in c["properties"]["groupIds"])
    assert groups == ["blob", "vault"]
    zone_groups = of_type("Microsoft.Network/privateEndpoints/privateDnsZoneGroups")
    assert len(zone_groups) == 2, "each endpoint registers its A record in a private DNS zone"


def test_private_dns_zone_names_follow_the_documented_scheme(main_template):
    names = module(main_template, "network")["variables"]["privateDnsZoneNames"]
    assert names == ["[format('privatelink.blob.{0}', environment().suffixes.storage)]",
                     "privatelink.vaultcore.azure.net"]


def test_logs_go_to_one_workspace(of_type):
    diags = of_type("Microsoft.Insights/diagnosticSettings")
    assert len(diags) == 3  # blob service, key vault, web app
    assert all(is_expression(d["properties"]["workspaceId"]) for d in diags)
    assert len(of_type("Microsoft.OperationalInsights/workspaces")) == 1


def test_role_assignments_are_least_privilege(of_type):
    assignments = of_type("Microsoft.Authorization/roleAssignments")
    assert len(assignments) == 2
    for ra in assignments:
        p = ra["properties"]
        assert p["principalType"] == "ServicePrincipal"
        # role comes from the module's 'roles' variable (pinned below), scoped to one resource, not the group
        assert "variables('roles')" in p["roleDefinitionId"]
        assert "scope" in ra
    assert not any(g in json.dumps(assignments) for g in BROAD_ROLES)


def test_role_definitions_are_the_two_data_roles(main_template):
    app = module(main_template, "app")
    assert app["variables"]["roles"] == {"storageBlobDataReader": "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1",
                                         "keyVaultSecretsUser": "4633458b-17de-408a-b874-0445c86b69e6"}
    assert set(app["variables"]["roles"].values()) == set(ALLOWED_ROLES)


def test_subnets_app_delegated_both_private_with_nsg(of_type):
    [vnet] = of_type("Microsoft.Network/virtualNetworks")
    subnets = {s["name"]: s["properties"] for s in vnet["properties"]["subnets"]}
    assert subnets["snet-app"]["delegations"][0]["properties"]["serviceName"] == "Microsoft.Web/serverFarms"
    assert int(subnets["snet-app"]["addressPrefix"].split("/")[1]) <= 26  # /26 recommended, /28 minimum
    for name, s in subnets.items():
        assert "networkSecurityGroup" in s, name
        assert s["defaultOutboundAccess"] is False, name


def test_environment_profiles_differ_only_in_resilience(main_template):
    profiles = main_template["variables"]["profiles"]
    assert set(profiles) == {"lab", "prod"}
    assert profiles["lab"].keys() == profiles["prod"].keys()  # same shape, different values
    prod, lab = profiles["prod"], profiles["lab"]
    assert prod["zoneRedundant"] is True and prod["planCapacity"] >= 2
    assert re.fullmatch(r"P\dv[34]", prod["planSku"])  # zone redundancy: Premium v2-v4
    assert prod["storageSku"].endswith("ZRS")
    assert prod["keyVaultPurgeProtection"] is True
    assert lab["planSku"] == "B1" and lab["zoneRedundant"] is False


def test_parameter_files_select_the_environment(params):
    for env in ("lab", "prod"):
        values = json.loads(params(env)["parametersJson"])["parameters"]
        assert values["environment"]["value"] == env


def test_governance_assigns_two_builtin_deny_policies(governance_template):
    assert governance_template["variables"]["definitions"] == {
        "allowedLocations": "e56962a6-4747-49cd-b67b-bf8b01975c4c",  # Allowed locations
        "requireTag": "871b6d14-10aa-478d-b590-94f262ecfa99",        # Require a tag on resources
    }
    res = governance_template["resources"]
    items = list(res.values()) if isinstance(res, dict) else res
    assert len(items) == 2
    assert all(r["properties"]["policyDefinitionId"].startswith("[tenantResourceId(") for r in items)
