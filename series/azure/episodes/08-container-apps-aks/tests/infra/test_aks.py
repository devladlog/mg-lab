from conftest import one

B_SERIES_PREFIX = "Standard_B"
FOUR_VCPU = {"Standard_D4as_v5", "Standard_D4s_v5", "Standard_D4ads_v5", "Standard_D4ds_v5"}


def test_free_tier_control_plane(aks):
    mc = one(aks, "Microsoft.ContainerService/managedClusters")
    assert mc["sku"] == {"name": "Base", "tier": "Free"}


def test_one_small_but_supported_system_node(aks):
    pool = one(aks, "Microsoft.ContainerService/managedClusters")["properties"]["agentPoolProfiles"][0]
    assert pool["mode"] == "System"
    assert pool["count"] == "[parameters('nodeCount')]"
    assert aks["parameters"]["nodeCount"]["defaultValue"] == 1
    size = aks["parameters"]["nodeVmSize"]["defaultValue"]
    assert not size.startswith(B_SERIES_PREFIX), "B-series isn't supported for system node pools"
    assert size in FOUR_VCPU, "Learn: system node pools need at least 4 vCPUs"
    assert pool["osDiskType"] == "Managed" and pool["osDiskSizeGB"] == 64


def test_kubelet_identity_gets_acrpull_on_the_registry(aks):
    ra = one(aks, "Microsoft.Authorization/roleAssignments")
    assert "kubeletidentity" in ra["properties"]["principalId"]
    assert "acrPullRole" in ra["properties"]["roleDefinitionId"]
    assert aks["variables"]["acrPullRole"] == "7f951dda-4ed3-4680-a7ca-43fe172d538d"
