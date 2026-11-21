# DEVLADLOG Azure #9 — Networking & VPN: a private VM reached from a laptop through a point-to-site gateway

Episodes 1–8 ran contoso's order services on public endpoints or behind private endpoints. This episode builds the part
that sits behind them: an **internal orders service** that must have no public address, and the network that lets an
administrator reach it from a laptop.

- **Hub and spoke.** Hub VNet `10.60.0.0/24` holds only `GatewaySubnet` (`10.60.0.0/27`) and a **VpnGw1AZ** gateway with a
  Standard, zone-redundant public IP. Spoke VNet `10.61.0.0/24` holds the workload subnet and one `Standard_B1s` Ubuntu VM
  with a **private IP only** (`10.61.0.4`) and a tiny HTTP service on 8080 (started by cloud-init)
- **Peering with gateway transit**, both directions: hub `allowGatewayTransit`, spoke `useRemoteGateways`
- **Point-to-site, certificate authentication**, IKEv2 + OpenVPN (no SSTP). Client pool `172.16.201.0/24`. The root and client
  certificates are made with OpenSSL on the laptop; only the root's public half goes to Azure
- **An NSG** with one allow rule (8080 from the client pool to the VM) and an explicit deny; no NSG on the gateway subnet
- **An address plan that is code.** `netplan.py` rejects overlaps (including the lab's `10.50.0.0/24`, so a site-to-site to
  the Hyper-V lab stays possible), undersized platform subnets, and a client pool that collides with a VNet
- **Network Watcher** (`test-ip-flow`, `show-next-hop`) to find out which rule or route decides

```
 laptop ── Azure VPN Client ── (IKEv2/OpenVPN, client cert) ──► vgw-hub (VpnGw1AZ, GatewaySubnet 10.60.0.0/27)
   pool 172.16.201.0/24                                          │  peering: allowGatewayTransit ⇄ useRemoteGateways
                                                                 ▼
                                    vnet-orders 10.61.0.0/24 ─ workload 10.61.0.0/26 ─ NSG ─ vm-orders-int 10.61.0.4:8080
                                    (no public IP, defaultOutboundAccess=false)
 Hyper-V lab 10.50.0.0/24: not connected, only kept free of overlaps
```

| Path | What it is |
|---|---|
| [`src/netplan/netplan.py`](src/netplan/netplan.py) | Stdlib-only checker: `check plan.json` (overlaps, 5 reserved addresses, GatewaySubnet/AzureFirewallSubnet/AzureBastionSubnet sizes, private ranges) and `params plan.json` (ARM parameters for `main.bicep`) |
| [`src/netplan/plan.json`](src/netplan/plan.json) / [`plan-overlap.json`](src/netplan/plan-overlap.json) | The plan we deploy / a plan that breaks three rules at once (for the demo) |
| [`infra/main.bicep`](infra/main.bicep) | Hub, spoke, NSG, gateway + public IP, both peerings, NIC, VM (9 resources) |
| [`infra/cloud-init.yaml`](infra/cloud-init.yaml) | The internal service (stdlib Python, systemd unit); answers with its host name and the client address it saw |
| [`infra/certs.sh`](infra/certs.sh) | OpenSSL root CA + client certificate + `.pfx` + the one-line base64 root the gateway wants |
| [`infra/deploy.sh`](infra/deploy.sh) | Plan check → certificates and SSH key (in `~/.contoso-net`) → resource group → what-if → deploy |
| [`infra/vpnclient.sh`](infra/vpnclient.sh) | Generates and downloads the VPN client package (run again after any peering change) |
| [`infra/Import-ClientCert.ps1`](infra/Import-ClientCert.ps1) | Windows: imports the `.pfx` into `CurrentUser\My` |
| [`infra/probe.py`](infra/probe.py) | TCP + HTTP probe from the laptop; `--expect closed` for the "VPN off" shot |
| [`infra/diagnose.sh`](infra/diagnose.sh) | IP flow verify (allowed and denied source) and next hop, with readable output |
| [`infra/teardown.sh`](infra/teardown.sh) | Deletes the resource group and the local state |
| [`tests/`](tests) | 31 pytest tests |

