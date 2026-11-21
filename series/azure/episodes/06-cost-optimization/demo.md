# Demo shot list — DEVLADLOG Azure #6, Cost Optimization

Everything below **needs the lab subscription** (marked *needs tenant*) except the local checks. The episode builder
ran the local checks (51 pytest tests, Bicep lint/build) and `costwatch estimate` against the **live, public** Retail
Prices API with the what-if fixtures. Nothing was deployed to Azure and no Azure sign-in was used.

## Lab environment

No VMs. Screens are recorded in a **browser on the lab tenant** (Azure portal) and a **terminal on the recording
laptop** (Azure CLI signed in, with the `resource-graph` extension, which `deploy-waste-demo.sh` installs; Python 3).

**Schedule:** record the *Cost analysis* screen **at least one day after** episodes 1–5 were recorded (cost data is
typically 8–24 hours late, and tags only count from when they were applied). Their resources can already be torn
down: the costs stay in the history.

Azure resources (prices: Azure Retail Prices API, EUR, list prices, queried 21 Nov 2026; check before recording):

| Resource | Where | SKU / setting | Estimated cost for a 2-hour recording window |
|---|---|---|---|
| Empty resource group `rg-contoso-whatif` | Sweden Central | only used as the what-if target; nothing is deployed | **€0** (what-if is free) |
| Budget `budget-contoso-lab` | subscription scope | €10/month, filter `workload` in (`order-intake`, `contoso`, `contoso-orders`), 3 e-mail alerts | **€0** (budgets are free) |
| Resource group `rg-contoso-waste` | Sweden Central | tag `workload=contoso-waste` | — |
| ↳ Public IP `pip-contoso-forgotten` | | Standard, static IPv4, **no tags** | €0.0045/h → **€0.01** |
| ↳ App Service plan `plan-contoso-leftover` | | **B1** Linux, 1 instance, no apps | €0.0162/h → **€0.03** |
| ↳ Disk `disk-orphaned-os` | | Standard_LRS, from the Ubuntu 24.04 image (30 GiB → billed as S4) | €1.38/month → **< €0.01** |
| ↳ Disk `disk-empty-never-used` | | Standard_LRS, empty, 32 GiB, never attached | **€0** (Learn: no storage allocated until first use) |
| **Total** | | | **≈ €0.05** if torn down the same day |

Licences/permissions: the Azure subscription with the €10 budget alert. On the subscription: **Reader** (Resource
Graph, Advisor), **Cost Management Reader** (cost analysis) and **Cost Management Contributor** or Contributor (to
create the budget); **Contributor** on the two resource groups. Owner covers all of it.

**Tear-down:** `infra/teardown.sh rg-contoso-waste rg-contoso-whatif` (add `--with-budget` only if the lab doesn't
want to keep the budget; it costs nothing). Check `az group exists` for both groups → `false`.

## Setup (needs tenant)

```bash
cd series/azure/episodes/06-cost-optimization
python3 -m pytest tests -q                                    # 51 passed, before anything else
az login
BUDGET_EMAIL=<recorder's mailbox> infra/deploy-budget.sh      # what-if, then create (subscription scope)
infra/deploy-waste-demo.sh rg-contoso-waste swedencentral     # ~3 min; lists 4 resources at the end
```

If `az disk create --image-reference Canonical:ubuntu-24_04-lts:server:latest` is refused in the region, list the
image with `az vm image list --publisher Canonical --offer ubuntu-24_04-lts --sku server --all -o table` and use a
listed URN; any Marketplace image works (the point is a disk that holds data).

Resource Graph indexes new resources within minutes; wait ~5 minutes after the waste demo before the waste screen.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/estimate-ep2.jpg` — scene `whatif_screen` (needs tenant)
`infra/estimate-ep2.sh rg-contoso-whatif swedencentral 25`. Capture the end of the lab block (table, **within**,
≈ 24.90 EUR) and the prod block (≈ 246.40 EUR, **OVER**, the `##vso[task.logissue …]` line) and the final exit code
(`echo $?` → 1). The prices are live, so small differences from 24.90 / 246.40 are expected; say what you got.
**Also hand the two real what-if files to the episode builder** (`~/.contoso-cost/whatif-lab.json` and
`whatif-prod.json`; check them for identifiers first): they replace the hand-written fixtures. Check that each `Create` has `after.sku` for the plan (the estimator needs it).

### 2. `screens/cost-analysis.jpg` — scene `costanalysis` (needs tenant)
Portal → **Cost Management** → **Cost analysis**, scope = the lab subscription, current month (or last month if
episodes 1–5 were recorded then), view *Accumulated costs* or *Daily costs*, **Group by → Tag → workload**. Must show
segments for `order-intake`, `contoso`, `contoso-orders` (whichever have accrued cost) and *Untagged*.

### 3. `screens/budget.jpg` — scene `budget_screen` (needs tenant)
Cost Management → **Budgets** → `budget-contoso-lab`. Must show: amount 10, reset period monthly, the filter on tag
`workload`, the three alert conditions (Actual 50 %, Actual 90 %, Forecasted 100 %) and the current spend. Right
after creation the evaluated cost can be empty (Learn: the first evaluation may not have happened yet); that's fine,
or record it the next day.

### 4. `screens/waste.jpg` — scene `waste_screen` (needs tenant)
1. Portal → **Resource Graph Explorer** → paste `queries/unattached-disks.kql` → Run. Must show the two disks with
   `createOption` `FromImage` and `Empty`.
2. Terminal: `PYTHONPATH=src python3 -m costwatch waste --subscriptions <subscription-id>`. Must show the priced table
   (plan ≈ 11.80, IP ≈ 3.28, orphaned disk ≈ 1.38, empty disk 0.00, total), the untagged table with the public IP,
   and the Advisor section (likely "(none)" on a new subscription; that's honest, keep it).
3. *Check while you're there:* if the `lastOwnershipUpdate` column of the empty disk isn't empty, or the
   `createOption` column is missing, tell the episode builder (the 0.00 rule depends on both).

## Masking
- Subscription ID and name, tenant name/domain, the account in the portal header.
- **Budget e-mail address** (budget blade, `BUDGET_EMAIL=` line in the terminal).
- The public IP address of `pip-contoso-forgotten` (Resource Graph, terminal).
- Use `pipeline/mask.js` in the browser; `series_label: "AZURE"` is set in script.yaml.

## Tear-down (needs tenant)
```bash
infra/teardown.sh rg-contoso-waste rg-contoso-whatif          # budget stays (free) unless --with-budget
az group exists --name rg-contoso-waste && az group exists --name rg-contoso-whatif   # false, false
```
