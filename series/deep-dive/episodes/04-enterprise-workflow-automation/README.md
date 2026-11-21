# DEVLADLOG Deep Dive #4 — Enterprise workflow automation (Durable Functions + Service Bus + Power Automate + SharePoint)

Episode 1 left Contoso's invoices in SharePoint marked **Ready**. Now they need approval: the manager for every
invoice, the finance director above 5,000 EUR, and if nobody answers before the deadline the request **escalates**.
An approval can wait for days, a late answer to an escalated request must not count, the same invoice must never be
approved twice, and nobody approves an invoice they uploaded.

```
SharePoint "Invoices Inbox" ─(flow 1: Ready)─► Service Bus Basic queue ─► OnInvoiceReady ─► InvoiceApproval orchestration (Durable Functions, .NET 10, Flex Consumption)
        ▲                                     Send-only SAS on 1 queue    instance ID =        │  stage → request → race(decision event, durable timer) → escalate once
        │                                                                 invoice key         ▼
        └── flow 2 "relay": update columns ◄── SendApprovalRequest / RecordOutcome ──► flow 2: Start and wait for an approval (Teams/Outlook)
                                                                                              │
                     SubmitDecision  ◄──── POST signed callback URL (one per request) ────────┘
```

- **Durable owns the process, Power Automate owns the people.** The orchestration holds the state machine:
  stages, deadlines, escalation, final status. The relay flow does what Power Automate is best at: an approval in
  Teams and Outlook, updating SharePoint, mailing the submitter. A cloud flow run lasts at most 30 days *including*
  pending approvals; the orchestration has no such limit and every rule is code with tests.
- **A late answer can't win.** Each request gets its own ID, its own external event name and its own signed callback
  URL. After an escalation, the old request's answer gets 409 and the flow tells that approver it wasn't used.
- **Idempotent intake.** Service Bus Basic has no duplicate detection, so the invoice key from episode 1 becomes the
  orchestration instance ID: a second message for the same invoice finds the running instance and stops. An
  *expired* approval can be restarted (reset the status to Not started); approved or rejected is final.
- **Keyless where it can be.** Storage (code package + task hub), Service Bus receive, Key Vault references and
  Application Insights all use the function's user-assigned identity. The flow stores no secret: the callback URL is
  an HMAC for one request. The one shared key left is a **Send-only** SAS policy on one queue, for the Service Bus
  connector in flow 1.

