# Demo shot list — DEVLADLOG AI #17 (Azure AI services as a platform)

Everything in `src/` and `infra/` is tested locally (85 pytest tests, Bicep build + lint) with the real azure-core pipeline and
the real Document Intelligence SDK against a stand-in service. The five `screen` scenes are recorded for real: the **portal**,
the **real Azure services** called by our code, and our scanner run on this repo. No M365 tenant objects are used. A 403, a
failed probe or a warning in the audit is part of the episode, not a retake.

## Lab environment

| Item | Value |
|---|---|
| Subscription | Lab pay-as-you-go subscription (Owner), €30/month budget alert already set |
| Resource group | `rg-mglab-ai-17`, region **West Europe** |
| Foundry resource | `mglab-ai17-<suffix>`, kind `AIServices` (portal: Foundry), SKU **S0**, custom subdomain, keys off, system-assigned identity |
| Log Analytics | `mglab-ai17-<suffix>-log`, PerGB2018, 30 days retention; diagnostic setting `to-log-analytics` (Audit, RequestResponse, AllMetrics) |
| Roles | `labadmin` is subscription Owner (no data-plane access by itself). Bicep step 2 adds **Cognitive Services User** on the resource for `labadmin` |
| Recording machine | Lab Windows laptop: Windows Terminal (WSL or PowerShell, Python 3.10+, `jq`), Azure CLI, Bicep CLI; browser on the lab tenant for the Azure portal. No VMs, no containers |
| Licences | None beyond the Azure subscription |

**Estimated cost for the recording window:** I did not check prices (no subscription access) so none are embedded. What Learn says:
a Foundry Tools resource is billed per transaction (Learn: "Pricing tiers and billing"); the calls here are a few dozen tiny
requests (a short sentence each, no document analysed, no model deployed). Log Analytics bills per GB ingested (PerGB2018); a
few dozen requests are kilobytes. Expect cents. Delete the resource group the same day.

**Needs verification before recording (I could not check these without a subscription):**
1. **The deployment itself.** `bicep build` and `lint` pass; I have not deployed. Check that `Microsoft.CognitiveServices/accounts@2025-06-01`
   accepts kind `AIServices` with `customSubDomainName` + `disableLocalAuth` and no project, and that the account name (`mglab-ai17-xxxxxx`)
   is accepted as a subdomain.
2. **Content Safety in West Europe.** Learn's overview says the resource must be in a supported region and points to a region page I
   did not open. If the Content Safety probe returns 404 or an availability error, that is the finding: say so on camera, or redeploy
   to a region the page lists (change `location`; Translator and the other probes are not region-bound the same way).
3. **Owner really gets 403** on all four probes. Learn says Owner/Contributor have no development permissions. The *error code and
   whether a service answers 401 instead of 403* are unknown until recorded; the narration has TODOs.
4. **Cognitive Services User is enough** for `probe` (data actions `Microsoft.CognitiveServices/*`), for `usage` (it lists
   `Microsoft.Insights/metrics/read`) and for the ARM reads of `audit`. Reading role assignments needs Reader/Owner; `labadmin` is Owner.
5. **Translator with an Entra token on the custom-domain path and no region header** (`/translator/text/v3.0/translate?api-version=3.0&to=pt`).
   Learn's Translator Entra page shows exactly this form; I could not run it.
6. **Language `analyze-text` api-version `2023-04-01`** on an AIServices resource (the same version episode 12 used on a Language resource).
7. **Document Intelligence resource details** (`GET <endpoint>/documentintelligence/info?api-version=2024-11-30`, issued by the SDK) with
   Cognitive Services User. The test fixture uses an invented limit.
8. **Metrics.** `usage` asks for `TotalCalls, TotalErrors, ClientErrors, ServerErrors, Latency` split by `ApiName`, with api-version
   `2019-07-01`. I do not know the `ApiName` values the service reports (the table in the tests is invented), how long metrics take to
   appear, or whether calls refused with 403 are counted as `ClientErrors`. Run a probe, wait, run `usage`; if the table is empty say
   "metrics arrive with a delay" and run again. The billable-unit lines (`ProcessedTextRecords`, `TextCharactersTranslated`,
   `ContentSafetyTextAnalyzeRequestCount`) only print when non-zero.