## Build and test (here, no Azure needed)

```bash
python3 -m pytest tests -q            # 31 passed
#   test_netplan 12   the shipped plan is clean; 5 reserved addresses (251 / 3 / 27 usable); VM = .4; overlap with the lab,
#                     pool inside a VNet, undersized/renamed GatewaySubnet, firewall/bastion /26, subnet overlap, public and
#                     malformed ranges; CLI exit codes; the generated parameters match what main.bicep asks for
#   test_bicep 8      bicep lint clean; VpnGw1AZ + Standard zone-redundant IP + certificate auth + IKEv2/OpenVPN; no NSG on
#                     GatewaySubnet; peering flags in both directions and spoke peering after the gateway; no public IP on the VM,
#                     one allow rule then deny, private subnet; no password login; no secrets in outputs
#   test_certs 2      certs.sh run for real: RSA 2048 root with CA:TRUE, client cert with clientAuth, chain verifies, base64 is the
#                     DER of the root on one line, .pfx opens and holds key + chain, keys not world-readable
#   test_probe 4      the service script is extracted from cloud-init.yaml and RUN; probe.py against it (reachable, client address,
#                     exit codes, unreachable with --expect closed)
#   test_script 5     script.yaml: header, 12-16 scenes, 750-900 words, 3 shorts, every code line exists in this folder

cd infra && bicep lint main.bicep                      # clean (bicepconfig.json rules at error)
for f in *.sh; do bash -n $f; done                     # syntax
pwsh -NoProfile -Command '[void][ScriptBlock]::Create((Get-Content -Raw ./Import-ClientCert.ps1))'   # parses
```

Verified in this container: Bicep 0.49.2, OpenSSL 3.0.13, pytest 9.1.1, PowerShell 7.6. Docker is not needed.

**Not run here (needs the lab subscription, see demo.md):** `deploy.sh`, `vpnclient.sh`, `diagnose.sh`, `teardown.sh` (no
`az` CLI in this container; `bash -n` only), the cloud-init on a real Ubuntu image (the service script itself was run), the
Azure VPN Client connection, `Import-ClientCert.ps1` (Windows only; parse check only), and every number marked *expected*
in demo.md. `bicep what-if` / deployment was never run, so ARM may reject something the linter accepts (for example
`Standard_B1s` capacity in the region, or the image URN `Canonical:ubuntu-24_04-lts:server:latest`).

## Cost (Azure Retail Prices API, EUR, list prices, West Europe, queried 21 Nov 2026)

| Item | Price | Note |
|---|---|---|
| VPN gateway `VpnGw1AZ` | 0.1885 / h | billed while the gateway exists, connected or not |
| Standard static public IPv4 (gateway) | 0.0045 / h | |
| `Standard_B1s` Linux VM | 0.0108 / h | the disk (30 GB StandardSSD) was not priced from the API; cents per day |
| VNet peering | traffic is charged per GB | Learn: "nominal charge for ingress and egress traffic"; a few KB here |
| **Recording window, 3 h** | **about 0.6 EUR** | 45+ min of gateway creation counts: it bills from creation |
| Left running a month | about 138 EUR | 0.1885 x 730 h, against a 30 EUR budget |

The API also lists a "VpnGw1AZ P2S Connection" meter at 0.009 / h; whether one connection triggers it was not checked.

## What we learned / gotchas

- **New gateways must be AZ SKUs with a Standard public IP.** Learn (gateway SKUs): "VpnGw1~5 are slated for migration and
  should not be used to create new VPN gateways"; "When you create a new VPN gateway, you must use a Standard SKU public IP".
  The Basic SKU still exists (PowerShell/CLI only, IKEv2 for P2S since Nov 2025) but **gateway transit does not support it**.
- **Creating a gateway "can often take 45 minutes or more"** (Learn). The deployment is one long ARM operation, and the
  spoke's peering waits for it (`dependsOn`), because `useRemoteGateways` needs a gateway to exist.
- **Windows clients keep stale routes after a peering change.** Learn: the VPN client package must be downloaded and
  installed again after peering is created or changed, or topology changes. `vpnclient.sh` exists for that.
