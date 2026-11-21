# Demo shot list — DEVLADLOG Deep Dive #7, Enterprise API management (APIM + Service Bus)

Code, test and Bicep scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs tenant + Azure subscription** for everything on screen. Offline (container, no Azure): 48 xUnit tests and
7 Pester tests pass, `bicep build` and `bicep lint` are clean, the Entra script parses. **Not yet run against Azure:**
the Bicep deployment, the policy inside a real gateway, the Entra script. Record the outcome of each in the README.

## Lab environment

Recorded on the **lab Windows laptop** (host): Edge for the Azure portal, Windows Terminal with PowerShell 7 for the
calls and for the worker. No Hyper-V VM and no Power Platform environment are needed.

**Azure** (lab subscription, one resource group `rg-mglab-deep-dive-07`, West Europe)

| Resource | SKU | Cost for the recording window |
|---|---|---|
| API Management `apim-mgl07-<token>` | **Consumption** (capacity 0), system-assigned identity | no fixed cost; billed per call above a threshold (Learn: *Plan and manage costs for API Management*). A recording is a few hundred calls. Check the [pricing page](https://azure.microsoft.com/pricing/details/api-management/) on the day. |
| Service Bus namespace `sb-mgl07-<token>`, topic `purchase-events`, 2 subscriptions | **Standard** (topics + duplicate detection need Standard or Premium) | Standard has a base charge per Azure subscription that has a Standard namespace, plus per-operation charges: check the [pricing page](https://azure.microsoft.com/pricing/details/service-bus/) and delete the group the same day. |

Budget alert `mglab-monthly` (€30) stays active. No Key Vault, no storage, no VM, no Application Insights.

**Microsoft Entra (lab tenant)**: two app registrations created by `apim/entra/New-GatewayApps.ps1`
(`contoso-purchase-gateway` with app role `Purchase.Submit`, `contoso-purchase-caller` with one client secret).
Lab users: only `labadmin` (the recording account; Owner on the subscription, runs the worker). No licences needed.

**Local tools on the laptop:** Azure CLI, .NET SDK 10, Bicep CLI, PowerShell 7.2+, the repo checked out.

## Setup (off camera)

1. **Tests first**
   ```bash
   cd series/deep-dive/episodes/07-enterprise-api-management-apim-service-bus
   dotnet test tests/PurchaseEvents.Tests -m:1                                   # expect Passed: 48
   pwsh -NoProfile -c 'Invoke-Pester ./scripts/PurchaseGateway.Tests.ps1'        # expect Tests Passed: 7
   bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep
   ```
2. **Entra apps** (as labadmin)
   ```powershell
   az login                                                   # off camera
   ./apim/entra/New-GatewayApps.ps1 -WhatIf
   $ids = ./apim/entra/New-GatewayApps.ps1                    # prints tenantId, apiClientId, callerClientId; secret stays in $env:PURCHASE_CALLER_SECRET
   ```
   If the app role assignment call is refused, grant `Purchase.Submit` to `contoso-purchase-caller` in the portal:
   *App registrations > contoso-purchase-caller > API permissions > Add a permission > My APIs > contoso-purchase-gateway >
   Application permissions > Purchase.Submit*, then *Grant admin consent*.
3. **Deploy**
   ```bash
   az group create -n rg-mglab-deep-dive-07 -l westeurope
   az deployment group create -g rg-mglab-deep-dive-07 -f infra/main.bicep \
     -p apiClientId=<apiClientId> publisherEmail=<labadmin UPN> receiverPrincipalId=$(az ad signed-in-user show --query id -o tsv) \
     --query properties.outputs -o json > /tmp/apim-outputs.json        # don't show on camera
   ```
   **Check on first deploy and write the result into the README:** (a) the Consumption instance deploys (allow extra time:
   the provisioning time was not verified); (b) the `$Default` rule on `finance-review` is the correlation filter and not
   the default true rule (portal: topic > finance-review > Filters); (c) the API shows one operation, `POST /purchase-events`,
   with the schema from the OpenAPI file; (d) the role assignments propagate (up to about five minutes, Learn).
4. **Subscription key and a first smoke call** (env vars only, never on screen)
   ```powershell
   $out = Get-Content /tmp/apim-outputs.json | ConvertFrom-Json
   $sub = az account show --query id -o tsv
   $env:APIM_KEY = az rest --method post --uri "https://management.azure.com/subscriptions/$sub/resourceGroups/rg-mglab-deep-dive-07/providers/Microsoft.ApiManagement/service/$($out.apimName.value)/subscriptions/lab-caller/listSecrets?api-version=2024-05-01" --query primaryKey -o tsv
   Import-Module ./scripts/PurchaseGateway.psm1 -Force
   $token = Get-GatewayToken -TenantId $ids.tenantId -CallerClientId $ids.callerClientId -ApiClientId $ids.apiClientId
   Send-PurchaseEvent -GatewayUrl $out.gatewayUrl.value -SubscriptionKey $env:APIM_KEY -Token $token -PurchaseRequestId PR-9001 -Total 10   # expect 202
   ```
   If the first call is **401** even with a valid token, decode the token (without sharing it) and compare `aud` with the
   named value `api-client-id`, `iss` with the OpenID metadata, and `roles` with `Purchase.Submit`: that is the most
   likely mistake (v1 token vs v2 token, see README). The smoke call leaves one message in `all-events`: start the worker
   once for each subscription to drain it (Ctrl+C after it prints PR-9001), so the counts on camera start from zero.
5. **Dry run** the whole sequence once. The rate-limit take needs a quiet minute beforehand (the window is a sliding 60 s).

## Screens to capture (1920×1080, browser zoom 100 %)

| Scene id | File | What must be on screen |
|---|---|---|
| `policy-screen` | `screens/policy-portal.jpg` | Portal: APIM > APIs > Contoso purchasing events > POST /purchase-events > Inbound processing > Policy code editor with `validate-jwt`, `rate-limit`, `validate-content` visible. Named values `{{...}}` visible, not their values. |
| `calls-screen` | `screens/calls.jpg` | Take 1: terminal output of 5 calls: PR-1001 at 1476 -> 202; PR-1002 at 7380 -> 202; PR-1002 again with the same `-IdempotencyKey` -> 202 (same id echoed); the same call without `-Token` -> 401; `-RawBody '{"total":-1}'` -> 400. Take 2 (after the topic and worker captures): `1..25 \| % { Send-PurchaseEvent ... -PurchaseRequestId PR-2000 -Total 10 }` showing 202s then 429 with `RetryAfter`. |
| `topic-screen` | `screens/topic.jpg` | Portal: Service Bus > purchase-events > Subscriptions: all-events 2 active, finance-review 1 active (before starting the worker, after take 1). Then Service Bus Explorer > finance-review > Peek: Subject `purchase.high`, MessageId = the key printed in the terminal. |
| `worker-screen` | `screens/worker.jpg` | Windows Terminal, two panes, after take 1 and the topic capture: `dotnet run --project src/PurchaseEvents.Worker -- --namespace <fqdn> --topic purchase-events --subscription all-events` (left) and `... --subscription finance-review` (right). Left shows PR-1001 and PR-1002, right only PR-1002. Stop both with Ctrl+C. |

Order of recording: smoke test, **policy-screen**, **calls take 1**, **topic-screen**, **worker-screen**, **calls take 2**.

## Masking

Run `pipeline/mask.js` before the portal captures. Mask the tenant name and id, the subscription name and id, the APIM
and Service Bus host names, the app registration client ids. Never show `$env:APIM_KEY`, `$env:PURCHASE_CALLER_SECRET`,
`$token`, `/tmp/apim-outputs.json` or a decoded token. The gateway URL must be masked in the terminal capture.

## Tear-down

```bash
az group delete -n rg-mglab-deep-dive-07 --yes --no-wait
az apim deletedservice purge --location westeurope --service-name <apimName>     # soft-delete keeps the name for 48 h otherwise (Learn)
az ad app delete --id <callerClientId>; az ad app delete --id <apiClientId>
```
Clear `$env:APIM_KEY`, `$env:PURCHASE_CALLER_SECRET`. The client secret was valid one year: deleting the app removes it.
