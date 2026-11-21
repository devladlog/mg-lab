# DEVLADLOG Azure #5 — Monitoring & Application Insights: alerts that survive sampling

Episode 4 protected the contoso **orders API**; this episode finds out what it is actually doing in production.
The same API (catalogue and order shape from episode 1, Entra auth left out so the load script can call it) gets:

- **OpenTelemetry with the Microsoft OpenTelemetry Distro** (`Microsoft.OpenTelemetry` 1.2.0, the package Microsoft
  Learn now recommends for new .NET apps): ASP.NET Core, HttpClient and Azure SDK instrumentation, plus our own
  `orders.price` span, two counters and a histogram
- **Entra ID-only ingestion**: `DisableLocalAuth: true` on Application Insights; the app sends with its
  user-assigned managed identity (role *Monitoring Metrics Publisher*)
- **Explicit sampling**: the distro samples at 5 traces per second by default; the setting is in config and
  validated at startup. Metrics are never sampled, so alerts use metrics, and every query counts with `sum(ItemCount)`
- **A 400 is not an outage**: a span processor marks 400/404/422 as successful requests (the exporter treats any 4xx
  as failed when the span status is unset); 401/403/409/429 and 5xx still fail
- **Three alerts in Bicep**: availability (standard test, 5 locations, alert at 3), failed requests (standard metric),
  failure **ratio** per operation (log search alert whose KQL is a file in `queries/` that the tests check)
- **Tested telemetry and KQL**: 43 xUnit tests read the real spans/metrics/logs with an in-memory exporter, parse
  every `.kql` file against the workspace schema with `Kusto.Language`, and check the compiled Bicep
- **Fault injection for the demo**: app setting `Chaos__FailurePercent` makes a share of saves throw (HTTP 500)

```
 load.sh ──► App Service (B1, .NET 10) ──► blob "orders" (managed identity, keys off)
             │ OpenTelemetry: requests, orders.price span, blob dependency, logs, contoso.orders.* metrics
             ▼ Entra token (Monitoring Metrics Publisher)
             Application Insights (workspace-based, local auth off) ──► Log Analytics (PerGB2018, 1 GB/day cap)
             ▲ standard test /healthz, 5 locations             │
             └──────── alerts ──► action group (e-mail) ◄──────┘ availability · requests/failed · failure ratio (KQL)
```

| Path | What it is |
|---|---|
| [`src/Contoso.Orders.Api/Telemetry/TelemetrySetup.cs`](src/Contoso.Orders.Api/Telemetry/TelemetrySetup.cs) | `UseMicrosoftOpenTelemetry`: Azure Monitor + Entra credential in Azure, console exporter locally; sampling settings and validation; managed identity / Azure CLI credential |
| [`src/Contoso.Orders.Api/Telemetry/OrdersTelemetry.cs`](src/Contoso.Orders.Api/Telemetry/OrdersTelemetry.cs) | `ActivitySource` + `Meter` (`IMeterFactory`): `contoso.orders.created`, `contoso.orders.rejected`, `contoso.orders.value` |
| [`src/Contoso.Orders.Api/Telemetry/ExpectedClientErrorProcessor.cs`](src/Contoso.Orders.Api/Telemetry/ExpectedClientErrorProcessor.cs) | 400/404/422 server spans → status Ok (pattern from Learn) |
| [`src/Contoso.Orders.Api/Orders/OrderEndpoints.cs`](src/Contoso.Orders.Api/Orders/OrderEndpoints.cs) | `POST /orders` (201/400/422), `GET /orders/{id}` (200/404), custom span, structured logs without the customer id |
| [`src/Contoso.Orders.Api/Orders/OrderStores.cs`](src/Contoso.Orders.Api/Orders/OrderStores.cs) | Blob store (managed identity), in-memory store, `ChaosOrderStore` fault injection |
| [`queries/*.kql`](queries) | Alert query (failure ratio), slow operations (p50/p95/p99), one order end to end, orders per channel, sampling check, billable GB per table |
| [`infra/main.bicep`](infra/main.bicep) | Workspace (cap), App Insights (Entra-only), storage, identity + 2 roles, B1 plan + web app, standard test, action group, 2 metric alerts, 1 log alert |
| [`infra/deploy.sh`](infra/deploy.sh) / [`load.sh`](infra/load.sh) / [`chaos.sh`](infra/chaos.sh) / [`teardown.sh`](infra/teardown.sh) | what-if → deploy → publish → zip deploy → `/healthz`; mixed traffic with a status tally; fault injection on/off; delete the group |
| [`tests/Contoso.Orders.Api.Tests`](tests/Contoso.Orders.Api.Tests) | 43 xUnit tests (below) |

