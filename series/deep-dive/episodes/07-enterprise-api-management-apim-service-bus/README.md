# DEVLADLOG Deep Dive #7 — Enterprise API management (Azure API Management + Service Bus)

In episodes 3 and 4 Contoso's purchase requests got a secure API and an approval process. Now other systems (the
shop floor app, a partner portal, a nightly job) need to tell Contoso about purchase events, and finance wants to
review every purchase of 5,000 EUR or more, **exactly once**, even when a caller retries after a network blip.
One front door does it: API Management in front of a Service Bus topic.

```
caller (Entra app-only token + subscription key)
   │  POST /purchasing/purchase-events      Idempotency-Key: <guid>
   ▼
API Management, Consumption tier ── validate-jwt ─► rate-limit ─► validate-content ─► key → MessageId, label by total
   │  system-assigned identity, Azure Service Bus Data Sender on ONE topic     REST: POST /<topic>/messages
   ▼
Service Bus Standard, topic purchase-events (duplicate detection 10 min, shared keys off)
   ├─ subscription all-events        ──► worker (dotnet, DefaultAzureCredential, Data Receiver)
   └─ subscription finance-review    ──► worker   (correlation filter: label = purchase.high)
```

- **The gateway answers 202, not 200.** Accepted for processing, not processed. Service Bus replies 201 to the
  gateway; the outbound policy turns that into 202 with the caller's key echoed back.
- **Idempotency by key.** The caller's `Idempotency-Key` (a GUID, checked by the policy) becomes the Service Bus
  `MessageId`. With duplicate detection on, a repeat inside the window is accepted and silently dropped
  (Learn: the send "succeeds" but the new message is ignored).
- **No secrets in the policy.** `authentication-managed-identity resource="https://servicebus.azure.net/"`; namespace
  shared keys are disabled (`disableLocalAuth`); the gateway identity has *Azure Service Bus Data Sender* on the topic only.
- **Routing by label, decided once at the edge.** 5,000 and above gets `Label: purchase.high`; the `finance-review`
  subscription has a correlation filter on that label. The worker re-checks that label and total agree.
- **Consumers stay idempotent.** The window is finite and delivery is at-least-once: the worker records processed
  `MessageId`s, dead-letters poison messages with a reason and abandons on transient failures.

| Path | What it is |
|---|---|
| [`apim/policies/purchase-events.policy.xml`](apim/policies/purchase-events.policy.xml) | The API policy: token, rate, body, idempotency key, label, managed identity, URL rewrite, 201→202. Valid XML (single-quoted attributes, entities) |
| [`apim/openapi/purchase-events.openapi.json`](apim/openapi/purchase-events.openapi.json) | OpenAPI 3.0 definition imported into APIM; its schema is what `validate-content` enforces |
| [`apim/entra/New-GatewayApps.ps1`](apim/entra/New-GatewayApps.ps1) | Azure CLI: the API app registration (v2 tokens, `Purchase.Submit` role), a caller app, role grant, secret in `$env:` only. `-WhatIf` supported. Needs tenant |
| [`infra/main.bicep`](infra/main.bicep), [`main.bicepparam`](infra/main.bicepparam) | APIM Consumption, named values, API + policy, API-scoped subscription, Service Bus Standard (topic, 2 subscriptions, filter), role assignments |
| [`src/PurchaseEvents.Worker`](src/PurchaseEvents.Worker) | .NET 10 consumer: `PurchaseEventHandler` (decisions), `Program.cs` (processor with manual settlement), `PurchaseRouting` (threshold + labels) |
| [`scripts/PurchaseGateway.psm1`](scripts/PurchaseGateway.psm1) | `Get-GatewayToken` (client credentials), `Send-PurchaseEvent` (what the demo calls) |
| [`tests/PurchaseEvents.Tests`](tests/PurchaseEvents.Tests) | 48 xUnit tests; [`scripts/PurchaseGateway.Tests.ps1`](scripts/PurchaseGateway.Tests.ps1): 7 Pester tests |

## Test locally (no Azure, no tenant)

```bash
dotnet test tests/PurchaseEvents.Tests -m:1                                      # Passed: 48 (about 18 s)
pwsh -NoProfile -c 'Invoke-Pester ./scripts/PurchaseGateway.Tests.ps1'           # Tests Passed: 7
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep # no warnings
bicep build-params infra/main.bicepparam --stdout > /dev/null
```

