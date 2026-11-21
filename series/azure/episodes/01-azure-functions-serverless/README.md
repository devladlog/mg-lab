# DEVLADLOG Azure #1 — Azure Functions & Serverless

A serverless **order intake** on Azure Functions, built the way a new app should be built in late 2026:

- **.NET 10, isolated worker model** (support for the in-process model ended on 10 November 2026)
- **Flex Consumption plan** (.NET 10 can't run on Linux Consumption, which itself retires on 30 September 2028)
- **No storage keys**: the storage account has shared-key access disabled; one user-assigned managed identity is used
  for host storage, the deployment container, the bindings and Application Insights
- Three functions, one pattern: **answer fast, queue the work, make retries safe, watch the poison queue**

```
POST /api/orders ──► SubmitOrder ──(202 + message)──► queue "orders" ──► ProcessOrder ──► blob orders-processed/{OrderId}.json
                       │                                                   │ throws (unknown SKU)
                       └─ 400 + errors, nothing queued                     └─ retried 5x ──► "orders-poison" ──► OrderPoison (LogError)
```

| Path | What it is |
|---|---|
| [`src/OrderIntake.Core/OrderRules.cs`](src/OrderIntake.Core/OrderRules.cs) | Shape validation (customer, 1–20 lines, SKU `ABC-123`, quantity 1–100, no duplicate SKUs). Pure, no I/O |
| [`src/OrderIntake.Core/Pricing.cs`](src/OrderIntake.Core/Pricing.cs) | Catalogue lookup + 5 % discount from €500. Throws `UnknownSkuException` |
| [`src/OrderIntake/OrderIntake.csproj`](src/OrderIntake/OrderIntake.csproj) | `Azure.Functions.Sdk` project SDK, `net10.0`, worker 2.52.0, HTTP/Queues/Blobs extensions |
| [`src/OrderIntake/Functions/SubmitOrder.cs`](src/OrderIntake/Functions/SubmitOrder.cs) | HTTP POST `orders`, function key. Multiple outputs: `[HttpResult]` + `[QueueOutput]` |
| [`src/OrderIntake/Functions/ProcessOrder.cs`](src/OrderIntake/Functions/ProcessOrder.cs) | Queue trigger → blob output named after the order id (idempotent on retry) |
| [`src/OrderIntake/Functions/OrderPoison.cs`](src/OrderIntake/Functions/OrderPoison.cs) | Queue trigger on `orders-poison` → `LogError` you can alert on |
| [`src/OrderIntake/host.json`](src/OrderIntake/host.json) | `maxDequeueCount: 5`, `visibilityTimeout: 5 s` (so the demo retries quickly) |
| [`src/OrderIntake/local.settings.sample.json`](src/OrderIntake/local.settings.sample.json) | Azurite settings; copy to `local.settings.json` (git-ignored) |
| [`tests/OrderIntake.Tests`](tests/OrderIntake.Tests) | 33 xUnit tests: rules, pricing, functions called directly, binding contract |
| [`infra/main.bicep`](infra/main.bicep) | Flex Consumption (FC1), .NET 10 runtime, storage with keys off, UAMI + 4 role assignments, App Insights (local auth off) |
| [`infra/deploy.sh`](infra/deploy.sh) | `what-if` → deploy → `dotnet publish` → `az functionapp deployment source config-zip` |
| [`infra/smoke.sh`](infra/smoke.sh) | Valid (202), invalid (400) and poison (202, then 5 attempts) orders with curl |
| [`infra/teardown.sh`](infra/teardown.sh) | `az group delete` |

## Build and test (run here, no Azure needed)

```bash
cd tests/OrderIntake.Tests
dotnet test                      # Passed!  - Failed: 0, Passed: 33, Skipped: 0, Total: 33

cd ../../infra
bicep lint main.bicep            # clean, with the rules in bicepconfig.json set to error
bicep build main.bicep --stdout > /dev/null && bicep build-params main.bicepparam --stdout > /dev/null
bash -n deploy.sh smoke.sh teardown.sh
```

Verified in this container: `dotnet test` (33 passed, .NET SDK 10.0.115), `dotnet publish -c Release` (12 MB output,
`extensions.json` lists the Queues and Blobs extensions), the source-generated function metadata (3 functions, bindings
as expected), `bicep lint` / `build` / `build-params` (Bicep 0.49.2), and `smoke.sh` against a dummy local server.
**Not run here:** the Functions host (`func start`) and Azurite. Core Tools aren't installed in this container, so the
end-to-end local run and everything in Azure is done by the recorder (see [demo.md](demo.md)).

## Run locally (recorder's machine)

```bash
npx azurite --silent --location /tmp/azurite &          # storage emulator
cd src/OrderIntake && cp local.settings.sample.json local.settings.json
func start                                              # Core Tools v4; finds SubmitOrder, ProcessOrder, OrderPoison
../../infra/smoke.sh http://localhost:7071              # keys aren't checked locally
```

## Deploy, test, tear down (needs a subscription)

```bash
az login
infra/deploy.sh rg-orders-demo swedencentral
APP=$(az functionapp list -g rg-orders-demo --query "[0].name" -o tsv)
KEY=$(az functionapp function keys list -g rg-orders-demo -n $APP --function-name SubmitOrder --query default -o tsv)
infra/smoke.sh "https://$(az functionapp show -g rg-orders-demo -n $APP --query defaultHostName -o tsv)" "$KEY"
infra/teardown.sh rg-orders-demo
```

## What we learned / gotchas

- **Binding expressions on JSON payloads don't work with SDK types.** The first draft of `ProcessOrder` bound the
  trigger to `Azure.Storage.Queues.Models.QueueMessage` (to log `DequeueCount`) and used `{OrderId}` in the blob path.
  It compiled and its unit tests passed. Microsoft Learn says payload properties in binding expressions require a
  string or a POCO trigger parameter, *"You can't use it with streams, clients, or other SDK types."* Fix: bind
  `OrderMessage`, read `DequeueCount` from `FunctionContext.BindingContext.BindingData`. A contract test now pins the
  parameter type. (Found by reading the docs before the live run. The recorder confirms in Azure that the blob name
  equals the order id.)
- **Function keys aren't enforced locally.** `AuthorizationLevel.Function` only applies after publishing to Azure,
  so the local smoke test works without a key and the Azure one needs `x-functions-key`.
- **Give the bindings their own connection name.** Learn recommends not reusing `AzureWebJobsStorage` for non-host
  components when you use managed identities. The bindings use `OrdersStorage__queueServiceUri` /
  `__blobServiceUri` / `__credential` / `__clientId`; host storage uses `AzureWebJobsStorage__accountName`.
- **Queue triggers are at-least-once.** A failed message comes back (after `visibilityTimeout`) and is tried up to
  `maxDequeueCount` (default 5) times before it moves to `<queue>-poison`. The blob is named after the order id so a
  retry overwrites instead of duplicating.
- **Flex Consumption config isn't in app settings.** Runtime (`dotnet-isolated` / `10.0`), scale (max instances,
  instance memory 512/2048/4096 MB) and the deployment container live in `functionAppConfig`. Don't set
  `WEBSITE_RUN_FROM_PACKAGE`.
