# Demo shot list — DEVLADLOG Azure #2, Cloud Architecture you can test

Everything below **needs the lab subscription** (marked *needs tenant*) except the local checks. The episode builder
ran the local checks only (pytest, xUnit, PSRule, Bicep lint/build); nothing was deployed to Azure.

## Prerequisites

| What | Notes |
|---|---|
| Azure subscription with the €10 budget alert | On the resource group: **Owner**, or Contributor + **Resource Policy Contributor** (policy assignments) + **User Access Administrator** (role assignments) |
| Region | `swedencentral` by default (any region with App Service Linux and private endpoints). A second region name for the policy test, e.g. `westeurope` |
| Azure CLI ≥ 2.53 | Needed for `.bicepparam` deployments; signed in with `az login` on the recording machine |
| .NET SDK 10, `zip`, `curl`, `nslookup` | Publish the probe, call `/healthz` |
| PowerShell 7 + PSRule.Rules.Azure | Only to re-show the local guardrail run (`Save-Module` to a temp folder, see README) |
| Cost (lab profile) | B1 App Service plan, 2 private endpoints, 2 private DNS zones, Standard_LRS storage, Key Vault standard, Log Analytics. Well under €1 for a ~1 hour recording if torn down the same day; check the pricing pages before recording. **Do not deploy the prod profile** (P1v3 × 2) for the demo |

## Setup (needs tenant)

```bash
cd series/azure/episodes/02-cloud-architecture
python3 -m pytest tests/guardrails -q                    # 15 passed, before anything else
dotnet test tests/ReadinessProbe.Tests                   # 7 passed
infra/deploy.sh rg-contoso-arch swedencentral lab        # ~10 min: governance, what-if, workload, probe
```

So that the "refused from outside" shot proves the **network** block and not missing permissions, give your own user
the same data roles the app has, on the two resources (after the workload deployment):

```bash
ME=$(az ad signed-in-user show --query id -o tsv)
ST_ID=$(az storage account list -g rg-contoso-arch --query "[0].id" -o tsv)
KV_ID=$(az keyvault list -g rg-contoso-arch --query "[0].id" -o tsv)
az role assignment create --assignee-object-id $ME --assignee-principal-type User --role "Storage Blob Data Reader" --scope $ST_ID
az role assignment create --assignee-object-id $ME --assignee-principal-type User --role "Key Vault Secrets User" --scope $KV_ID
```

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/policy-deny.jpg` — scene `policy` (needs tenant)
Wait at least **five minutes** after the governance step (Learn: a new assignment takes about five minutes to apply).
Then `infra/try-policy.sh rg-contoso-arch westeurope`. Capture both blocks:
- block 1 (tagged NSG in `westeurope`): `RequestDisallowedByPolicy`, assignment **Workload resources only in approved
  regions**, message "Deploy only to the approved regions for this workload."
- block 2 (untagged NSG in the allowed region): `RequestDisallowedByPolicy`, assignment **Every resource carries a
  workload tag**, message "Add the workload tag (cost and ownership reporting)."

If a request succeeds, the assignment isn't active yet: wait a few minutes, delete the NSG it created, and retry.

### 2. `screens/what-if.jpg` — scene `whatif` (needs tenant)
Easiest on a fresh group (`infra/deploy.sh rg-contoso-arch2 ...` and stop after step 2), or rerun only:
`az deployment group what-if -g rg-contoso-arch --parameters infra/env/lab.bicepparam`. On an already deployed group
the output is mostly "NoChange"/"Ignore", which is also a valid shot ("nothing drifted"); say which one you captured.
Mask the subscription ID in the scope lines.

### 3. `screens/private-proof.jpg` — scene `private` (needs tenant)
`infra/prove-private.sh rg-contoso-arch`. Must show:
1. `nslookup <account>.blob.core.windows.net`: the CNAME to `<account>.privatelink.blob.core.windows.net`
2. `az storage container show ... --auth-mode login`: an error (public network access is disabled)
3. `az keyvault secret show ...`: an error (public network access disabled / forbidden by firewall)
4. `curl https://<app>/healthz`: `{"status":"Healthy","checks":[{"name":"storage","status":"Healthy",...},{"name":"keyvault",...}]}`

If `/healthz` shows `Unhealthy` right after deployment, wait a few minutes (role assignments and the VNet
integration can take a moment) and retry; note it in the episode if it happens, it's a real thing.

### 4. `screens/resource-visualizer.jpg` — scene `visualizer` (needs tenant)
Portal → resource group → **Resource visualizer**. Arrange so the app, plan, VNet, both private endpoints, storage,
key vault, DNS zones and the workspace are visible. Optional extra capture: the web app's **Health check** blade
showing the `/healthz` path and status.

## Masking
- Subscription ID, tenant name/domain, your account in the portal header and in CLI errors (`az` prints the
  signed-in principal in some authorization errors).
- The unique suffixes in resource names (`stcontosolab…`, `kv-contoso-lab-…`, `app-contoso-lab-…`) and the
  `*.azurewebsites.net` host.
- Never show the secret value: the probe only reports the secret **name**; don't run `az keyvault secret show` with
  `--query value` on camera.
- Use `pipeline/mask.js` in the browser; `series_label: "AZURE"` is set in script.yaml.

## Tear-down (needs tenant)
```bash
infra/teardown.sh rg-contoso-arch       # deletes the group (policy assignments included) and purges the lab vault
az group exists --name rg-contoso-arch  # false
```
If you created `rg-contoso-arch2` for the what-if shot, delete it too. Remove the two role assignments you gave
yourself if they were created at a broader scope than the resources (they're deleted with the resources otherwise).
