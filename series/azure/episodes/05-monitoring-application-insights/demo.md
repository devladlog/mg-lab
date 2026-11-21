# Demo shot list — DEVLADLOG Azure #5, Monitoring & Application Insights

Everything below **needs the lab subscription** (marked *needs tenant*) except the local checks. The episode builder
ran only the local checks (43 xUnit tests, Bicep lint/build, the API with the console exporter, `load.sh` against it).
Nothing was deployed to Azure.

## Lab environment

No VMs. Screens are recorded in a **browser on the lab tenant** (Azure portal) and a **terminal on the recording
laptop** (Azure CLI signed in, .NET SDK 10, `zip`, `curl`, `python3`).

Azure resources (one resource group, `rg-contoso-monitoring`, region **Sweden Central**), all created by
`infra/deploy.sh`. Prices: Azure Retail Prices API, EUR, Sweden Central, pay-as-you-go list prices, queried
21 Nov 2026; check again before recording.

| Resource | SKU / setting | Why this size | Estimated cost, 3-hour recording window |
|---|---|---|---|
| App Service plan (Linux) | **B1**, 1 instance | Smallest tier with Always On, so the availability test and alerts don't see cold starts (F1 has no Always On) | €0.0162/h → **≈ €0.05** |
| Web app | .NET 10 (`DOTNETCORE\|10.0`), user-assigned identity, Health check `/healthz` | — | included in the plan |
| Storage account | StorageV2 **Standard_LRS**, shared keys off, container `orders` | A few hundred small JSON blobs | **< €0.01** |
| User-assigned managed identity | 2 role assignments (Storage Blob Data Contributor, Monitoring Metrics Publisher) | — | free |
| Log Analytics workspace | **PerGB2018**, 30-day retention, **daily cap 1 GB** | The demo ingests a few MB | **€0** within the 5 GB per billing account per month that is free; beyond it €2.68/GB |
| Application Insights | workspace-based, `DisableLocalAuth: true` | billing is done by the workspace | included above |
| Standard availability test | 5 locations × every 5 min = 60 executions/h | Learn recommends at least 5 locations | €0.0006 per execution → **≈ €0.11** |
| Action group | 1 e-mail receiver (address passed at deploy time) | — | a handful of e-mails; see [Azure Monitor pricing](https://azure.microsoft.com/pricing/details/monitor/) |
| 2 metric alert rules | 1-minute frequency | — | €0.27 per monitored time series per month → **< €0.01** prorated |
| 1 log search alert rule | 5-minute frequency, scope = workspace | — | billed per month per time series, prorated **< €0.01** |
| **Total** | | | **well under €0.25** if torn down the same day |

Licences/permissions: an Azure subscription with the €10 budget alert; on the resource group **Owner**, or Contributor
+ User Access Administrator (the template creates role assignments). No Microsoft 365 licence is needed.

**Tear-down:** `infra/teardown.sh rg-contoso-monitoring` deletes the group, which contains everything above
(web test, alert rules and action group included). Check with `az group exists --name rg-contoso-monitoring` → `false`.

## Setup (needs tenant)

```bash
cd series/azure/episodes/05-monitoring-application-insights
dotnet test tests/Contoso.Orders.Api.Tests                       # 43 passed, before anything else
az login
ALERT_EMAIL=<recorder's mailbox> infra/deploy.sh rg-contoso-monitoring swedencentral   # ~8 min
URL=$(python3 -c 'import json;print(json.load(open("'$HOME'/.contoso-orders-monitoring/outputs.json"))["appUrl"]["value"])')
infra/load.sh "$URL" 100                                          # ~2 min of mixed traffic
```

1. Wait **3–5 minutes** for telemetry to arrive (ingestion isn't instant).
2. Open the Log Analytics workspace → Logs and run `queries/slow-operations.kql`. You should see `POST /orders` and
   `GET /orders/{orderId}`.
3. **Check the role name before trusting the log alert:** `AppRequests | take 5 | project AppRoleName`. It must be
   `contoso-orders-api` (the alert query filters on it). If it isn't, stop and tell the episode builder; don't edit
   the query on camera.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/transaction.jpg` — scene `transaction` (needs tenant)
Application Insights → **Transaction search** → filter *Request*, pick a `POST /orders` with result 201 → end-to-end
transaction details. Must show: the request, the child **orders.price** (with `order.channel`, `order.line_count`,
`order.total` in the properties pane) and the **Azure blob** dependency (upload to the `orders` container).
Rate-limited sampling keeps whole traces, so any 201 you can open is complete.

### 2. `screens/orders-by-channel.jpg` — scene `logs` (needs tenant)
Log Analytics workspace → Logs → paste `queries/orders-by-channel.kql` → Run. Must show a timechart with two series,
`web` and `partner`. Optional second capture: `queries/sampling-check.kql` (at 100 rounds the API stays under
5 traces/s most of the time, so expect values at or near 100; say what you captured).

### 3. `screens/alert-fired.jpg` — scene `alert` (needs tenant)
1. `infra/chaos.sh rg-contoso-monitoring 30` (the app restarts; wait until `curl $URL/healthz` answers).
2. `infra/load.sh "$URL" 100` → the tally shows `HTTP 500` lines next to 201/400/404/422.
3. Within ~5–10 minutes: Azure Monitor → **Alerts** shows **alert-orders-failed-requests** (Sev 2) and
   **alert-orders-failure-ratio** with dimension `OperationName = POST /orders`. Capture terminal (left) + Alerts
   blade (right). Optional: the alert e-mail.
4. `infra/chaos.sh rg-contoso-monitoring 0`, then run `load.sh` once more so the alerts resolve (`autoMitigate`).
Also useful for the narration: `queries/order-journey.kql` with the operation id of one 500 (the `traceId` in the
response body, the 32 hex characters after `00-`) shows request + exception log together.

### 4. `screens/availability.jpg` — scene `availability` (needs tenant)
Application Insights → **Availability**. Toggle **Scatter plot**. Must show `orders-api-healthz` with results from the
five European locations (West Europe, North Europe, France Central, UK South, UK West), all green. Hover one dot so
the location and duration are visible.

## Masking
- Subscription ID, tenant name/domain, the account in the portal header.
- Resource names with the random suffix (`app-orders-xxxx`, `appi-…`, `log-…`, `storders…`) and the
  `*.azurewebsites.net` host in the terminal, the web test and the transaction view.
- **The alert e-mail address** (action group blade, the e-mail itself, the `ALERT_EMAIL=` line in the terminal).
- The connection string never appears on screen (don't open the web app's Environment variables blade).
- Use `pipeline/mask.js` in the browser; `series_label: "AZURE"` is set in script.yaml.

## Tear-down (needs tenant)
```bash
infra/chaos.sh rg-contoso-monitoring 0     # if you stop before the end
infra/teardown.sh rg-contoso-monitoring
az group exists --name rg-contoso-monitoring   # false when done
```