| Path | What it is |
|---|---|
| [`src/InvoiceApproval/InvoiceApprovalOrchestrator.cs`](src/InvoiceApproval/InvoiceApprovalOrchestrator.cs) | Class-based `TaskOrchestrator` + `[Function]` wrapper: stages, `CreateTimer` vs `WaitForExternalEvent` race, one escalation, custom status, retry policy on activities |
| [`src/InvoiceApproval/ApprovalPlan.cs`](src/InvoiceApproval/ApprovalPlan.cs) | Manager always, finance above the threshold; the submitter never approves their own invoice |
| [`src/InvoiceApproval/InvoiceIntake.cs`](src/InvoiceApproval/InvoiceIntake.cs) | Service Bus trigger (`%InvoiceQueueName%`, identity connection), strict message parsing, instance ID = invoice key, restart only after expiry |
| [`src/InvoiceApproval/DecisionEndpoint.cs`](src/InvoiceApproval/DecisionEndpoint.cs) | `POST /api/approvals/{instanceId}/{requestId}/decision?sig=…`: signature, live request, assigned approver, then `RaiseEventAsync` |
| [`src/InvoiceApproval/CallbackSigner.cs`](src/InvoiceApproval/CallbackSigner.cs) | HMAC-SHA256 per request, constant-time compare |
| [`src/InvoiceApproval/ApprovalActivities.cs`](src/InvoiceApproval/ApprovalActivities.cs) | Activities that post to the relay flow; `HttpFlowGateway` (SAS URL, or a managed-identity token for "Specific users in my tenant") |
| [`src/InvoiceApproval/host.json`](src/InvoiceApproval/host.json) | Task hub name, `maxQueuePollingInterval` 10 s (Learn's Flex Consumption recommendation) |
| [`flow/invoice-ready-to-queue.definition.json`](flow/invoice-ready-to-queue.definition.json) | Flow 1 (reference): SharePoint trigger with conditions → Service Bus *Send message* |
| [`flow/approval-relay.definition.json`](flow/approval-relay.definition.json) | Flow 2 (reference): HTTP trigger → switch → update columns / *Start and wait for an approval* / POST callback / mail |
| [`contract/approval-columns.json`](contract/approval-columns.json) | The five columns this episode adds to the episode 1 library |
| [`provision/ApprovalColumns.psm1`](provision/ApprovalColumns.psm1), [`Add-ApprovalColumns.ps1`](provision/Add-ApprovalColumns.ps1) | PnP PowerShell, idempotent, `-WhatIf` |
| [`infra/main.bicep`](infra/main.bicep) | Flex Consumption (`dotnet-isolated` 10.0), storage without shared keys, Service Bus **Basic** + queue + Send-only rule, Key Vault (RBAC), App Insights, least-privilege roles |
| [`tests/InvoiceApproval.Tests`](tests/InvoiceApproval.Tests) | 45 xUnit tests; [`provision/ApprovalColumns.Tests.ps1`](provision/ApprovalColumns.Tests.ps1): 9 Pester tests |

## Test locally (no Azure, no tenant)

```bash
dotnet test tests/InvoiceApproval.Tests -m:1                                   # Passed: 45 (about 11 s)
pwsh -NoProfile -c 'Invoke-Pester ./provision/ApprovalColumns.Tests.ps1'      # Tests Passed: 9
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep   # no warnings
dotnet publish src/InvoiceApproval -c Release -o publish                       # functions.metadata lists 5 functions
```

How the orchestration is tested: `Microsoft.DurableTask.InProcessTestHost` (`DurableTaskTestHost`) runs a complete
Durable Task engine in memory. The tests register the **real** orchestrator (same name and body as the Functions
wrapper) and the **real** activity code; only the Power Automate flow is replaced by a `FakeFlow` that records the
messages. The tests then play the flow's part: they take the signed callback URL from the message and call
`DecisionHandler` against the engine's real `DurableTaskClient`. Timers are real (stage timeouts of 1–2 seconds), so
escalation, expiry and the late answer after an escalation all run for real. `ContractTests` check that the code,
the two flow definitions, the column contract, `host.json` and the compiled Bicep agree.

Tested with .NET SDK 10.0.115, `Microsoft.Azure.Functions.Worker` 2.52.0, `…Extensions.DurableTask` 1.22.0
(Durable Task SDK 1.28.0), `…Extensions.ServiceBus` 5.24.0, `…Extensions.Http.AspNetCore` 2.1.1, `Azure.Identity`
1.21.0, `Microsoft.DurableTask.InProcessTestHost` **0.2.3-preview.1** (test project only), xUnit 2.9.3, PowerShell 7.6
with Pester, Bicep CLI 0.49.2.

## Deploy (needs an Azure subscription and the lab tenant)

The full runbook (columns, Key Vault secrets, both flows, test users) is in [`demo.md`](demo.md). Azure part:

```bash
az deployment group create -g rg-mglab-approvals -f infra/main.bicep -p infra/main.bicepparam -p stageTimeoutMinutes=5
cd src/InvoiceApproval && func azure functionapp publish <functionAppName> && cd ../..
```

## What we learned / gotchas

- **The Durable analyzer stops non-deterministic code at build time.** It ships in the Durable extension package and
  our build treats warnings as errors. Writing `DateTime.UtcNow` in the stage loop failed with `DURABLE0001 … uses
  'System.DateTime.UtcNow' that may cause non-deterministic behavior`; the first draft's `while (true)` retry loop
  failed with `DURABLE0011` (unbounded loop without `ContinueAsNew`), and returning a value from an activity the
  orchestrator called without a type failed with `DURABLE2002`. Time comes from `context.CurrentUtcDateTime`, IDs from
  `context.NewGuid()`, settings travel in the orchestration input (never read configuration in the orchestrator).
- **Race a timer against the event, and cancel the loser.** `WaitForExternalEvent` waits forever by default; Learn's
  pattern is `Task.WhenAny(event, CreateTimer(deadline, cts.Token))` and cancelling the timer when the event wins.
- **External events are at-least-once; use unique names.** Learn recommends a unique ID per event. We go further:
  one event *name* per request (`Decision-{requestId}`), so an answer to a replaced request can't complete the newer
  wait even if it gets past the endpoint's checks.
- **Set the custom status before calling the activity.** Both are committed at the same checkpoint, so when the
  approval reaches the approver, the decision endpoint already knows which request is live.
- **Cloud flows run at most 30 days, including pending approvals,** and Learn's approvals known-issues page says a
  flow waiting longer than 28 days fails while the approval stays in the action center. Long waits belong in the
  orchestration; the flow only relays.
- **Service Bus Basic = queues only, no duplicate detection.** The orchestration instance ID is the dedupe key.
  Invalid messages throw, Service Bus redelivers and dead-letters after `maxDeliveryCount` (5).
- **Least privilege has a scaling cost.** With an identity connection, the Service Bus extension needs *Data Owner*
  (or a custom role with read) for accurate scale counts; with *Data Receiver* it silently falls back to peek-based
  estimates. At a few invoices an hour we keep Receiver, scoped to the one queue.
- **The task hub storage is security-sensitive** (Learn: write access can change app behaviour), so the storage
  account has shared keys off and only the function's identity has data roles.
- **Flex Consumption and Durable:** Learn recommends `maxQueuePollingInterval` of 10 s or less (done) and one
  always-ready instance for the `durable` group. That instance is billed all the time, so the lab parameter
  `durableAlwaysReady` defaults to 0 and the first step after an idle period is slower.
- **The test host is a preview package.** Learn's unit-testing page asks for `Microsoft.DurableTask.InProcessTestHost`
  v1.0.0 or later; on NuGet (Nov 2026) only `0.2.3-preview.1` exists. It runs only in the test project.
- **Not verified in the lab yet (needs tenant):** both flow definitions were written by hand from the designer steps
  (replace them with the exported ones and re-run `ContractTests`); the exact parameter names of the Service Bus
  *Send message* and Approvals actions in the export; calling the HTTP trigger with the managed identity
  (`Flow__Audience`, token for `https://service.flow.microsoft.com/`): if it fails, use the SAS URL from Key Vault
  (the default); end-to-end timing on Flex Consumption.

## References

- [Human interaction pattern (approval, timeout, custom status)](https://learn.microsoft.com/azure/durable-task/common/durable-task-human-interaction) · [External events: unique names, timeouts](https://learn.microsoft.com/azure/durable-task/common/durable-task-external-events#best-practices) · [Durable timers](https://learn.microsoft.com/azure/durable-task/common/durable-task-timers)
- [Orchestrator code constraints](https://learn.microsoft.com/azure/durable-task/common/durable-task-code-constraints) · [Durable Task Roslyn analyzer rules](https://learn.microsoft.com/azure/durable-task/durable-functions/durable-functions-roslyn-analyzer#analyzer-rules)
- [Unit testing Durable Functions and the Durable Task SDKs (DurableTaskTestHost)](https://learn.microsoft.com/azure/durable-task/durable-functions/durable-functions-unit-testing)
- [Durable Functions in the .NET isolated worker](https://learn.microsoft.com/azure/durable-task/durable-functions/durable-functions-dotnet-isolated-overview) · [Supported .NET versions (isolated, .NET 10)](https://learn.microsoft.com/azure/azure-functions/dotnet-isolated-process-guide#supported-versions)
- [Flex Consumption: Durable Functions storage providers and considerations](https://learn.microsoft.com/azure/azure-functions/flex-consumption-plan#considerations) · [Azure Storage provider: Flex Consumption recommendations](https://learn.microsoft.com/azure/durable-task/durable-functions/durable-functions-azure-storage-provider#flex-consumption-plan) · [host.json `maxQueuePollingInterval`](https://learn.microsoft.com/azure/durable-task/durable-functions/durable-functions-host-json-settings)
- [Storage considerations: task hub security](https://learn.microsoft.com/azure/azure-functions/storage-considerations#important-considerations) · [Roles for identity-based connections (Service Bus, Durable)](https://learn.microsoft.com/azure/azure-functions/manage-connections#grant-permissions-to-an-identity)
- [Service Bus trigger: connections and scaling permissions](https://learn.microsoft.com/azure/azure-functions/functions-bindings-service-bus-trigger#connections) · [Service Bus tiers (Basic = queues only)](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-premium-messaging#choosing-a-tier) · [Secure Service Bus: limit SAS to one entity and Send](https://learn.microsoft.com/azure/service-bus-messaging/secure-service-bus#identity-and-access-management)
- [Key Vault references (RBAC, `keyVaultReferenceIdentity`)](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references)
- [Power Automate limits: 30-day run duration](https://learn.microsoft.com/power-automate/limits-and-config#duration-and-retention-limits) · [Approvals known issues (28 days)](https://learn.microsoft.com/power-automate/approvals-known-issues) · [Create and test an approval workflow](https://learn.microsoft.com/power-automate/modern-approvals)
- [OAuth authentication for HTTP request triggers](https://learn.microsoft.com/power-automate/oauth-authentication)
- Blog: [Enterprise Workflow Automation — Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-02-24-enterprise-workflow-automation-azure-power-platform-sharepoint/)