9. **Role propagation** takes up to five minutes (Learn). Do step 2 of the setup before you start filming the portal screen, or cut.
10. **`AllMetrics` as the metric category name** in the diagnostic setting. Learn's supported-metrics table marks the metrics as
    exportable; the portal's diagnostic-setting blade will show what is ticked.

## Setup (off camera)

```bash
cd series/ai/episodes/17-azure-ai-services-platform
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest tests -q                                        # expect 85 passed
az login                                                         # labadmin, off camera
az group create -n rg-mglab-ai-17 -l westeurope
# step 1: no data-plane role (this is what the "forbidden" screen needs)
az deployment group create -g rg-mglab-ai-17 -f infra/main.bicep -p infra/main.bicepparam \
   --query properties.outputs -o json > /tmp/ai17-outputs.json    # don't show this file on camera
export AIPLATFORM_ENDPOINT=$(jq -r .endpoint.value /tmp/ai17-outputs.json)
export AIPLATFORM_RESOURCE_ID=$(jq -r .resourceId.value /tmp/ai17-outputs.json)
export PYTHONPATH=src
```

Terminal: dark theme, font ≥ 16 pt, 1920×1080, short prompt (no user or host name). Do not `echo` the two variables.

## Screens to capture (record in this order)

| Scene id | File | Needs | What must be on screen |
|---|---|---|---|
| `resource-screen` | `screens/resource.jpg` | portal, Azure | Azure portal → the Foundry resource: Overview (type, region West Europe, endpoint masked), Keys and Endpoint showing local authentication disabled, Diagnostic settings showing `to-log-analytics` (Audit, RequestResponse, AllMetrics) → the workspace. Mask subscription, tenant, user, name suffix. |
| `forbidden-screen` | `screens/forbidden.jpg` | Azure (step 1 deployment) | `python -m aiplatform probe ; echo exit=$?` as `labadmin` (Owner, no data role): four rows, HTTP 403 `forbidden`, the hint lines, `0 of 4 services answered`, `exit=1`. Take this **before** step 2. |
| `probe-screen` | `screens/probe.jpg` | Azure (after role) | Step 2 below, wait ~5 minutes, then the same command: four rows `ok` with the answers (language, translation, severities, custom model count of limit), ms per call, `4 of 4 services answered with the same identity.` |
| `operate-screen` | `screens/operate.jpg` | Azure | `python -m aiplatform audit ; echo exit=$?` (PASS lines, one WARN for the open public network, exit 0), then `python -m aiplatform usage --minutes 30` (one row per ApiName; billable-unit lines). Run `probe` two or three more times first so there is something to see; wait for metrics. |
| `lifecycle-screen` | `screens/lifecycle.jpg` | local only (real run on this repo) | `python -m aiplatform lifecycle ../ --no-lines ; echo exit=$?` then once more without `--no-lines` for the file:line list. Expected from the current repo: Image Analysis (episode 13) and Language sentiment and key phrases (episode 12), exit 0. |

Step 2 (between `forbidden-screen` and `probe-screen`, can be shown or cut):

```bash
az deployment group create -g rg-mglab-ai-17 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv)
```

After recording, update the TODO comments in `script.yaml` with what the services returned (the 403 error code, the language and
translation, the severities, the metrics delay, the days left on the day). Keep `build/` until the episode is published, then delete it.

## Masking

- Mask the subscription ID, tenant, signed-in user and the resource-name suffix (`pipeline/mask.js`). The endpoint contains the
  suffix: mask it wherever it appears (portal Overview, `az` output). Don't show `/tmp/ai17-outputs.json`.
- The probe texts are fixed and fictional (a Portuguese sentence about a VPN, a printer out of toner). Nothing real is typed or pasted.
- Don't show Cost Management or the pricing page with real amounts.

## Tear-down

```bash
az group delete -n rg-mglab-ai-17 --yes
az cognitiveservices account purge -g rg-mglab-ai-17 -n <accountName> -l westeurope   # releases the soft-deleted account name
rm -rf /tmp/ai17-outputs.json build; deactivate; rm -rf .venv
```

Deleting the resource group removes the account, the workspace and the diagnostic setting. Purge the account so the soft-deleted
name is released (same as episode 12). If the Log Analytics workspace name is ever reused, a soft-deleted workspace may block it;
I did not verify the retention behaviour. Confirm in Cost Management the next day that nothing in `rg-mglab-ai-17` is still billing.
