# Demo shot list — DEVLADLOG Azure #10, Azure AI & Cognitive Services

## Lab environment

No VMs. Screens are recorded on the **recording laptop** (Windows): a bash terminal (Git Bash or WSL) with the **Azure CLI**
signed in as `labadmin` (`az login`), the **.NET 10 SDK**, `jq` and `curl`; and a **browser on the lab tenant** (Azure portal).
The app signs in through `DefaultAzureCredential`, which uses the Azure CLI session on the laptop.

Azure resources, all in resource group **`rg-mglab-azure-10`** (West Europe), tags `workload=contoso-support-triage`, `environment=lab`:

| Resource | SKU / setting | Cost |
|---|---|---|
| Azure AI Language `lang-triage-xxxxx` (kind `TextAnalytics`) | **F0 (free)**, custom subdomain = name, key access disabled, public network enabled | **€0** (5,000 text records a month; a run is 21) |
| Role assignment on the account | Cognitive Services Language Reader to `labadmin` (second deploy) | €0 |
| **Total** | | **€0** |

**Preconditions**
- Only **one F0 Language resource per subscription** (Learn). `deploy.sh` stops with a message if another exists. If a previous
  episode or test left a soft-deleted one, purge it: `az cognitiveservices account list-deleted -o table`, then
  `az cognitiveservices account purge ...`.
- `labadmin` must be able to create role assignments (Owner on the subscription is enough) and, for the purge, have a role that
  allows it at **subscription** level (Learn: Contributor at subscription level; Owner includes it).
- The Language service must be available in West Europe for F0 (expected; not checked). If the region is refused, use another
  and change the location argument.

**Tear-down:** `infra/teardown.sh rg-mglab-azure-10` (deletes the group, then purges the account, then removes `~/.contoso-ai`).
Check `az group exists --name rg-mglab-azure-10` → `false` and `az cognitiveservices account list-deleted -o table` shows nothing for this account.

## What the builder ran, and what is still unverified

Run in the builder's container (no Azure, no `az`): `dotnet test` (22 passed: the real SDK against a stand-in HTTP handler),
`pytest tests/infra` (17 passed), `bicep lint`, `bash -n` on every script, the app's `--dry-run` and its no-endpoint exit code.
**Never run against Azure** (marked *needs tenant*): the deployment, the role assignment, every call to the real Language service,
`rest-check.sh`, `teardown.sh`. The **expected** results below are guesses from the docs, not observations: record what
comes back and keep corrected files.

## Setup (needs tenant)

```bash
cd series/azure/episodes/10-azure-ai-cognitive-services
dotnet test tests/SupportTriage.Tests -m:1 && python3 -m pytest tests/infra -q       # 22 + 17 passed first
az login                                                                              # as labadmin
az account set --subscription "<lab subscription>"
```

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/deploy.jpg` — scene `deploy_screen` (needs tenant)
`infra/deploy.sh rg-mglab-azure-10 westeurope` (≈ 1–2 min): the what-if table (one `Create`), the outputs (`accountName`, `endpoint`).
Portal: the Language resource **Overview** (Pricing tier **Free (F0)**, Location West Europe, Endpoint
`https://lang-triage-….cognitiveservices.azure.com/`) and **Access control (IAM) > Role assignments** with no role for `labadmin` on this
resource (inherited Owner from the subscription is expected to show; point out that none is a *data* role). Mask: subscription ID,
the account name and endpoint host.

### 2. `screens/denied.jpg` — scene `denied_screen` (needs tenant)
`infra/run.sh` right after the first deployment: **expected** a failure from the service (HTTP 401 or 403 with an error code), the
app's hint about the role, exit code 3 (`echo $?`). Record exactly what comes back, including the status. If it somehow succeeds
(for example a role inherited from the subscription already allows the data action) that is a finding: say so, and in the next
screen show the role from the resource-level assignment instead. Mask: endpoint host if shown.

### 3. `screens/run.jpg` — scene `run_screen` (needs tenant)
`infra/deploy.sh rg-mglab-azure-10 westeurope --role`, then wait (Learn: up to 5 minutes; retry `infra/run.sh` until it works and
note how long it took), then a clean `infra/run.sh`: seven JSON lines and, on standard error,
`text records (billed this run): 21 = language 7, pii 7, sentiment 7; that is 0.4 % of the free 5,000 a month, 238 such runs per month`.
**Expected** (not observed): T-1004 (card) → `security-review` with `CreditCardNumber` in `piiCategories`; T-1006 (IBAN) → `security-review`;
T-1001 and T-1007 → `escalate`; T-1002/T-1005/T-1006 get language codes `pt`/`fr`/`es`. The real models may differ (a missed
category is itself the finding, and README's PII-category gotcha applies). Read the routes aloud as they are, and show the redacted
text of T-1004. Mask: endpoint host.

### 4. `screens/rest.jpg` — scene `rest_screen` (needs tenant)
`infra/rest-check.sh`: first call (bearer token) → `HTTP 200` with `detectedLanguage` Portuguese (`pt`); second call (made-up key
header) → an HTTP error (**expected** 401 or 403; record the exact status and message). Mask: endpoint host.

## Tear-down (needs tenant, last thing on the day)
`infra/teardown.sh rg-mglab-azure-10`; `az group exists --name rg-mglab-azure-10` → `false`; confirm the purge
(`az cognitiveservices account list-deleted -o table`).
