"""Cross-file contracts: the names and numbers that must agree between the app, Dapr, KEDA, Kubernetes and Bicep."""
import re

import pytest

from conftest import ROOT, arm_eval, program_constants, resources

NAMESPACE = "contoso-finance"


def doc(rendered, file, kind):
    return next(d for d in rendered[file] if d and d["kind"] == kind)


def test_every_manifest_is_valid_yaml_with_kind_and_apiversion(rendered):
    assert set(rendered) == {"00-namespace-and-identity.yaml", "10-dapr-component.yaml", "20-deployment.yaml", "30-keda.yaml"}
    for f, docs in rendered.items():
        for d in docs:
            assert d["apiVersion"] and d["kind"] and d["metadata"]["name"], f


def test_no_token_survives_rendering(rendered):
    assert "{{" not in str(rendered)


# ---- the subscription name: Bicep = Dapr consumerID = KEDA ------------------------------------------------------
def test_one_subscription_name_everywhere(arm, rendered):
    topic = resources(arm, "Microsoft.ServiceBus/namespaces/topics")[0]
    subs = resources(arm, "Microsoft.ServiceBus/namespaces/topics/subscriptions")
    assert [arm_eval(s["name"], arm).split("/")[-1] for s in subs] == ["finance-review"]
    comp = doc(rendered, "10-dapr-component.yaml", "Component")
    meta = {m["name"]: m["value"] for m in comp["spec"]["metadata"]}
    keda = next(d for d in rendered["30-keda.yaml"] if d["kind"] == "ScaledObject")["spec"]["triggers"][0]["metadata"]
    assert meta["consumerID"] == keda["subscriptionName"] == "finance-review"
    assert keda["topicName"] == arm_eval(topic["name"], arm).split("/")[-1] == program_constants()["Topic"] == "purchase-events"


def test_the_finance_subscription_only_takes_purchase_high(arm):
    rule = resources(arm, "Microsoft.ServiceBus/namespaces/topics/subscriptions/rules")[0]
    assert arm_eval(rule["name"], arm).endswith("/finance-review/$Default")
    assert rule["properties"]["filterType"] == "CorrelationFilter"
    assert rule["properties"]["correlationFilter"]["label"] == "purchase.high"


# ---- Dapr ----------------------------------------------------------------------------------------------------------------
def test_dapr_component_uses_entra_not_keys_and_does_not_manage_entities(rendered):
    comp = doc(rendered, "10-dapr-component.yaml", "Component")
    assert comp["spec"]["type"] == "pubsub.azure.servicebus.topics"
    meta = {m["name"]: m["value"] for m in comp["spec"]["metadata"]}
    assert meta["namespaceName"].endswith(".servicebus.windows.net")
    assert meta["disableEntityManagement"] == "true"
    assert not {"connectionString", "azureClientSecret"} & set(meta)


def test_component_name_and_app_id_match_the_code_and_the_deployment(rendered):
    comp = doc(rendered, "10-dapr-component.yaml", "Component")
    assert comp["metadata"]["name"] == program_constants()["PubSubName"] == "purchase-pubsub"
    ann = doc(rendered, "20-deployment.yaml", "Deployment")["spec"]["template"]["metadata"]["annotations"]
    assert ann["dapr.io/enabled"] == "true"
    assert comp["scopes"] == [ann["dapr.io/app-id"]] == ["finance-worker"]


def test_buffer_is_small_enough_that_new_replicas_get_work(rendered):
    """Dapr buffers up to maxActiveMessages (default 1000) per replica: keep it near the KEDA target so one replica cannot hold a whole burst."""
    comp = doc(rendered, "10-dapr-component.yaml", "Component")
    meta = {m["name"]: m["value"] for m in comp["spec"]["metadata"]}
    keda = next(d for d in rendered["30-keda.yaml"] if d["kind"] == "ScaledObject")["spec"]["triggers"][0]["metadata"]
    assert int(meta["maxActiveMessages"]) <= 2 * int(keda["messageCount"])
    assert int(meta["maxConcurrentHandlers"]) <= int(meta["maxActiveMessages"])


# ---- Kubernetes ----------------------------------------------------------------------------------------------------------
def test_deployment_is_workload_identity_enabled_and_hardened(rendered):
    dep = doc(rendered, "20-deployment.yaml", "Deployment")
    pod = dep["spec"]["template"]
    assert pod["metadata"]["labels"]["azure.workload.identity/use"] == "true"
    assert pod["spec"]["serviceAccountName"] == "finance-worker"
    c = pod["spec"]["containers"][0]
    assert c["securityContext"]["runAsNonRoot"] is True and c["securityContext"]["allowPrivilegeEscalation"] is False
    assert c["securityContext"]["readOnlyRootFilesystem"] is True
    assert c["resources"]["requests"] and c["resources"]["limits"]
    assert c["image"].endswith("finance-worker:1")


def test_the_deployment_has_no_replicas_field_because_keda_owns_it(rendered):
    assert "replicas" not in doc(rendered, "20-deployment.yaml", "Deployment")["spec"]


def test_app_port_matches_the_dockerfile(rendered):
    port = doc(rendered, "20-deployment.yaml", "Deployment")["spec"]["template"]["metadata"]["annotations"]["dapr.io/app-port"]
    docker = (ROOT / "src" / "FinanceReview.Worker" / "Dockerfile").read_text()
    assert f"ASPNETCORE_HTTP_PORTS={port}" in docker
    c = doc(rendered, "20-deployment.yaml", "Deployment")["spec"]["template"]["spec"]["containers"][0]
    assert c["ports"][0]["containerPort"] == int(port)