## Build and test (here, no Azure needed)

```bash
cd tests/Contoso.Orders.Api.Tests
dotnet test            # Passed!  - Failed: 0, Passed: 43, Skipped: 0, Total: 43
#   TelemetryTests   7  real app + in-memory exporter: request/price span parent-child, tags, metrics,
#                       no customer id in any tag, 400/404/422 successful, 500 failed + exception log in the same trace
#   Processor tests  9  which status codes flip, client spans and explicit errors untouched
#   Sampling + chaos 8  config validation, deterministic fault injection
#   KqlTests        12  6 query files parsed + type-checked against the App* tables; 4 broken queries must fail
#   BicepTests       7  bicep build: Entra-only, daily cap, 5 locations / locations-2, requests/failed,
#                       log alert query == the .kql file, every alert has the action group, role + app settings

cd ../../infra
bicep lint main.bicep  # clean (bicepconfig.json rules at error)
bicep build main.bicep --stdout > /dev/null && bicep build-params main.bicepparam --stdout > /dev/null
bash -n deploy.sh load.sh chaos.sh teardown.sh
```

Verified in this container (.NET SDK 10.0.115, Bicep CLI 0.49.2, Microsoft.OpenTelemetry 1.2.0,
Microsoft.Azure.Kusto.Language 12.4.1): 43 passed (three runs), lint/build clean. The API ran locally with the console
exporter and `load.sh` against it gave `201: 40, 400: 4, 404: 2, 422: 2` for 20 rounds; the console showed the
`POST /orders` server span and the `orders.price` span with `order.total: 538.98`. **Mutation check:** removing the
`AddProcessor<ExpectedClientErrorProcessor>()` line makes exactly the three 400/404/422 tests fail.
**Not run here:** anything in Azure (deployment, export to Application Insights, alerts, the availability test).
See [demo.md](demo.md).

## Run locally

```bash
cd src/Contoso.Orders.Api
dotnet run --urls http://localhost:5199      # no connection string: in-memory store, spans printed to the console
../../infra/load.sh http://localhost:5199 20
```

## Deploy, demo, tear down (needs a subscription)

```bash
az login
ALERT_EMAIL=you@example.com infra/deploy.sh rg-contoso-monitoring swedencentral
infra/load.sh https://<app>.azurewebsites.net 100
infra/chaos.sh rg-contoso-monitoring 30 && infra/load.sh https://<app>.azurewebsites.net 100   # alerts fire
infra/chaos.sh rg-contoso-monitoring 0
infra/teardown.sh rg-contoso-monitoring
```

## What we learned / gotchas

- **`ExportTarget.None` turns telemetry off, not just the exporter.** The first draft used it when no connection
  string is set. Six telemetry tests failed with *zero* spans: the in-memory exporter added by the tests got nothing,
  because with `None` the distro builds no pipeline. Locally the app now uses `ExportTarget.Console`, which also
  makes the spans visible in the terminal. (Found by our own tests.)
- **Every 4xx is a failed request by default.** Learn: the Azure Monitor exporter treats HTTP 4xx as failure when the
  span status is Unset. Validation errors and "not found" would inflate *Failed requests* and trip the alert; the
  processor sets status Ok for 400/404/422 only. The result code stays in the `requests` data.
- **The distro samples by default.** Rate-limited at 5 traces per second (.NET distro). Logs follow trace sampling by
  default in .NET. Metrics are never sampled, and standard metrics like `requests/failed` are pre-aggregated, so
  their accuracy isn't affected by sampling. Count in KQL with `sum(ItemCount)`; a test rejects `count()` on
  `AppRequests`.
- **Switching to fixed-rate sampling needs `TracesPerSecond = null`.** Setting only `SamplingRatio` keeps the
  rate-limited default (Learn note for the .NET distro). `SamplingSettings.Validate()` refuses both at once.
