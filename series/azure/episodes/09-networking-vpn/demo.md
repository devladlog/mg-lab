# Demo shot list — DEVLADLOG Azure #9, Networking & VPN

## Lab environment

No Hyper-V VMs are needed. Screens are recorded on the **recording laptop** (Windows):
- a bash terminal (Git Bash or WSL) with the **Azure CLI** signed in as `labadmin` (`az login`), `python3`, `openssl`, `jq`, `unzip`, `curl`, `ssh-keygen`;
- **PowerShell** (for `Import-ClientCert.ps1`);
- the **Azure VPN Client** (Microsoft Store) for the certificate profile;
- a **browser on the lab tenant** (Azure portal, signed in as `labadmin`).

Before recording, check the laptop's own networks do not use `10.60.0.0/24`, `10.61.0.0/24` or `172.16.201.0/24` (`ipconfig`); the
Hyper-V lab uses `10.50.0.0/24` and the plan already avoids it.

Azure resources, all in resource group **`rg-mglab-azure-09`** (West Europe), tags `workload=contoso-orders`, `environment=lab`.
Prices: Azure Retail Prices API, EUR, list prices, West Europe, queried 21 Nov 2026 (check before recording).

| Resource | SKU / setting | Cost for the recording window (3 h) |
|---|---|---|
| Virtual network `vnet-hub` | `10.60.0.0/24`, only `GatewaySubnet` `10.60.0.0/27` | €0 |
| Virtual network `vnet-orders` | `10.61.0.0/24`, subnet `workload` `10.61.0.0/26`, NSG `nsg-workload`, private subnet | €0 |
| Public IP `pip-vpngw` | Standard, static, zones 1-3 | 3 x €0.0045 = €0.01 |
| VPN gateway `vgw-hub` | **VpnGw1AZ**, Generation1, route-based, P2S: IKEv2 + OpenVPN, certificate auth, pool `172.16.201.0/24` | **3 x €0.1885 = €0.57** (bills from creation, ~45 min before it is usable) |
| VM `vm-orders-int` | `Standard_B1s`, Ubuntu 24.04, 30 GB StandardSSD, **no public IP**, SSH key only | 3 x €0.0108 = €0.03 + cents for the disk |
| Peerings `hub-to-orders`, `orders-to-hub` | gateway transit | traffic-based, a few KB |
| **Total** | | **about €0.6-0.7** |

**Budget warning:** the gateway bills every hour it exists. Left running it is about €4.5 a day and about €138 a month against
the €30/month `mglab-monthly` budget. Run `infra/teardown.sh rg-mglab-azure-09` as soon as the last screen is captured and check
`az group exists --name rg-mglab-azure-09` returns `false`.

Permissions: Contributor on the subscription is enough (no role assignments). Licences: none. Network Watcher is enabled
automatically per region; if `diagnose.sh` complains, run `az network watcher configure -g NetworkWatcherRG -l westeurope --enabled true`.

**Tear-down:** `infra/teardown.sh rg-mglab-azure-09` (also deletes `~/.contoso-net`: keys, `.pfx`, client package). Then delete
the "contoso lab" profile in the Azure VPN Client and the client certificate from `Cert:\CurrentUser\My`
(`Get-ChildItem Cert:\CurrentUser\My | Where-Object Subject -like '*@contoso.example' | Remove-Item`).

## What the builder ran, and what is still unverified

Run in the builder's container (no Azure, no `az`): 31 pytest tests (plan checker, `bicep build` assertions, a real OpenSSL run of
`certs.sh`, the cloud-init service script executed and probed), `bicep lint`, `bash -n` on every script, PowerShell parse check.
**Never run against Azure** (marked *needs tenant*): every `az` call in `deploy.sh`, `vpnclient.sh`, `diagnose.sh`,
`teardown.sh`; the template deployment itself; cloud-init on the Ubuntu image; the VPN client connection; the `.pfx` import on
Windows. Expect small fixes on the first run (CLI flags, a capacity error for `Standard_B1s`, an image URN) and keep the
corrected files: the repo must contain what ran. The two **expected** results below are design assumptions, not Learn facts:
the source address the VM sees, and the next hop type towards the VPN client range. Record what actually comes back.