There is no local API Management gateway in this container (no Docker daemon), so the policy cannot run end to end
here. What the tests do instead:

- **Every expression in the policy is compiled** with Roslyn (`Microsoft.CodeAnalysis.CSharp.Scripting`) and the
  ones that carry logic are **run**: key normalisation, the GUID check, the label by total (including 4,999.99 and 5,000),
  the `BrokerProperties` JSON, the 201→202 body. They run against a small hand-written stand-in for APIM's `context`
  (test code only; members and shapes as documented on Learn). That proves syntax and logic, not the gateway's runtime.
- **Contract tests** read the policy, the OpenAPI file and the *compiled* Bicep (real `bicep build`) and check that they
  agree: Consumption has no forbidden policies and the document is under 16 KiB; the threshold and labels equal the
  worker's; every `{{named value}}` is defined; Service Bus is Standard with local auth off and duplicate detection on;
  the finance rule filters on the label the policy sets; the gateway has only Data Sender, scoped to the topic; every
  value the OpenAPI schema allows is accepted by the worker's validation, and the boundaries are rejected.
- **Worker decisions** run against real `ServiceBusReceivedMessage` objects (`ServiceBusModelFactory`): duplicate
  `MessageId`, transient failure then success, poison content, label mismatch, cancellation.

Tested with .NET SDK 10.0.115, `Azure.Messaging.ServiceBus` 7.20.1, `Azure.Identity` 1.17.1,
`Microsoft.CodeAnalysis.CSharp.Scripting` 4.14.0, xUnit 2.9.3, PowerShell 7 with Pester 5, Bicep CLI (current in the container).

## Deploy and run (needs the lab Azure subscription and tenant)

Full runbook, costs, masking and tear-down in [`demo.md`](demo.md). Short version:

```bash
./apim/entra/New-GatewayApps.ps1                         # needs az login; prints the three ids
az group create -n rg-mglab-deep-dive-07 -l westeurope
az deployment group create -g rg-mglab-deep-dive-07 -f infra/main.bicep -p apiClientId=<id> publisherEmail=<lab UPN> receiverPrincipalId=<your object id>
dotnet run --project src/PurchaseEvents.Worker -- --namespace <ns>.servicebus.windows.net --topic purchase-events --subscription finance-review
```

## What we learned / gotchas

- **Consumption tier is a different product in the details.** Learn's gateway comparison says `rate-limit-by-key`,
  `quota-by-key` and the LLM token limit policies are **not available** on Consumption, so the policy uses `rate-limit`
  (per subscription key; "only applied when an API is accessed using a subscription key", so the API requires one).
  The policy document is capped at **16 KiB** (classic and v2: 512 KiB), the `validate-content` body at 100 KiB, a
  request may last 30 seconds in total, and there are no Log Analytics request logs (Application Insights only).
- **The built-in `send-service-bus-message` policy is not for Consumption.** Learn lists it as classic-tier (preview).
  The portable route, which also works on Consumption, is the Service Bus REST *Send message* call authenticated with the
  gateway's managed identity (`authentication-managed-identity`, resource `https://servicebus.azure.net/`, listed in
  Learn's examples; works on all tiers). Message properties travel in a `BrokerProperties` JSON header.
- **A duplicate is not an error.** Service Bus reports the duplicate send as accepted and drops it, so the caller (and
  our 202) cannot tell. That is what makes retries safe, and why the 202 means "accepted", not "new". The window defaults to
  10 minutes (min 20 s, max 7 days) and duplicate detection **cannot be changed after creation** (Learn FAQ: immutable).
  Basic tier has no duplicate detection and no topics: Standard is the minimum.
- **Policy XML has to be valid XML to be testable.** APIM's docs show `As<JObject>` and `"` inside double-quoted
  attributes; this file uses single-quoted attributes and `&lt;` / `&gt;` so that any XML parser (and our tests) can read it.
  Not verified in the lab: that the gateway decodes the entities exactly like that on import. If it does not, only
  `As<JObject>` and `>=` in the `label` expression change, and the Roslyn tests will tell you what the code means.