def test_dockerfile_runs_as_the_numeric_non_root_user_with_pinned_bases():
    docker = (ROOT / "src" / "FinanceReview.Worker" / "Dockerfile").read_text()
    assert re.search(r"^USER 1654$", docker, re.M)
    assert len(re.findall(r"^FROM .+@sha256:[0-9a-f]{64}", docker, re.M)) == 2
    assert 'ENTRYPOINT ["dotnet", "FinanceReview.Worker.dll"]' in docker


# ---- KEDA ------------------------------------------------------------------------------------------------------------------
def test_keda_uses_workload_identity_and_scales_from_zero(rendered):
    auth = next(d for d in rendered["30-keda.yaml"] if d["kind"] == "TriggerAuthentication")
    so = next(d for d in rendered["30-keda.yaml"] if d["kind"] == "ScaledObject")
    assert auth["spec"]["podIdentity"]["provider"] == "azure-workload"
    assert auth["spec"]["podIdentity"]["identityId"] == "22222222-2222-2222-2222-222222222222"
    assert auth["metadata"]["namespace"] == so["metadata"]["namespace"] == NAMESPACE  # Learn: same namespace
    trig = so["spec"]["triggers"][0]
    assert trig["type"] == "azure-servicebus" and trig["authenticationRef"]["name"] == auth["metadata"]["name"]
    assert "." not in trig["metadata"]["namespace"]  # the namespace NAME, as in Learn's tutorial, not the FQDN
    assert so["spec"]["scaleTargetRef"]["name"] == "finance-worker"
    assert so["spec"]["minReplicaCount"] == 0 and so["spec"]["maxReplicaCount"] == 10
    assert "connection" not in trig["metadata"] and "connectionFromEnv" not in trig["metadata"]


def test_the_namespace_name_in_keda_is_a_prefix_of_the_dapr_host(rendered):
    comp = doc(rendered, "10-dapr-component.yaml", "Component")
    host = next(m["value"] for m in comp["spec"]["metadata"] if m["name"] == "namespaceName")
    ns = next(d for d in rendered["30-keda.yaml"] if d["kind"] == "ScaledObject")["spec"]["triggers"][0]["metadata"]["namespace"]
    assert host == f"{ns}.servicebus.windows.net"


# ---- Bicep: identity, network of trust, cost ----------------------------------------------------------------------
def test_service_bus_is_entra_only_with_duplicate_detection(arm):
    sb = resources(arm, "Microsoft.ServiceBus/namespaces")[0]
    assert sb["sku"]["name"] == "Standard" and sb["properties"]["disableLocalAuth"] is True
    assert resources(arm, "Microsoft.ServiceBus/namespaces/topics")[0]["properties"]["requiresDuplicateDetection"] is True


def test_aks_has_workload_identity_oidc_and_keda_on_the_free_tier(arm):
    aks = resources(arm, "Microsoft.ContainerService/managedClusters")[0]
    p = aks["properties"]
    assert aks["sku"] == {"name": "Base", "tier": "Free"}
    assert p["oidcIssuerProfile"]["enabled"] is True
    assert p["securityProfile"]["workloadIdentity"]["enabled"] is True
    assert p["workloadAutoScalerProfile"]["keda"]["enabled"] is True


def test_dapr_extension_runs_without_ha_in_the_lab(arm):
    ext = resources(arm, "Microsoft.KubernetesConfiguration/extensions")[0]
    assert ext["properties"]["extensionType"] == "microsoft.dapr"
    assert ext["properties"]["configurationSettings"]["global.ha.enabled"] == "false"
    assert ext["properties"]["scope"]["cluster"]["releaseNamespace"] == "dapr-system"


def test_federated_credentials_trust_exactly_the_two_service_accounts(arm, rendered):
    sa = doc(rendered, "00-namespace-and-identity.yaml", "ServiceAccount")["metadata"]
    subjects = sorted(arm_eval(f["properties"]["subject"], arm) for f in resources(arm, "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials"))
    assert subjects == sorted([f"system:serviceaccount:{sa['namespace']}:{sa['name']}", "system:serviceaccount:kube-system:keda-operator"])
    for f in resources(arm, "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials"):
        assert f["properties"]["audiences"] == ["api://AzureADTokenExchange"]


def test_service_account_is_annotated_with_the_worker_client_id(rendered):
    sa = doc(rendered, "00-namespace-and-identity.yaml", "ServiceAccount")
    assert sa["metadata"]["annotations"]["azure.workload.identity/client-id"] == "11111111-1111-1111-1111-111111111111"


def test_roles_are_the_three_expected_and_nothing_broad(arm):
    ra = resources(arm, "Microsoft.Authorization/roleAssignments")
    assert len(ra) == 3
    assert arm["variables"]["roles"] == {
        "serviceBusDataReceiver": "4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0",
        "serviceBusDataOwner": "090c5cfd-751d-490a-894a-3ce6f1109419",
        "acrPull": "7f951dda-4ed3-4680-a7ca-43fe172d538d",
    }
    scopes = {re.search(r"variables\('roles'\)\.(\w+)", r["properties"]["roleDefinitionId"]).group(1): r["scope"] for r in ra}
    assert "topics" in scopes["serviceBusDataReceiver"]       # the worker may receive on the topic only
    assert "registries" in scopes["acrPull"]                   # the kubelet may pull from the registry only
    assert "topics" not in scopes["serviceBusDataOwner"]       # KEDA: namespace scope, as in Learn's tutorial


def test_acr_has_no_admin_user(arm):
    assert resources(arm, "Microsoft.ContainerRegistry/registries")[0]["properties"]["adminUserEnabled"] is False