- **The P2S pool must not overlap anything** (Learn: private range that doesn't overlap the on-premises location or the VNet);
  minimum mask /29 for active/passive. `netplan.py` checks it against both.
- **No NSG on `GatewaySubnet`** (Learn: not supported, may stop the gateway). A test pins it; the NSG lives on the workload subnet.
- **P2S certificates: RSA only, no ECC** (Learn FAQ). The root needs to be a proper CA; the client certificate is signed by it
  and exported with the chain. The legacy PBE/MAC flags in `certs.sh` are this episode's choice for older Windows importers,
  not from Learn (not tested on old Windows).
- **Peering is directional.** Learn: configure both directions; allowGatewayTransit on the gateway side, useRemoteGateways on the
  other, allowForwardedTraffic on both; only one peering per VNet can use remote gateways, and not if the VNet has its own gateway.
- **Private subnets.** Learn: for API versions released after 31 Mar 2026, new VNets default to `defaultOutboundAccess=false`.
  We set it explicitly; the VM needs no internet because python3 ships in the image and cloud-init needs no download.
- **Azure Network Watcher diagnostics show which rule decides.** IP flow verify returns the access and the rule name; next hop
  returns the type (`None` for a destination nothing routes to, per Learn's tutorial). What exactly next hop returns for the P2S
  client range from the spoke VM is **not documented in what we read**: demo.md says to record whatever it returns.
- **Whether the VM sees the VPN client's pool address as the source** (the NSG rule relies on it) is the design assumption of
  this episode; `probe.py` prints the source address the service saw, and the demo reads it out. If Azure NATs it, the rule needs the
  address it really sees, and that is the finding to keep.

## References
- Blog: [Networking & VPN — Complete Guide](https://www.devladlog.com/articles/azure/2026-01-30-networking-vpn-complete-guide-2026/)
- [About gateway SKUs](https://learn.microsoft.com/azure/vpn-gateway/about-gateway-skus) (AZ SKUs, Standard public IP, P2S limits, Basic) and [SKU consolidation](https://learn.microsoft.com/azure/vpn-gateway/gateway-sku-consolidation)
- [Tutorial: create a VPN gateway](https://learn.microsoft.com/azure/vpn-gateway/tutorial-create-gateway-portal) (45 minutes or more) and [VPN Gateway settings](https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-about-vpn-gateway-settings) (GatewaySubnet name, /27)
- [P2S: certificates with OpenSSL](https://learn.microsoft.com/azure/vpn-gateway/point-to-site-certificates-linux-openssl), [P2S certificate gateway settings](https://learn.microsoft.com/azure/vpn-gateway/point-to-site-certificate-gateway) (address pool), [VPN Gateway FAQ](https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-vpn-faq) (RSA only), [SSTP retirement](https://learn.microsoft.com/azure/vpn-gateway/ikev2-openvpn-from-sstp)
- [Gateway transit for peering](https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-peering-gateway-transit), [P2S routing](https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-about-point-to-site-routing), [VNet peering requirements](https://learn.microsoft.com/azure/virtual-network/virtual-network-manage-peering#requirements-and-constraints), [gateway in a different region](https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-different-region)
- [IP address planning](https://learn.microsoft.com/azure/networking/design-guide/ip-planning) (5 reserved addresses) and [VNets and subnets](https://learn.microsoft.com/azure/networking/design-guide/vnets-subnets) (dedicated subnet sizes)
- [Default outbound access](https://learn.microsoft.com/azure/virtual-network/ip-services/default-outbound-access)
- [Network Watcher overview](https://learn.microsoft.com/azure/network-watcher/network-watcher-overview), [next hop](https://learn.microsoft.com/azure/network-watcher/next-hop-overview), [`az network watcher`](https://learn.microsoft.com/cli/azure/network/watcher), [`az network vnet-gateway vpn-client generate`](https://learn.microsoft.com/cli/azure/network/vnet-gateway/vpn-client)
- Prices: [Azure Retail Prices API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices) (EUR, West Europe, queried 21 Nov 2026)
