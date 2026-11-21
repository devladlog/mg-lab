# Demo shot list — DEVLADLOG Deep Dive #4, Enterprise workflow automation

Code, test and Bicep scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs tenant** for everything on screen. Offline: 45 xUnit tests + 9 Pester tests pass, `bicep build`/`lint`
clean, `dotnet publish` produces the five functions.

## Lab environment

Recorded on the **lab Windows laptop** (host): Edge for SharePoint, Power Automate and Outlook on the web, the Teams
desktop or web client for the approvals, a terminal for `az` / `func`. No Hyper-V VM is needed.

**Azure** (no subscription yet: this is the full list to provision; one resource group `rg-mglab-approvals`,
West Europe; check `az functionapp list-flexconsumption-locations -o table` first)

| Resource | SKU | Estimated cost |
|---|---|---|
| Function app `func-appr-<token>` on a Flex Consumption plan | **FC1**, `dotnet-isolated` 10.0, 2,048 MB instances, always-ready **0** | per execution and GB-second; a recording session is a few hundred executions: cents |
| Storage account `stappr<token>` | Standard_LRS, shared keys off (code package + Durable task hub) | cents (queue polling transactions while the app is up) |
| Service Bus namespace `sb-appr-<token>` + queue `invoice-approvals` | **Basic** | per million operations: cents |
| Key Vault `kv-appr-<token>` | Standard, RBAC | per 10,000 operations: cents |
| User-assigned managed identity `id-appr-<token>` | — | free |
| Log Analytics + Application Insights | PerGB2018, 30-day retention | per GB ingested; a few MB: cents |