## Setup (needs tenant)

```bash
cd series/azure/episodes/09-networking-vpn
python3 -m pytest tests -q                                   # 31 passed, before anything else
az login                                                     # as labadmin
az account set --subscription "<lab subscription>"
infra/deploy.sh rg-mglab-azure-09 westeurope                 # ~50-60 min, almost all of it the gateway
infra/vpnclient.sh rg-mglab-azure-09                         # downloads the client package to ~/.contoso-net/client
```

`deploy.sh` prints the certificate password once: do not record that line (or re-run `infra/certs.sh` off camera). On Windows
import the client certificate: `pwsh infra/Import-ClientCert.ps1 -PfxPath $HOME/.contoso-net/certs/labadmin.pfx`.
In the Azure VPN Client: **Add** > **Import**, choose the `AzureVPN` folder's `azurevpnconfig_cert.xml` from the package (Learn
names that file for certificate auth; if the folder looks different, the gateway's tunnel type or auth type was changed after the
package was generated: run `vpnclient.sh` again), name it `contoso lab`, pick the client certificate, Save. If something
fails on first connect, fix it before recording and note the fix.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/netplan.jpg` — scene `plan_screen` (runs anywhere, no tenant)
Terminal in the episode folder: `python3 src/netplan/netplan.py check src/netplan/plan.json` then the same with
`plan-overlap.json`. Expect `OK: no overlaps; workload subnet 10.61.0.0/26 has 59 usable addresses; VM gets 10.61.0.4`, then three
`ERROR` lines (GatewaySubnet too small; hub overlaps lab-hyperv; client pool overlaps spoke). Nothing to mask.

### 2. `screens/deploy.jpg` — scene `deploy_screen` (needs tenant)
Terminal: start of `infra/deploy.sh` (plan OK, "certificates", what-if table with nine `Create` rows, "deploy (gateway: 45 minutes
or more)"). Add a caption with the real elapsed time and cut the wait in the edit (never fake it). Then the portal, resource group
`rg-mglab-azure-09` (nine resources plus the VM's disk), then **vgw-hub > Point-to-site configuration**: pool `172.16.201.0/24`,
tunnel type IKEv2 and OpenVPN, authentication Azure certificate, root certificate `contoso-p2s-root`.
Mask: subscription ID, the gateway's public IP and host name, tenant name in the portal header.

### 3. `screens/connect.jpg` — scene `connect_screen` (needs tenant)
Right terminal first, VPN **disconnected**: `python3 infra/probe.py 10.61.0.4 --expect closed --timeout 3` prints
`"reachable": false` with a timeout error and exits 0 (`echo $?`). Then connect in the Azure VPN Client (left window shows
**Connected**) and run `python3 infra/probe.py 10.61.0.4`: **expected** one JSON line with `"reachable": true`, `"status": 200`,
`"service": "contoso-orders-internal"`, `"host": "vm-orders-int"`, and `"client"` = an address in `172.16.201.0/24`. Read the
client address out and note it for screen 4. If `client` is something else, or the probe times out, that is the finding: check
the NSG rule's source prefix and whether the client package was installed after the peering existed (README gotcha).
Mask: gateway host name in the client window, certificate password.

### 4. `screens/diagnose.jpg` — scene `diagnose_screen` (needs tenant)
`infra/diagnose.sh rg-mglab-azure-09 <client address from screen 3>`. **Expected:** IP flow verify from the client address:
`Allow`, rule `securityRules/allow-orders-from-vpn-pool`; from `10.50.0.22`: `Deny`, rule `securityRules/deny-all-inbound`;
next hop to the client address: record what comes back (likely `VirtualNetworkGateway`, not verified); next hop to `10.50.0.22`:
`None` (the lab is not connected). The VM must be running. Mask: subscription ID.

## Tear-down (needs tenant, last thing on the day)
`infra/teardown.sh rg-mglab-azure-09`; `az group exists --name rg-mglab-azure-09` -> `false`; remove the VPN profile and the
client certificate on the laptop (commands above).
