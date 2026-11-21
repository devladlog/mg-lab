from conftest import one, resources


def test_registry_has_no_admin_user_and_accepts_arm_audience_tokens(aca):
    acr = one(aca, "Microsoft.ContainerRegistry/registries")
    assert acr["sku"]["name"] == "Basic"
    assert acr["properties"]["adminUserEnabled"] is False
    assert acr["properties"]["policies"]["azureADAuthenticationAsArmPolicy"]["status"] == "enabled"


def test_app_pulls_with_the_user_assigned_identity_that_has_acrpull(aca):
    app = one(aca, "Microsoft.App/containerApps")
    reg = app["properties"]["configuration"]["registries"]
    assert len(reg) == 1 and "userAssignedIdentities" in reg[0]["identity"]
    assert "id-{0}-pull" in reg[0]["identity"]   # the same identity the app carries, not another one
    assert "passwordSecretRef" not in reg[0]
    pulls = [r for r in resources(aca, "Microsoft.Authorization/roleAssignments")
             if "acrPull" in r["properties"]["roleDefinitionId"]]
    assert len(pulls) == 1
    assert "userAssignedIdentities" in pulls[0]["properties"]["principalId"]
    assert aca["variables"]["roles"]["acrPull"] == "7f951dda-4ed3-4680-a7ca-43fe172d538d"
    assert aca["variables"]["roles"]["acrPush"] == "8311e382-0749-4cb8-b61a-304f252e45ec"


def test_app_is_created_only_in_phase_two_and_after_the_role(aca):
    app = one(aca, "Microsoft.App/containerApps")
    assert app["condition"] == "[parameters('deployApp')]"
    assert any("roleAssignments" in d for d in app["dependsOn"])
    assert aca["parameters"]["deployApp"]["defaultValue"] is False


def test_environment_is_workload_profiles_with_consumption(aca):
    env = one(aca, "Microsoft.App/managedEnvironments")
    assert env["properties"]["workloadProfiles"] == [{"name": "Consumption", "workloadProfileType": "Consumption"}]
    app = one(aca, "Microsoft.App/containerApps")
    assert app["properties"]["workloadProfileName"] == "Consumption"


def test_multiple_revisions_and_ingress_on_8080(aca):
    cfg = one(aca, "Microsoft.App/containerApps")["properties"]["configuration"]
    assert cfg["activeRevisionsMode"] == "Multiple"
    ing = cfg["ingress"]
    assert ing["external"] is True and ing["targetPort"] == 8080 and ing["allowInsecure"] is False
    assert ing["traffic"] == [{"latestRevision": True, "weight": 100}]


def test_scales_to_zero_on_http_concurrency(aca):
    scale = one(aca, "Microsoft.App/containerApps")["properties"]["template"]["scale"]
    assert scale["minReplicas"] == 0
    assert scale["maxReplicas"] == "[parameters('maxReplicas')]"
    rule = scale["rules"][0]
    assert rule["http"]["metadata"]["concurrentRequests"] == "[string(parameters('concurrentRequests'))]"
    assert aca["parameters"]["concurrentRequests"]["defaultValue"] == 20


def test_probes_use_the_apps_own_endpoints(aca):
    c = one(aca, "Microsoft.App/containerApps")["properties"]["template"]["containers"][0]
    probes = {p["type"]: p["httpGet"] for p in c["probes"]}
    assert probes == {
        "Startup": {"path": "/healthz/live", "port": 8080},
        "Readiness": {"path": "/healthz/ready", "port": 8080},
        "Liveness": {"path": "/healthz/live", "port": 8080},
    }
    assert c["resources"]["memory"] == "0.5Gi"


def test_log_workspace_has_a_daily_cap(aca):
    ws = one(aca, "Microsoft.OperationalInsights/workspaces")
    assert ws["properties"]["workspaceCapping"]["dailyQuotaGb"] == 1


def test_no_secret_outputs_or_parameters(aca):
    assert set(aca["outputs"]) == {"acrName", "acrLoginServer", "environmentName", "appName", "appUrl"}
    assert not [p for p in aca["parameters"].values() if p["type"].lower().startswith("secure")]
