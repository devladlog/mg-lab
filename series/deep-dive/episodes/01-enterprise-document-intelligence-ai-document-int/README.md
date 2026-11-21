# DEVLADLOG Deep Dive #1 — Enterprise document intelligence (Document Intelligence + Power Automate + SharePoint)

Invoices land in a SharePoint library. A minute or two later every file has its vendor, number, dates, totals and
currency filled in, and a **review status**: `Ready`, or `Needs review` with the exact reason (low confidence on a
required field, totals that don't add up, above the approval limit, ambiguous currency, possible duplicate…).

```
SharePoint "Invoices Inbox" ──► Power Automate flow ──(file bytes, function key from Key Vault)──► Azure Function (Python, Flex Consumption)
        ▲                          │                                                             │  managed identity, no keys
        └──── Update file properties ◄──── status + reasons + 13 columns ◄─── routing rules ◄────┴──► Document Intelligence, prebuilt-invoice
```

- **The model extracts, the policy decides.** Document Intelligence returns values and a confidence per field;
  `rules.py` turns that into a decision with reasons. Thresholds (`MIN_CONFIDENCE`, `APPROVAL_LIMIT`,
  `ALLOWED_CURRENCIES`) are app settings, not code.
- **Keyless.** The Document Intelligence account has `disableLocalAuth: true`; the function's user-assigned identity
  has **Cognitive Services User** on that account only. The function's storage also uses the identity.
- **One contract.** [`src/docintel/columns.json`](src/docintel/columns.json) defines the 13 library columns. The PnP
  script creates them from it, the function returns exactly those keys, and tests check the flow only reads and
  writes columns that exist.

| Path | What it is |
|---|---|
| [`src/function_app.py`](src/function_app.py) | HTTP function `POST /api/invoices/extract` (Python v2 model, `AuthLevel.FUNCTION`): accepts raw bytes or the flow's `{"$content-type","$content"}` envelope, sniffs the file type, size limit, maps service errors (429/5xx → 503 so the flow retries) |
| [`src/docintel/extract.py`](src/docintel/extract.py) | `DocumentIntelligenceClient` with `DefaultAzureCredential`, `prebuilt-invoice`, API `2024-11-30` |
| [`src/docintel/mapping.py`](src/docintel/mapping.py) | AnalyzeResult JSON → columns: typed values, per-field confidence, currency code (only unambiguous symbols), duplicate key |
| [`src/docintel/rules.py`](src/docintel/rules.py) | `Policy` + `decide()`: Ready / Needs review / Rejected, every reason written down |
| [`src/docintel/columns.json`](src/docintel/columns.json) | The contract (library name, 13 columns, status choices) |
| [`infra/main.bicep`](infra/main.bicep) | Document Intelligence (keys off, custom subdomain), Flex Consumption app (Python 3.11), storage + App Insights via managed identity, 5 role assignments |
| [`provision/InvoiceInbox.psm1`](provision/InvoiceInbox.psm1), [`New-InvoiceInbox.ps1`](provision/New-InvoiceInbox.ps1) | PnP PowerShell: create the library, versioning, columns from the contract (CAML), idempotent, `-WhatIf` |
| [`flow/definition.json`](flow/definition.json) | Reference definition of the cloud flow (trigger, Key Vault secret, HTTP call, duplicate check, update, failure branch) |
| [`samples/make_samples.py`](samples/make_samples.py) | Writes three fictional invoice PDFs (clean, over the limit, totals mismatch) for the demo |
| [`samples/smoke.py`](samples/smoke.py) | Posts PDFs to the deployed function and prints the decision per file |
| [`tests/`](tests) | 59 pytest tests (incl. compiled-ARM checks); [`provision/InvoiceInbox.Tests.ps1`](provision/InvoiceInbox.Tests.ps1): 13 Pester tests |

## Test locally (no Azure, no tenant)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q                                   # 59 passed (about 14 s)
pwsh -NoProfile -c 'Invoke-Pester ./provision/InvoiceInbox.Tests.ps1'      # Tests Passed: 13
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep   # no warnings
python samples/make_samples.py                        # samples/out/*.pdf
```

How the tests work without Azure: [`tests/stub_service.py`](tests/stub_service.py) is a tiny local HTTP server that
speaks the Document Intelligence long-running analyze pattern (`POST …/documentModels/prebuilt-invoice:analyze` →
`202` + `Operation-Location` → `running` → `succeeded`). The **real** `azure-ai-documentintelligence` client talks to
it, so the tests check the actual request (`base64Source`, `api-version=2024-11-30`, `locale`), polling, error and
retry behaviour. `test_samples.py` runs the whole chain: `smoke.py` → local HTTP host → `function_app.handle` → SDK →
stub. The Pester tests mock the PnP cmdlets.

Tested with Python 3.13, `azure-ai-documentintelligence 1.0.2`, `azure-core 1.41.0`, `azure-functions 2.4.0`,
PowerShell 7.6 + Pester 6.2.0, Bicep CLI 0.49.2.

## Deploy (needs an Azure subscription and a Microsoft 365 lab tenant)

See [`demo.md`](demo.md) for the full recording runbook. In short:

```bash
az group create -n rg-mglab-docintel -l westeurope        # check: az functionapp list-flexconsumption-locations
az deployment group create -g rg-mglab-docintel -f infra/main.bicep -p infra/main.bicepparam
cd src && func azure functionapp publish <functionAppName> && cd ..
pwsh ./provision/New-InvoiceInbox.ps1 -SiteUrl https://contoso.sharepoint.com/sites/finance-lab -ClientId <your PnP app id>
# then build the flow (demo.md, step 5) and upload samples/out/*.pdf to the library
```

## What we learned / gotchas

- **Use "When a file is created (properties only)".** "When a file is created or modified (properties only)" fires
  each time file properties change, so the flow's own *Update file properties* would trigger it again.
  `test_trigger_is_created_only…` keeps it that way.
- **Retries multiply.** In `test_sdk_already_retries_a_persistent_429_three_times`, one SDK call to a service that
  keeps answering 429 became **four** HTTP requests (azure-core 1.41 defaults). The HTTP action's *Default* retry
  policy sends up to four more retries for 408/429/5xx on top (Logic Apps docs, same workflow engine), so the flow
  sets an explicit exponential policy with `count: 2`.
- **azure-core retries any 4xx/5xx that carries `Retry-After`.** Our first stub sent `Retry-After` on a 400 and the
  SDK retried it three times. Real services send it on throttling; the stub now does the same.
- **Choice columns are written through `item/<Column>/Value`** in *Update file properties*; a contract test checks no
  action writes `item/InvStatus` directly and that every literal status is one of the choices.
- **A function key in a flow is a secret.** Learn's guidance: keep it in an environment variable of type *Secret*
  backed by Azure Key Vault (read with the Dataverse unbound action `RetrieveEnvironmentVariableSecretValue`) and turn
  on **Secure inputs/outputs** so it never appears in run history. The HTTP action is a **premium** connector.
- **Microsoft Entra auth needs a custom subdomain** on the Cognitive Services account; regional endpoints don't
  support it. The Contributor role can't call the data plane when keys are disabled: you need **Cognitive Services
  User** (also for Document Intelligence Studio).
- **Free tier (F0) reads only the first two pages** of a PDF and accepts files up to 4 MB (S0: up to 2,000 pages and
  500 MB). The function refuses non-PDF/image bytes and anything above `MAX_UPLOAD_MB` *before* calling the service.
- **`$` alone is not a currency.** The model returns a currency symbol and, when it can, a code. `mapping.py` maps only
  unambiguous symbols (€, £); a bare `$` goes to review.
- **The SharePoint trigger polls.** Learn: the run "may occur within minutes" and can gather more than one change, so
  the trigger uses *Split On* (one run per file) and the demo waits a couple of minutes.
- **Not verified in the lab yet (needs tenant):** `flow/definition.json` was written by hand from the designer steps and
  is checked only by tests for internal consistency (actions, references, columns, secure data). Build the flow in
  the designer as in `demo.md`, then replace the file with the exported definition. The real confidence values the
  prebuilt model returns for the sample PDFs are unknown until the recording.

## References

- [Document Intelligence invoice model (v4.0)](https://learn.microsoft.com/azure/ai-services/document-intelligence/prebuilt/invoice?view=doc-intel-4.0.0) · [input requirements and limits](https://learn.microsoft.com/azure/ai-services/document-intelligence/prebuilt/invoice?view=doc-intel-4.0.0#input-requirements)
- [Invoice model fields (VendorName, InvoiceId, InvoiceTotal, …)](https://learn.microsoft.com/ai-builder/prebuilt-invoice-processing#model-output)
- [SDK quickstart, Python, v4.0](https://learn.microsoft.com/azure/ai-services/document-intelligence/quickstarts/get-started-sdks-rest-api?view=doc-intel-4.0.0&pivots=programming-language-python)
- [Interpret and improve accuracy and confidence scores](https://learn.microsoft.com/azure/ai-services/document-intelligence/concept/accuracy-confidence?view=doc-intel-4.0.0) · [Transparency note: thresholds and human review](https://learn.microsoft.com/azure/foundry/responsible-ai/document-intelligence/transparency-note#evaluation-of-document-intelligence)
- [Document Intelligence Studio: Cognitive Services User when keys are disabled](https://learn.microsoft.com/azure/ai-services/document-intelligence/quickstarts/get-started-studio?view=doc-intel-4.0.0#prerequisites)
- [Authenticate with Microsoft Entra ID (custom subdomain required)](https://learn.microsoft.com/azure/ai-services/authentication#authenticate-with-microsoft-entra-id) · [Built-in roles: Cognitive Services User](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles#ai--machine-learning)
- [Flex Consumption with Bicep and managed identity](https://learn.microsoft.com/azure/azure-functions/functions-create-first-function-bicep?pivots=programming-language-python) · [Flex Consumption regions](https://learn.microsoft.com/azure/azure-functions/flex-consumption-how-to#view-currently-supported-regions)
- [SharePoint connector triggers and actions, known limitations](https://learn.microsoft.com/sharepoint/dev/business-apps/power-automate/sharepoint-connector-actions-triggers)
- [HTTP connector is premium (SharePoint guidance)](https://learn.microsoft.com/sharepoint/dev/business-apps/power-automate/guidance/migrate-from-classic-workflows-to-power-automate-flows#pain-points-in-moving-between-classic-workflows-in-sharepoint-and-power-automate-flows)
- [Retry policies (Default: up to 4 retries)](https://learn.microsoft.com/azure/logic-apps/error-exception-handling#retry-policies) · [Content types and `$content`](https://learn.microsoft.com/azure/logic-apps/logic-apps-content-type)
- [Environment variables for Azure Key Vault secrets](https://learn.microsoft.com/power-apps/maker/data-platform/environmentvariables-azure-key-vault-secrets) · [Secure data in cloud flows](https://learn.microsoft.com/power-automate/guidance/coding-guidelines/use-secure-inputs-outputs-triggers)
- [PnP PowerShell needs PowerShell 7.4+ and your own app registration](https://learn.microsoft.com/sharepoint/dev/transform/modernize-userinterface-site-pages-powershell#install-or-update-pnp-powershell)
- Blog: [Enterprise Document Intelligence — Complete Guide](https://www.devladlog.com/articles/deep-dive/2026-05-18-enterprise-document-intelligence-azure-ai-power-automate-sharepoint/)