- **The server span doesn't carry the exception.** For the injected 500, the span has status Error but no exception
  event; the exception arrives as the error log written by `UseExceptionHandler`, in the same trace (a test checks
  the trace id), and ends up in `AppExceptions`.
- **Custom metric dimensions in Metrics explorer are opt-in.** The pre-aggregated copy of a custom metric has no
  dimensions unless you enable "With dimensions" (preview, billed separately). The log copy (`AppMetrics`) keeps all
  of them, so the per-channel chart is KQL.
- **`loadTextContent()` compiles to a template variable.** The Bicep test first compared the alert `query` to the
  file and got `[variables('$fxv#0')]`; it now resolves the variable. One file, two consumers: the alert and the test.
- **`AppRoleName` = `service.name`** when `service.namespace` isn't set (Learn), so the alert filters on
  `contoso-orders-api`. *Verify in the lab:* the recorder checks the role name on the first rows before trusting the
  alert (demo.md, step 3), because resource detectors also set attributes on App Service.
- **Kusto.Language catches typos, not everything.** Misspelled tables/columns and `real + string` fail; comparing the
  bool `Success` to the string `"false"` passed the checker, so that case isn't in the "must fail" list.
- **URL ping tests retire on 30 September 2028**; this episode only uses a standard test (billed per execution).

## References
- Blog: [Monitoring & Application Insights — Complete Guide](https://www.devladlog.com/articles/azure/2026-01-23-monitoring-application-insights-complete-guide-2026/)
- [Configure OpenTelemetry in Application Insights](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-configuration) (Microsoft OpenTelemetry Distro, connection string, cloud role name, sampling defaults and `TracesPerSecond = null`, Entra credential, live metrics)
- [Add and modify OpenTelemetry](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-add-modify) (custom spans and `AddSource`, custom metrics and aggregation types, override error status for HTTP 4xx)
- [Automatic data collection and resource detectors](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-collect-detect) (ASP.NET Core, HttpClient, SqlClient, Azure SDK included)
- [Sampling in Application Insights with OpenTelemetry](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-sampling) (metrics not sampled, validate sampling query, daily cap as last resort)
- [Metrics in Application Insights](https://learn.microsoft.com/azure/azure-monitor/app/metrics-overview) (standard metrics vs log-based, custom metric dimensions, `itemCount`)
- [Supported metrics for microsoft.insights/components](https://learn.microsoft.com/azure/azure-monitor/reference/supported-metrics/microsoft-insights-components-metrics) (`requests/failed`, `availabilityResults/availabilityPercentage`)
- [Application Insights telemetry data model](https://learn.microsoft.com/azure/azure-monitor/app/data-model-complete) and the table references [AppRequests](https://learn.microsoft.com/azure/azure-monitor/reference/tables/apprequests), [AppDependencies](https://learn.microsoft.com/azure/azure-monitor/reference/tables/appdependencies), [AppExceptions](https://learn.microsoft.com/azure/azure-monitor/reference/tables/appexceptions), [AppTraces](https://learn.microsoft.com/azure/azure-monitor/reference/tables/apptraces), [AppMetrics](https://learn.microsoft.com/azure/azure-monitor/reference/tables/appmetrics), [AppAvailabilityResults](https://learn.microsoft.com/azure/azure-monitor/reference/tables/appavailabilityresults), [Usage](https://learn.microsoft.com/azure/azure-monitor/reference/tables/usage)
- [Application Insights availability tests](https://learn.microsoft.com/azure/azure-monitor/app/availability) (standard tests, 5 locations, threshold = locations − 2, population tags, URL ping retirement 30 Sep 2028)
- [Microsoft Entra authentication for Application Insights](https://learn.microsoft.com/azure/azure-monitor/app/azure-ad-authentication) (`DisableLocalAuth`)
- [Azure Monitor Logs cost calculations](https://learn.microsoft.com/azure/azure-monitor/logs/cost-logs) and [Set a daily cap](https://learn.microsoft.com/azure/azure-monitor/logs/daily-cap)
- Prices in demo.md: [Azure Retail Prices API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices) (EUR, Sweden Central, queried 21 Nov 2026)
