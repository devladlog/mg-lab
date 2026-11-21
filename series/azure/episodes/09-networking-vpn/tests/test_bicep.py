import subprocess

from conftest import ROOT, one, resources


def test_bicep_lint_is_clean():
    r = subprocess.run(["bicep", "lint", str(ROOT / "infra" / "main.bicep")], capture_output=True, text=True)
    assert r.returncode == 0 and "Warning" not in r.stderr and "Error" not in r.stderr, r.stderr


def test_gateway_uses_an_az_sku_standard_zone_redundant_ip_and_p2s_certificates(main):
    gw = one(main, "Microsoft.Network/virtualNetworkGateways")["properties"]
    assert gw["gatewayType"] == "Vpn" and gw["vpnType"] == "RouteBased"
    assert gw["sku"] == {"name": "VpnGw1AZ", "tier": "VpnGw1AZ"}  # VpnGw1..5 non-AZ can no longer be created
    ip = one(main, "Microsoft.Network/publicIPAddresses")
    assert ip["sku"]["name"] == "Standard" and ip["properties"]["publicIPAllocationMethod"] == "Static"
    assert ip["zones"] == ["1", "2", "3"]
    vpn = gw["vpnClientConfiguration"]
    assert vpn["vpnAuthenticationTypes"] == ["Certificate"]
    assert set(vpn["vpnClientProtocols"]) == {"IkeV2", "OpenVPN"}  # no SSTP: being retired, 128-connection cap
    assert "p2sRootCertData" in str(vpn["vpnClientRootCertificates"])


def test_gateway_subnet_has_no_nsg(main):
    # Learn: NSGs on the gateway subnet aren't supported and can stop the gateway from working.
    hub = next(r for r in resources(main, "Microsoft.Network/virtualNetworks") if r["name"] == "vnet-hub")
    for s in hub["properties"]["subnets"]:
        assert s["name"] == "GatewaySubnet"
        assert "networkSecurityGroup" not in s["properties"]


def test_peering_is_set_up_in_both_directions_for_gateway_transit(main):
    peerings = {r["name"]: r["properties"]
                for r in resources(main, "Microsoft.Network/virtualNetworks/virtualNetworkPeerings")}
    hub = next(p for n, p in peerings.items() if "hub-to-orders" in n)
    spoke = next(p for n, p in peerings.items() if "orders-to-hub" in n)
    assert hub["allowGatewayTransit"] is True and hub["useRemoteGateways"] is False
    assert spoke["allowGatewayTransit"] is False and spoke["useRemoteGateways"] is True
    assert hub["allowForwardedTraffic"] is True and spoke["allowForwardedTraffic"] is True


def test_spoke_peering_waits_for_the_gateway(main):
    spoke = next(r for r in resources(main, "Microsoft.Network/virtualNetworks/virtualNetworkPeerings")
                 if "orders-to-hub" in r["name"])
    assert any("vgw-hub" in d or "virtualNetworkGateways" in d for d in spoke["dependsOn"])


def test_workload_is_private_and_only_the_vpn_pool_reaches_it(main):
    assert resources(main, "Microsoft.Network/publicIPAddresses").__len__() == 1  # the gateway's, nothing for the VM
    nic = one(main, "Microsoft.Network/networkInterfaces")["properties"]["ipConfigurations"][0]["properties"]
    assert "publicIPAddress" not in nic and nic["privateIPAllocationMethod"] == "Static"
    rules = {r["name"]: r["properties"] for r in one(main, "Microsoft.Network/networkSecurityGroups")["properties"]["securityRules"]}
    allow = rules["allow-orders-from-vpn-pool"]
    assert allow["access"] == "Allow" and allow["destinationPortRange"] == "8080"
    assert allow["sourceAddressPrefix"] == "[parameters('p2sPoolPrefix')]"
    assert rules["deny-all-inbound"]["access"] == "Deny" and rules["deny-all-inbound"]["priority"] > allow["priority"]
    assert not any(p.get("sourceAddressPrefix") in ("*", "Internet") and p["access"] == "Allow" for p in rules.values())
    spoke = next(r for r in resources(main, "Microsoft.Network/virtualNetworks") if r["name"] == "vnet-orders")
    assert spoke["properties"]["subnets"][0]["properties"]["defaultOutboundAccess"] is False


def test_vm_has_no_password_login(main):
    vm = one(main, "Microsoft.Compute/virtualMachines")["properties"]["osProfile"]
    assert vm["linuxConfiguration"]["disablePasswordAuthentication"] is True
    assert "adminPassword" not in vm


def test_no_secret_in_outputs(main):
    assert set(main["outputs"]) == {"gatewayName", "gatewayPublicIpName", "vmName", "vmPrivateIp"}
