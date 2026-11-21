# Demo shot list — DEVLADLOG Deep Dive #1, Enterprise document intelligence

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | none |
| Tenant | Power Platform environment **`DEV`** (Dataverse: solution `Invoice intake`, environment variables incl. the Key Vault secret). **SharePoint**: a lab site `/sites/finance-lab` (create it as `labadmin` if missing; shown masked) with the *Invoices Inbox* library provisioned by `provision/New-InvoiceInbox.ps1` |
| Lab users | `labadmin` (the recording account): owner of the flow and the solution, SharePoint site owner, Owner on the subscription. **`alex.demo` (Alex Demo)** uploads the three invoices, so *Created by* / *Modified by* show a fictional name |
| Azure | Resource group **`rg-mglab-deep-dive-01`** in **West Europe** (check `az functionapp list-flexconsumption-locations`), deployed by `infra/main.bicep`: Document Intelligence **S0** (pay per page: three one-page invoices plus retries, cents; F0 also works, free), Function App on Flex Consumption (per execution, cents), Storage, Application Insights; plus the **Key Vault** (Azure RBAC, standard) for `invoice-api-key`, created in the same group so tear-down removes it. Estimated total under €1. Tear-down: delete the resource group, purge the vault |
| Licences / trials | **Power Automate Premium** for `labadmin` (the HTTP action is premium). Not in the shared lab list: use the Power Automate trial started in `DEV` if it includes premium connectors, otherwise start a Premium trial for labadmin. SharePoint and Dataverse connectors are standard. Register `Microsoft.PowerPlatform` in the subscription |
| Recording machine | The Windows lab laptop: browser (SharePoint, Power Automate, maker portal) with `pipeline/mask.js`; WSL (Ubuntu) bash with Azure CLI, Functions Core Tools v4, Python 3.11+, Bicep CLI; PowerShell 7.4+ with PnP.PowerShell on Windows for the library script |

Code and test scenes in `script.yaml` are already real (from this folder). The four `screen` scenes need the lab.
**Status: needs tenant** for everything on screen. Offline: 59 pytest + 13 Pester tests, `bicep build`/`lint` pass.

## Prerequisites
- **Azure** lab subscription with the budget alert; Owner (or Contributor + User Access Administrator) on the
  resource group, because the template creates role assignments. Register `Microsoft.PowerPlatform` in the
  subscription (needed for Key Vault-backed environment variables).
- **Microsoft 365** lab tenant: a SharePoint site (we use `/sites/finance-lab`, shown masked), a Power Platform
  environment **with Dataverse** (for the solution and the secret environment variable).
- **Licences:** the flow uses the **HTTP** action, a premium connector → the flow owner needs Power Automate Premium
  (a 90-day trial is fine for recording). SharePoint and Dataverse connectors are standard.
