# Demo shot list — DEVLADLOG Azure #1, Azure Functions & Serverless

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / tenant apps | none |
| Lab user | `labadmin` (the recording account): Owner on the subscription; runs `az login` and `infra/deploy.sh`; gets Storage Blob/Queue Data Reader on the storage account for the browse shot |
| Azure | Resource group **`rg-mglab-azure-01`** in **West Europe** (if `az functionapp list-flexconsumption-locations` doesn't list it, use `swedencentral`), deployed by `infra/deploy.sh`: Function App on **Flex Consumption** (on demand, no always-ready instances: per execution and GB-s, cents), Storage account Standard_LRS, Application Insights + Log Analytics workspace (cents for ~1 hour). Estimated total: well under €1. Tear-down: `infra/teardown.sh rg-mglab-azure-01` |
| Local scene | The `local` screen runs the real Functions host (Core Tools `func start`) with **Azurite**, Microsoft's local Storage emulator, on the laptop. That is the topic of the scene (the local dev loop), not a stand-in for the cloud screens, which all show the deployed app |
| Licences / trials | none beyond the subscription |
| Recording machine | The Windows lab laptop: Azure portal in the browser, bash terminal in WSL (Ubuntu) with the tools listed under Prerequisites (the scripts are bash) |

Everything below **needs the lab machine and the lab subscription** (marked *needs tenant*). Nothing here was run in
Azure by the episode builder; the code, tests, Bicep and scripts were validated locally (see README).

## Prerequisites

| What | Notes |
|---|---|
| Azure subscription with the €10 budget alert | Contributor + **User Access Administrator** (or Owner) on the resource group: the Bicep creates role assignments |
| Region with Flex Consumption | `az functionapp list-flexconsumption-locations -o table`; the lab uses `westeurope` if listed (the scripts default to `swedencentral`) |
| Azure CLI | Signed in as `labadmin` with `az login` on the recording machine (not in the builder container) |
| .NET SDK 10, `zip`, `curl` | For `dotnet publish` and the smoke test |
| Azure Functions Core Tools v4 + Azurite | Only for the local scene (`npm i -g azurite` or `npx azurite`) |
| Cost | Flex Consumption on demand bills per execution and GB-s, with no always-ready instances configured; Standard_LRS storage and a Log Analytics workspace for ~1 hour. Expect cents. Check the [pricing page](https://azure.microsoft.com/pricing/details/functions/) and tear down the same day |

## Setup (needs tenant)

```bash
cd series/azure/episodes/01-azure-functions-serverless
dotnet test tests/OrderIntake.Tests          # 33 passed, before anything else
infra/deploy.sh rg-mglab-azure-01 westeurope # what-if, deploy, publish, zip deploy (~5 min)
RG=rg-mglab-azure-01
APP=$(az functionapp list -g $RG --query "[0].name" -o tsv)
HOST=$(az functionapp show -g $RG -n $APP --query defaultHostName -o tsv)
KEY=$(az functionapp function keys list -g $RG -n $APP --function-name SubmitOrder --query default -o tsv)
```

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/local-run.jpg` — scene `local`
1. Terminal A: `npx azurite --silent --location /tmp/azurite`
2. Terminal B: `cd src/OrderIntake && cp local.settings.sample.json local.settings.json && func start`
   Wait for the function list: `SubmitOrder: [POST] http://localhost:7071/api/orders`, `ProcessOrder: queueTrigger`,
   `OrderPoison: queueTrigger`.
3. Terminal C: `infra/smoke.sh http://localhost:7071`
4. Capture B (function list + "Order ... accepted" / "Pricing order ... attempt 1" log lines) and C (202 with orderId,
   400 with the `errors` array) side by side.
5. **Check while you're there:** after the 400, the `orders` queue gets no new message (Azure Storage Explorer or
   `az storage message peek --queue-name orders --connection-string UseDevelopmentStorage=true`).

### 2. `screens/flex-overview.jpg` — scene `deployed` (needs tenant)
Portal → Function App → **Overview**. Must show: plan type **Flex Consumption**, runtime **.NET 10 Isolated**, the
three functions in the Functions tab. Optional second capture: **Settings → Scale and concurrency** (max 40
instances, 2048 MB).

### 3. `screens/blob-output.jpg` — scene `blob` (needs tenant)
1. `infra/smoke.sh "https://$HOST" "$KEY"` → capture the first block (HTTP 202, `orderId`).
2. Portal → storage account → **Storage browser** → Blob containers → `orders-processed` → open `<orderId>.json`.
   Must show subtotal **538.98**, discount **26.95**, total **512.03**. *Confirms that `{OrderId}` resolved from the
   JSON message (the gotcha).* Shared-key access is disabled on this account, so browse with Microsoft Entra ID:
   give your own user **Storage Blob Data Reader** and **Storage Queue Data Reader** on the account first.

### 4. `screens/poison.jpg` — scene `poison` (needs tenant)
The third smoke order (`ZZZ-999`) is accepted (202), then fails 5 times. With `visibilityTimeout` 5 s it lands in
`orders-poison` in under a minute. Application Insights → **Logs**:

```kusto
traces
| where timestamp > ago(30m)
| where message has "Pricing order" or message has "needs a human"
| project timestamp, severityLevel, message
| order by timestamp asc
```

Capture: five `Pricing order <id>, attempt 1..5` lines, then the severity-3 line from `OrderPoison`. Telemetry can lag
a few minutes; wait for it. Optional: Storage browser → Queues → `orders-poison` (it will be empty again once
`OrderPoison` has processed it, so the log is the reliable shot).

## Masking
- Subscription ID, tenant name/domain, your account in the portal header.
- The random suffix in resource names (`func-orders-xxxx`, `storders...`) and the `*.azurewebsites.net` host.
- **The function key** in the terminal (`x-functions-key`): never on screen; blur the `KEY=` line and the smoke
  command arguments.
- Use `pipeline/mask.js` in the browser; `series_label: "AZURE"` is set in script.yaml.

## Tear-down (needs tenant)
```bash
infra/teardown.sh rg-mglab-azure-01
az group exists --name rg-mglab-azure-01        # false when done
```
Stop Azurite and `func` locally, and delete `src/OrderIntake/local.settings.json`.
