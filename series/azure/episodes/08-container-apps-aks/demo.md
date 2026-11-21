# Demo shot list — DEVLADLOG Azure #8, Container Apps & AKS

## Lab environment

No VMs. Screens are recorded on the **recording laptop** (Windows): a bash terminal (Git Bash or WSL) with the **Azure CLI**
signed in as `labadmin` (`az login`), the **.NET 10 SDK**, `python3`, `curl`, and `kubectl` (`az aks install-cli`); and a
**browser on the lab tenant** (Azure portal, signed in as `labadmin`). No Docker is needed anywhere. The two terminals in
screens 2 and 3 are two bash windows side by side.

Azure resources, all in resource group **`rg-mglab-azure-08`** (West Europe), tags `workload=contoso-orders`,
`environment=lab`. Prices: Azure Retail Prices API, EUR, list prices, West Europe, queried 21 Nov 2026 (check before recording).

| Resource | SKU / setting | Cost for the recording window |
|---|---|---|
| Log Analytics workspace `log-orders-xxxx` | PerGB2018, 30 days, **daily cap 1 GB** | **€0** (first 5 GB a month free; a few MB of logs) |
| Container Registry `acrordersxxxx` | **Basic**, admin user disabled | **€0.15** (€0.1496 per day, billed per registry-day) |
| User-assigned identity `id-orders-pull` + role assignments | AcrPull (identity), AcrPush (labadmin) | €0 |
| Container Apps environment `cae-orders-xxxx` | workload profiles, **Consumption profile only** (no Dedicated profile, so no plan-management fee) | €0 |
| Container app `ca-orders-api` | 0.25 vCPU / 0.5 GiB per replica, 0–3 replicas, external ingress, Multiple revisions | **€0** inside the monthly free grants (180,000 vCPU-s, 360,000 GiB-s, 2 M requests per subscription): the recording uses a few hundred vCPU-seconds. Zero replicas = no usage charge |
| AKS cluster `aks-orders-lab` | **Free tier** (Base SKU), Azure Linux, Azure CNI overlay, **1 x `Standard_D4as_v5`** system node (4 vCPU / 16 GiB), 64 GB managed OS disk | control plane €0; node €0.1867/h; disk €0.0138/h; Standard LB €0.0224/h; 2 public IPs 2 x €0.0045/h → **≈ €0.232 per hour** |
| ↳ node resource group `MC_rg-mglab-azure-08_aks-orders-lab_westeurope` | created and deleted by AKS | included above |
| **Total** | AKS up for ≤ 2 hours | **≈ €0.61** (0.46 AKS + 0.15 registry) |

**Budget warning:** the AKS node bills by the hour whether pods run or not. Left running for a day it is ≈ €5.6; for a month
≈ €170, against the €30/month `mglab-monthly` budget. Create it only for screen 4 and run
`infra/teardown.sh rg-mglab-azure-08 --aks-only` straight after, then check `az aks list -g rg-mglab-azure-08 -o table` is empty.

Permissions: **Owner** on the subscription (the templates create role assignments). Licences: none beyond the subscription.
Quota: **4 free vCPUs of the "Standard DASv5 Family" in West Europe** (`deploy-aks.sh` checks and stops early). Resource
providers `Microsoft.App`, `Microsoft.ContainerRegistry`, `Microsoft.OperationalInsights`, `Microsoft.ManagedIdentity` and
`Microsoft.ContainerService` are registered by the scripts (a fresh subscription may take a few minutes).

**Tear-down:** `infra/teardown.sh rg-mglab-azure-08`, then `az group exists --name rg-mglab-azure-08` → `false`.

## What the builder ran, and what is still unverified

Run in the builder's container (no Azure): `dotnet test` (9 passed), `pytest tests/infra` (29 passed, including a real image
build), `bicep lint`/`build-params` for both templates, `bash -n` on every script, the published app on localhost (probes,
SIGTERM drain, quote). **Never run against Azure** (marked *needs tenant*): every script in `infra/`, the managed-identity
pull, scale-out/in timings, the traffic split, the AKS deployment, `kubectl apply --dry-run=server`. Expect to fix small
things on the first run (CLI flag changes, extension versions) and keep the corrected scripts: the repo must contain what ran.

## Setup (needs tenant)