- **Cost:** Document Intelligence **S0** is pay per page (three one-page invoices plus retries: a few cents; check
  the [pricing page](https://azure.microsoft.com/pricing/details/ai-document-intelligence/)). Flex Consumption bills
  per execution; storage, App Insights and Key Vault are near zero for one session. Delete everything after recording.
  `F0` also works for one-page samples (free, first two pages only, 4 MB).
- **Local:** Azure CLI, Azure Functions Core Tools v4, Python 3.11+, PowerShell 7.4+ with `PnP.PowerShell`, Bicep CLI.

## Setup (off camera)

1. **Tests first** (screen-record this terminal only if a scene needs it):
   ```bash
   cd series/deep-dive/episodes/01-enterprise-document-intelligence-ai-document-int
   python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
   python -m pytest -q                     # expect 59 passed
   python samples/make_samples.py          # samples/out/fabrikam-{clean,over-limit,mismatch}.pdf
   ```
2. **Azure resources**
   ```bash
   az login                                                      # labadmin, off camera
   az functionapp list-flexconsumption-locations -o table        # westeurope must be listed, else change main.bicepparam
   az group create -n rg-mglab-deep-dive-01 -l westeurope
   az deployment group create -g rg-mglab-deep-dive-01 -f infra/main.bicep -p infra/main.bicepparam \
      --query properties.outputs -o json > /tmp/docintel-outputs.json      # don't show on camera
   cd src && func azure functionapp publish <functionAppName> && cd ..
   ```
   Role assignments can take a few minutes. Smoke test (off camera):
   ```bash
   export INVOICE_API_URL=$(jq -r .extractUrl.value /tmp/docintel-outputs.json)
   read -rs INVOICE_API_KEY && export INVOICE_API_KEY     # az functionapp keys list -g rg-mglab-deep-dive-01 -n <app> --query functionKeys.default -o tsv
   python samples/smoke.py samples/out/*.pdf
   ```
   Expect `fabrikam-clean.pdf  Ready` and the other two `Needs review` with reasons. A `503` right after deployment
   usually means the role assignment hasn't propagated yet: wait and retry. **Write down the actual confidence values**
   for the README (they are unknown until this run).
3. **Key Vault secret** for the function key: create a vault with the **Azure RBAC** permission model in
   `rg-mglab-deep-dive-01`, add secret `invoice-api-key` = the function key, and follow Learn's *Configure Azure Key Vault* steps
   (Key Vault Secrets User for the maker and for Dataverse).
4. **SharePoint library**
   ```powershell
   # once per tenant, if you don't have a PnP app registration yet:
   Register-PnPEntraIDAppForInteractiveLogin -ApplicationName "PnP lab" -Tenant contoso.onmicrosoft.com
   ./provision/New-InvoiceInbox.ps1 -SiteUrl https://contoso.sharepoint.com/sites/finance-lab -ClientId <app id> -WhatIf
   ./provision/New-InvoiceInbox.ps1 -SiteUrl https://contoso.sharepoint.com/sites/finance-lab -ClientId <app id>
   ```
   Run it twice: the second run must show `Exists` for all 13 columns. In the library, edit the **All Documents** view
   to show Name, Review status, Vendor, Invoice number, Total, Currency, Confidence.
5. **Flow** (in a solution, name `Invoice intake`):
   - Environment variables: `mgl_SiteUrl` (text), `mgl_InvoicesLibrary` (text, library id), `mgl_InvoiceApiUrl`
     (text, the `extractUrl` output), `mgl_InvoiceApiKey` (**Secret**, Azure Key Vault, `invoice-api-key`).
   - Trigger **SharePoint › When a file is created (properties only)** on *Invoices Inbox* (Split On stays on).
   - **Dataverse › Perform an unbound action** `RetrieveEnvironmentVariableSecretValue`, name `mgl_InvoiceApiKey`,
     rename to `Get API key`, Settings → **Secure inputs and Secure outputs ON**.
   - **SharePoint › Get file content** (File identifier from the trigger).
   - **HTTP** POST to `mgl_InvoiceApiUrl`, headers `x-functions-key` = the secret value, `X-File-Name` = *File name
     with extension*, body = *File content*. Rename `Extract invoice`. Settings → Secure inputs ON; Retry policy
     **Exponential, count 2, interval PT30S**.
   - **SharePoint › Get files (properties only)**, filter `InvDedupKey eq '<fields.InvDedupKey>' and ID ne <ID>`,
     top 1. Rename `Find duplicates`.
   - **Compose** `Final status` and **Update file properties** exactly as in `flow/definition.json`.
   - Parallel branch after `Extract invoice` with *Configure run after* = has failed / has timed out →
     **Update file properties**: Review status `Needs review`, reasons `Extraction failed…`.
   - Save, then **export the solution** and copy the workflow definition over `flow/definition.json`; re-run
     `python -m pytest tests/test_contract.py` and fix any difference before recording.

## Screens to capture (1920×1080, browser zoom 100 %, dark mode off for SharePoint)

| Scene id | File | What must be on screen |
|---|---|---|
| `upload` | `screens/library-upload.jpg` | SharePoint *Invoices Inbox*, All Documents view, right after uploading the three `samples/out/*.pdf`: three rows, Review status **Pending**, all other invoice columns empty. |
| `run` | `screens/flow-run.jpg` | Power Automate run history of `Invoice intake` → one successful run opened (the `fabrikam-mismatch.pdf` run): all actions green, `Get API key` showing *Content not shown due to security configuration*. |
| `results` | `screens/library-results.jpg` | The library after the three runs: `fabrikam-clean.pdf` **Ready** with Vendor, Invoice number, Total 1476, EUR, Confidence; the other two **Needs review**. |
| `reasons` | `screens/review-reasons.jpg` | Details pane (or edit form) of `fabrikam-mismatch.pdf`: Review reasons = *Subtotal + tax (1467.00) does not match total (1476.00).* |

The trigger polls: allow 1–5 minutes after the upload before capturing `results`. If a file shows `Needs review`
with a *Low confidence* reason instead of the expected one, keep it and adjust the narration to what is on screen —
don't edit values by hand.

## Masking
- Run `pipeline/mask.js` in the browser before each capture. Mask: tenant name in URLs and the suite bar, user
  names/avatars (uploads as *Alex Demo*; labadmin's name masked), environment name/ID in Power Automate, function app host name in the
  HTTP action, subscription/resource IDs in any Azure portal view.
- Never show the function key, the Key Vault secret value, `/tmp/docintel-outputs.json`, or the `func` publish output
  (it prints the host name).

## Tear-down
```bash
az group delete -n rg-mglab-deep-dive-01 --yes --no-wait
```
Then: turn off and delete the `Invoice intake` flow and its solution (with the environment variables), delete the
Key Vault (and purge it if soft delete is on), delete the *Invoices Inbox* library, and remove the PnP app
registration if it was created only for this episode.