- **`Azure.Functions.Sdk`** replaces both `Microsoft.NET.Sdk` and the `Microsoft.Azure.Functions.Worker.Sdk` package.
  You still reference `Microsoft.Azure.Functions.Worker` explicitly.
- **Conditional queue output = an array.** `SubmitOrderOutput.Messages` is an `OrderMessage[]` (one message per
  element, the pattern Learn uses for multiple messages), empty by default, so 400/415 replies queue nothing. Unit
  tests check the return object; the recorder confirms in Azure that the queue stays empty after the 400.
- **`.bicepparam` names its template.** The first `deploy.sh` passed both `--template-file main.bicep` and
  `--parameters main.bicepparam`; Learn says the Azure CLI rejects that ("Only a .bicep file is allowed with a
  .bicepparam file"). The script now passes only the parameters file. (Caught by reading the docs, not by a run.)
- **.NET 8 is not the target any more.** The Flex runtime list on Learn shows .NET 8 end of life on 9 Nov 2026;
  .NET 10 (LTS) is supported there until 9 Nov 2028.

## References
- Blog: [Azure Functions & Serverless — Complete Guide](https://www.devladlog.com/articles/azure/2026-01-05-azure-functions-serverless-complete-guide-2026/)
- [Guide for running C# Azure Functions in the isolated worker model](https://learn.microsoft.com/azure/azure-functions/dotnet-isolated-process-guide) (Azure.Functions.Sdk, multiple outputs, `[HttpResult]`, supported versions)
- [Differences between the isolated worker model and the in-process model](https://learn.microsoft.com/azure/azure-functions/dotnet-isolated-in-process-differences) (in-process end of support 10 Nov 2026; .NET 10 not on Linux Consumption)
- [Azure Functions Flex Consumption plan hosting](https://learn.microsoft.com/azure/azure-functions/flex-consumption-plan) (benefits, instance sizes, supported stacks)
- [Azure Functions Consumption plan hosting (legacy)](https://learn.microsoft.com/azure/azure-functions/consumption-plan) (Linux Consumption retires 30 Sep 2028)
- [Create your function app resources using Bicep (Flex Consumption)](https://learn.microsoft.com/azure/azure-functions/functions-create-first-function-bicep)
- [Package-based deployment for Azure Functions (Flex Consumption)](https://learn.microsoft.com/azure/azure-functions/deployment-zip-push)
- [Get-AzFunctionAppFlexConsumptionRuntime](https://learn.microsoft.com/powershell/module/az.functions/get-azfunctionappflexconsumptionruntime) (runtime versions and end-of-life dates)
- [Azure Queue storage trigger](https://learn.microsoft.com/azure/azure-functions/functions-bindings-storage-queue-trigger) (poison messages, peek-lock, metadata) and [host.json settings](https://learn.microsoft.com/azure/azure-functions/functions-bindings-storage-queue#hostjson-settings)
- [Azure Functions binding expressions and patterns](https://learn.microsoft.com/azure/azure-functions/functions-bindings-expressions-patterns#json-payloads)
- [Configure connections to remote services (identity-based)](https://learn.microsoft.com/azure/azure-functions/manage-connections) (settings, roles)
- [Azure Functions HTTP trigger](https://learn.microsoft.com/azure/azure-functions/functions-bindings-http-webhook-trigger) (auth levels, `x-functions-key`, 230-second limit)