Total for one recording day: **about €1**. Check the [pricing calculator](https://azure.microsoft.com/pricing/calculator/) on the day and delete the resource group right after. Setting `durableAlwaysReady=1` (Learn's recommendation for Durable on Flex) adds an always-billed instance: don't for the lab.

**Microsoft 365 lab tenant**
- Users (lab, fictional): **Alex Demo** (accounts payable, uploads invoices), **Sam Demo** (manager), **Jordan Demo**
  (finance director), **Riley Demo** (escalation approver). All need Exchange and Teams (M365 E5 trial). Sam is also
  in episode 3; reuse the same accounts.
- SharePoint site `/sites/finance-lab` with the **Invoices Inbox** library from episode 1
  (`../01-enterprise-document-intelligence-ai-document-int/provision/New-InvoiceInbox.ps1`). Episode 1's Azure pipeline
  does **not** have to be deployed: the demo can mark invoices *Ready* by hand.
- Power Platform environment **`DEV`**; a solution `Invoice approvals` for the two flows.
- **Power Automate Premium** (or trial) for the flow owner: the HTTP trigger, the HTTP action and the Service Bus
  connector are premium. Approvers only respond, their Microsoft 365 licence is enough (they're members, not guests).

**Local tools on the laptop:** Azure CLI, Azure Functions Core Tools v4, .NET SDK 10, Bicep CLI, PowerShell 7.4+ with
`PnP.PowerShell` and the lab's PnP app registration (episode 1 created it).

## Setup (off camera)

1. **Tests first**
   ```bash
   cd series/deep-dive/episodes/04-enterprise-workflow-automation
   dotnet test tests/InvoiceApproval.Tests -m:1          # expect Passed: 45
   pwsh -NoProfile -c 'Invoke-Pester ./provision/ApprovalColumns.Tests.ps1'   # Tests Passed: 9
   ```
2. **Columns** on the episode 1 library
   ```powershell
   ./provision/Add-ApprovalColumns.ps1 -SiteUrl https://contoso.sharepoint.com/sites/finance-lab -ClientId <PnP app id> -WhatIf
   ./provision/Add-ApprovalColumns.ps1 -SiteUrl https://contoso.sharepoint.com/sites/finance-lab -ClientId <PnP app id>
   ```
   Run it twice: the second run shows `Exists` for all five. Edit the *All Documents* view: Name, Review status,
   Vendor, Total, **Approval status**, **Approval step**, **Decided by**, **Approval summary**.
3. **Azure** (deadline 5 minutes so the escalation happens on camera)
   ```bash
   az login                                                      # lab account, off camera
   az group create -n rg-mglab-approvals -l westeurope
   az deployment group create -g rg-mglab-approvals -f infra/main.bicep -p infra/main.bicepparam \
      -p managerEmail=<Sam UPN> financeEmail=<Jordan UPN> escalationEmail=<Riley UPN> stageTimeoutMinutes=5 \
      --query properties.outputs -o json > /tmp/approvals-outputs.json      # don't show on camera
   KV=$(jq -r .keyVaultName.value /tmp/approvals-outputs.json)
   az role assignment create --role "Key Vault Secrets Officer" --assignee $(az ad signed-in-user show --query id -o tsv) \
      --scope $(az keyvault show -n $KV --query id -o tsv)
   az keyvault secret set --vault-name $KV -n callback-signing-key --value "$(openssl rand -base64 48)" -o none
   cd src/InvoiceApproval && func azure functionapp publish $(jq -r .functionAppName.value /tmp/approvals-outputs.json) && cd ../..
   ```
   Role assignments can take a few minutes to apply.
4. **Flow 2, `Invoice approval relay`** (create it first, its URL goes into Key Vault). Environment variables
   `mgl_SiteUrl`, `mgl_InvoicesLibrary` as in episode 1.
   - Trigger **When an HTTP request is received**, *Who can trigger the flow*: **Anyone** (the URL's SAS signature is
     the credential and lives only in Key Vault). Request body JSON schema: copy `triggers.manual.inputs.schema` from
     `flow/approval-relay.definition.json`.
   - **Switch** on `kind`. Case `approval-request`: **SharePoint › Update file properties** (Id = `itemId`, Approval
     status = `status`, Approval step = `statusText`, Approval instance = `instanceId`) → **Approvals › Start and wait
     for an approval**, *Approve/Reject - First to respond*, Assigned to = `approverEmail`, title, details and item
     link as in the JSON → **HTTP** POST to `callbackUrl`, body `{"outcome": Outcome, "responder": first response's
     email, "comments": first response's comments}`, retry exponential ×3, Settings → **Secure inputs ON** → a
     **Send an email (V2)** to `approverEmail` with *Configure run after* = HTTP **has failed** ("your answer was not used").
     Case `outcome`: **Update file properties** (Approval status = `status`, Decided by = `decidedBy`, Approval summary
     = `statusText`, Approval step = empty) → **Send an email (V2)** to `submittedBy`.
     Default: **Terminate** (Failed).
   - Save, copy the trigger URL into Key Vault (never on screen), restart the app so it reads the secret:
     ```bash
     read -rs FLOW_URL && az keyvault secret set --vault-name $KV -n approval-flow-url --value "$FLOW_URL" -o none
     az functionapp restart -g rg-mglab-approvals -n <functionAppName>
     ```
   - *Optional, after the main take works:* switch the trigger to **Specific users in my tenant** with the
     `identityPrincipalId` output as allowed user, redeploy with `-p flowAudience=https://service.flow.microsoft.com/`,
     and check in run history that the function's call is accepted. Record the result in README either way.
5. **Flow 1, `Invoice ready to approval queue`**: trigger **SharePoint › When a file is created or modified
   (properties only)** on *Invoices Inbox*, Settings → **Trigger conditions**: paste the expression from
   `flow/invoice-ready-to-queue.definition.json`. **Compose** the message (keys exactly as in the JSON) →
   **Azure Service Bus › Send message** to `invoice-approvals`, content = the Compose output, Message ID = duplicate key.
   Connection: *Access Key*, connection string of the **`flow-send`** rule (Send only, one queue):
   `az servicebus queue authorization-rule keys list -g rg-mglab-approvals --namespace-name <ns> --queue-name invoice-approvals -n flow-send --query primaryConnectionString -o tsv` (off camera).
6. **Export** the solution, copy both workflow definitions over `flow/*.definition.json`, run
   `dotnet test tests/InvoiceApproval.Tests --filter ContractTests` and fix any difference before recording.
7. **Test data.** Two invoices in *Invoices Inbox* (upload episode 1's `samples/out/*.pdf` or any two PDFs as Alex),
   and if episode 1's pipeline isn't running, fill the columns by hand:
   `fabrikam|INV1001`, Fabrikam Ltd, INV1001, 1476, EUR and `fabrikam|INV1002`, Fabrikam Ltd, INV1002, 7380, EUR.
   Leave Approval status = *Not started*. For the take, set **Review status = Ready** on both.
8. **Dry run** once, then reset: Approval status back to *Not started* is only allowed after *Expired* (by design);
   for a clean take use new invoice numbers (`INV1003`, `INV1004`) instead.

## Screens to capture (1920×1080, browser zoom 100 %, SharePoint light theme)

| Scene id | File | What must be on screen |
|---|---|---|
| `waiting-screen` | `screens/library-waiting.jpg` | *Invoices Inbox*, about a minute after setting both invoices to Ready: INV1001 and INV1002 with Approval status **Waiting for approval** and Approval step **Manager approval: sam.demo@…** |
| `teams-screen` | `screens/teams-approval.jpg` | Teams → **Approvals** (or Outlook actionable message) signed in as **Sam**: the request "Invoice INV1002 from Fabrikam Ltd: 7380 EUR", details text with the deadline, *Open the invoice* link, Approve/Reject buttons. INV1001 already approved in the list. |
| `escalated-screen` | `screens/escalated.jpg` | After the 5-minute deadline: library row INV1002 with Approval step **Manager approval escalated to riley.demo@…**. Second capture for the same scene: Sam's inbox with "Invoice INV1002: your answer was not used" after he approves the old request. |
| `outcome-screen` | `screens/outcome.jpg` | Riley approves, then Jordan approves the finance stage: INV1002 **Approved**, Decided by **jordan.demo@…**, Approval summary "Manager: Approved by riley… (escalated); Finance: Approved by jordan…". Optional inset: Alex's result e-mail. |

## Masking

Run `pipeline/mask.js` before capturing. Mask the tenant name and the domain part of every e-mail address (keep the
`sam.demo` / `riley.demo` part readable), the function app, Service Bus and Key Vault names, the subscription name,
GUIDs in Power Automate run history. Never show `/tmp/approvals-outputs.json`, the flow trigger URL, a callback URL
(they contain signatures), the Service Bus connection string, or the Key Vault secret values.

## Tear-down

```bash
az group delete -n rg-mglab-approvals --yes --no-wait
az keyvault purge -n <keyVaultName> --location westeurope    # soft delete keeps the name for 7 days otherwise
```
Delete the `Invoice approvals` solution (both flows) in `DEV`. Keep the five library columns if episode 5 builds on
them; otherwise remove them in library settings. The lab users stay (shared).