- **v2 tokens and the audience.** Learn: for v2.0 tokens `aud` is the API's client ID (a GUID); v1.0 tokens carry the
  Application ID URI. `requestedAccessTokenVersion` null or 1 means v1.0 tokens. The Entra script sets it to 2 and the policy
  validates the GUID against the v2.0 OpenID metadata. A mismatch gives a plain 401.
- **App-only callers use the `roles` claim.** The caller app gets an application permission (app role) on the API; the policy
  requires `Purchase.Submit` in `roles`. A user token would carry `scp` instead.
- **APIM is soft-deleted for 48 hours** after you delete the resource group; the name cannot be reused until you purge
  (`az apim deletedservice purge`). The demo's tear-down purges it.
- **Bicep:** a nested child resource and an `existing` reference to the same topic fail with BCP121 (same symbolic name
  within the file). Referencing the nested resource as `serviceBus::topic` as the role assignment scope fixed it.
  The `$Default` rule of a subscription is replaced by declaring a rule named `$Default`.
- **Standard Service Bus is cheap but not free:** Learn's FAQ describes a base charge per Azure subscription that has a
  Standard namespace, plus operation charges. Delete the group the same day.
- **Not verified in the lab yet (needs tenant/subscription):** the deployment itself and how long a Consumption instance
  takes; that the `$Default` override leaves a single correlation rule; that `Label` in `BrokerProperties` is what the
  correlation filter's `label` matches (both are the message Label/Subject property per the REST and ARM docs, but the
  end-to-end result is only proven by the `topic-screen` capture); what other client headers do when forwarded to the REST
  endpoint (Learn: non-reserved headers become custom properties; we delete only the subscription key and the idempotency
  key); the flags of the Azure CLI calls in `New-GatewayApps.ps1` (syntax-checked only).

## References

- [Send Message (Service Bus REST): BrokerProperties, custom headers, 201](https://learn.microsoft.com/rest/api/servicebus/send-message-to-queue) · [Send a Service Bus message with Entra authentication (REST)](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-rest-send-entra-token-how-to)
- [Duplicate detection (window, tiers, MessageId)](https://learn.microsoft.com/azure/service-bus-messaging/duplicate-detection) · [Service Bus FAQ (immutable properties, Standard base charge, 256 KB)](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-faq) · [Service Bus tiers](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-premium-messaging#choosing-a-tier)
- [Authenticate with managed identity (policy)](https://learn.microsoft.com/azure/api-management/authentication-managed-identity-policy) · [Validate JWT](https://learn.microsoft.com/azure/api-management/validate-jwt-policy) · [Validate content](https://learn.microsoft.com/azure/api-management/validate-content-policy) · [Limit call rate by subscription](https://learn.microsoft.com/azure/api-management/rate-limit-policy) · [Limit call rate by key (not on Consumption)](https://learn.microsoft.com/azure/api-management/rate-limit-by-key-policy)
- [Send service bus message policy (classic tiers, preview)](https://learn.microsoft.com/azure/api-management/send-service-bus-message-policy) · [Policy expressions (allowed types, `context`)](https://learn.microsoft.com/azure/api-management/api-management-policy-expressions)
- [API gateway: feature comparison and runtime limits per tier](https://learn.microsoft.com/azure/api-management/api-management-gateways-overview) · [API Management tiers](https://learn.microsoft.com/azure/api-management/api-management-features) · [Plan and manage costs (Consumption: no fixed cost)](https://learn.microsoft.com/azure/api-management/plan-manage-costs) · [Soft-delete](https://learn.microsoft.com/azure/api-management/soft-delete)
- [Service Bus roles and scopes](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-managed-service-identity#assign-a-service-bus-role-to-the-managed-identity) · [Azure built-in roles: Service Bus Data Sender / Receiver](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/integration) · [Secure Service Bus (disable local auth)](https://learn.microsoft.com/azure/service-bus-messaging/secure-service-bus#identity-and-access-management)
- [Entra access tokens: v1.0 vs v2.0](https://learn.microsoft.com/entra/identity-platform/access-tokens#token-formats) · [Claims validation: audience](https://learn.microsoft.com/entra/identity-platform/claims-validation#validate-the-audience) · [Bicep: Microsoft.ApiManagement/service](https://learn.microsoft.com/azure/templates/microsoft.apimanagement/service)
- Blog: [Enterprise API Management — Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-03-17-enterprise-api-management-azure-apim-service-bus-microservices/)