```bash
cd series/azure/episodes/08-container-apps-aks
dotnet test tests/Contoso.Orders.Api.Tests -m:1 && python3 -m pytest tests/infra -q    # 9 + 29 passed, before anything else
az login                                                                                # as labadmin
az account set --subscription "<lab subscription>"
infra/deploy-aca.sh rg-mglab-azure-08 westeurope     # ~6-8 min: providers, registry, push 1.0.0, what-if, app, first answer
```

The script prints the app URL and stores it in `~/.contoso-orders-containers/url`; `URL=$(cat ~/.contoso-orders-containers/url)`.
If the first `GET /` takes a few seconds, that is the cold start from zero replicas; the script retries for 5 minutes.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/deploy-aca.jpg` — scene `deploy_screen` (needs tenant)
Terminal, the end of `infra/deploy-aca.sh`: "== push 1.0.0" with the tag table (`1.0.0`), the what-if summary for the container
app, then the JSON of `GET /`: `"platform":"container-apps"`, `"revision":"ca-orders-api--v1-0-0"`, `"version":"1.0.0"`.
Mask: subscription ID, registry and app host names (scroll or blur).

### 2. `screens/scale-out.jpg` — scene `scale_screen` (needs tenant)
Left terminal: `infra/load.py "$URL" 24 90` (prints `{"total": ..., "per_second": ..., "status": {"200": ...}}`). Right terminal, started
first: `infra/replicas.sh rg-mglab-azure-08 12` (a line every 30 s). Capture the sequence `0` (or `1`) → `3` under load → back to
`0` about 5 minutes after the load ended (so the right terminal must keep running: ~12 minutes in total; cut the wait in
the edit, never fake it). If it only reaches 2, raise `per_second` (more workers: `load.py "$URL" 48 90`) rather than
changing the rule; say the number that was reached. Optional second shot: portal → container app → **Revisions and
replicas** → the replica list. Mask: app host name. Check `status` shows only `200`; anything else is a finding to keep.

### 3. `screens/revisions-split.jpg` — scene `revisions_screen` (needs tenant)
`infra/release-v2.sh rg-mglab-azure-08 20`: the pin step, `v1-1-0` reaching `Provisioned`, the traffic table (80 / 20) and the
revision list. Then `infra/split.sh "$URL" 100`: about `1.0.0  80` and `1.1.0  20` (random: don't expect exactly 80/20; show what
came out). Optional: portal → Revisions and replicas with both revisions active and their weights. Mask: app host name.
Also run `curl -si "$URL/" | grep -i x-app-version` once to show the header.

### 4. `screens/aks-pods.jpg` — scene `aks_screen` (needs tenant; **the AKS clock starts here**)
`infra/deploy-aks.sh rg-mglab-azure-08` (~8–12 min; start the screen capture after "AKS cluster" returns): the quota line,
`kubectl apply --dry-run=server`, `deployment "orders-api" successfully rolled out`, `kubectl get nodes,pods,svc,hpa -o wide`
(1 node, 2 pods `Running`, `orders-api` with an `EXTERNAL-IP`, HPA `cpu: …/70%` 2/5) and `GET /` with
`"platform":"kubernetes"`, `"replica":"orders-api-…"`. Optional second shot: portal → AKS cluster → **Node pools** (1 node,
Standard_D4as_v5) and **Overview** showing **Free** tier. **Immediately afterwards:**
`infra/teardown.sh rg-mglab-azure-08 --aks-only`, then confirm with `az aks list -g rg-mglab-azure-08 -o table` after a few
minutes. Mask: external IP, registry name, node names if they contain the group name.

### 5. Extras for the narration (no separate screen scene)
- Portal → Container Registry → **Access keys**: admin user **Disabled**; Container app → **Containers** or **Identity**: the user-assigned identity. Good B-roll for the `aca_bicep` scene.
- Portal → **Cost analysis** filtered on the resource group, the next day, if you want a real number next to the estimate.

## If something differs from the script
Say what happened. The script claims only what Learn documents (grants, 300 s cool-down, 30 s SIGTERM, HTTP rule math,
AKS node-pool rules) and what ran locally; if the lab shows 2 replicas instead of 3, or a different cool-down, change the
narration, not the footage.

## Tear-down (needs tenant)
```bash
infra/teardown.sh rg-mglab-azure-08 --aks-only    # right after screen 4, if not already done
infra/teardown.sh rg-mglab-azure-08               # everything else (registry, environment, app, workspace)
az group exists --name rg-mglab-azure-08          # false after a few minutes (the MC_ group goes with the cluster)
```
