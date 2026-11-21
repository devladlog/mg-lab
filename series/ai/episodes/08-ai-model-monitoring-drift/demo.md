# Demo shot list — DEVLADLOG AI #8 (model monitoring and drift)

Everything in `src/` and `infra/` is tested locally (36 pytest tests, Bicep build + lint). The four `screen` scenes
**need the lab subscription**: real model calls, real telemetry in Application Insights / Log Analytics, a real alert.
No tenant (M365) objects are used.

## Lab environment

| Item | Value |
|---|---|
| Subscription | Lab pay-as-you-go subscription (Owner) — €30/month budget alert already set |
| Resource group | `rg-mglab-ai-08`, region **Sweden Central** |
| Log Analytics workspace | `mglab-mon-law-…`, PerGB2018, 30-day retention |
| Application Insights | `mglab-mon-appi-…`, workspace-based, **local auth disabled** (Entra-only ingestion) |
| Azure OpenAI | `mglab-mon-aoai-…`, kind `OpenAI`, S0, custom subdomain, keys off; deployment `chat` = **gpt-5-mini 2025-08-07, DataZoneStandard**, capacity 20, NoAutoUpgrade; diagnostic setting: AzureOpenAIRequestUsage + AllMetrics → workspace |
| Alert rule | `mglab-mon-drift-alert` (`scheduledQueryRules`, severity 2, every 5 min over 15 min, query on `drift_report` records with `hr_max_psi >= 0.2`), no action group (the fired alert is shown in the portal) |
| Roles (Bicep) | `labadmin`: Cognitive Services OpenAI User (model), Monitoring Metrics Publisher (App Insights ingestion), Log Analytics Reader (workspace queries) |
| Recording machine | Lab Windows laptop: Windows Terminal (WSL or PowerShell, Python 3.10+), Azure CLI, Bicep CLI; browser for the Azure portal |

**Estimated cost for the recording window:** one full run is 2 windows × (40 questions + 16 golden) = 112 triage
calls to gpt-5-mini, a few hundred input tokens plus reasoning/output tokens each — on the order of 100K tokens per
run; with a warm-up run and two takes, expected well under €1 at the published gpt-5-mini Data Zone rates (check the
pricing page in EUR). Log Analytics ingestion: well under 10 MB. The log search alert rule is billed per rule per
month (pro-rated; see Azure Monitor pricing) — delete the resource group the same day.

**Needs verification before recording:**
- gpt-5-mini 2025-08-07 DataZoneStandard quota in Sweden Central (fallback `chatSku='GlobalStandard'`; say so in the
  README note if used, because episode 7's MOD-03 control would flag it).
- That `response.model` from the deployment returns a versioned name (e.g. `gpt-5-mini-2025-08-07`); the model-version
  line shows whatever the service returns.
- After the first run: `AppDependencies | take 5` in the workspace shows the OpenAI spans from the distro **without
  message content** (we pass `enable_sensitive_data=False`). If content appears, stop and fix before filming.

## Setup (off camera)

```bash
cd series/ai/episodes/08-ai-model-monitoring-drift
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest tests -q                                       # expect 36 passed
az login                                                        # labadmin, off camera
az group create -n rg-mglab-ai-08 -l swedencentral
az deployment group create -g rg-mglab-ai-08 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) \
   --query properties.outputs -o json > /tmp/ai08-outputs.json   # don't show this file on camera
export AOAI=$(jq -r .aoaiEndpoint.value /tmp/ai08-outputs.json)
export APPINSIGHTS=$(jq -r .appInsightsConnectionString.value /tmp/ai08-outputs.json)
export WS=$(jq -r .workspaceId.value /tmp/ai08-outputs.json)
```

Wait ~5 minutes for the role assignments. Warm-up (off camera) with a throwaway window label so it doesn't mix with
the takes: `PYTHONPATH=src python -m hrmon.traffic --data data/golden.jsonl --window warmup --aoai-endpoint $AOAI
--appinsights "$APPINSIGHTS"` must print `16 triaged, 0 failed`. `401/403` from the model = role not propagated;
exporter errors mentioning 400/403 = credential/Monitoring Metrics Publisher (Learn troubleshooting).

Use **fresh window labels per take** if you re-record (e.g. `baseline2` / `current2`), otherwise the monitor reads
both takes together.

Terminal: dark theme, font ≥ 16 pt, 1920×1080, short prompt (no user/host name). The drift table needs ~110 columns.

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `traffic` | `screens/traffic.jpg` | `PYTHONPATH=src python -m hrmon.traffic --data data/baseline.jsonl --window baseline --aoai-endpoint $AOAI --appinsights "$APPINSIGHTS" --golden data/golden.jsonl`, then the same with `data/current.jsonl --window current`. Both "40 triaged, 0 failed" lines and both golden accuracy lines. Each run takes about a minute; cut the wait. |
| `kql` | `screens/kql.jpg` | Wait 3–5 minutes. Portal → workspace → **Logs**: `AppTraces \| where Message == "triage" \| summarize n=count() by window=tostring(Properties["hr_window"]), lang=tostring(Properties["hr_lang"]) \| order by window` — table (optionally chart) with en/pt counts per window. |
| `monitor-run` | `screens/monitor.jpg` | `PYTHONPATH=src python -m hrmon.monitor --workspace-id $WS --baseline baseline --current current --appinsights "$APPINSIGHTS" ; echo exit=$?` — full drift table, model versions, golden accuracy, ALERT line, exit code. If the triage counts are below 40/40, wait a minute and re-run (ingestion). |
| `alert` | `screens/alert.jpg` | 5–20 minutes later: portal → **Monitor → Alerts**, filter `rg-mglab-ai-08`, open the fired `mglab-mon-drift-alert`: condition (query, Count > 0), fired time. Only fires if the monitor reported max PSI ≥ 0.2. |

After recording, update the TODO comments in `script.yaml` with what really happened (golden accuracies, which
features were significant, exit code, how long the alert took). **Don't edit the datasets or thresholds to force
drift on camera**; if the real model's outputs didn't drift, the honest version says so and the alert scene is
replaced by the portal view of the rule (Monitor → Alerts → Alert rules) with the narration adjusted.

## Masking

- Mask the subscription ID, tenant, signed-in user and resource name suffixes in the portal (`pipeline/mask.js`).
- Don't `echo` `$AOAI`, `$APPINSIGHTS` or `$WS`; don't show `/tmp/ai08-outputs.json`. The connection string isn't a
  secret with local auth off, but it identifies the resource.
- The questions in `data/` are fictional; no personal data reaches telemetry by design (only features and answers).

## Tear-down

```bash
az group delete -n rg-mglab-ai-08 --yes
az cognitiveservices account purge -g rg-mglab-ai-08 -n $(jq -r .aoaiName.value /tmp/ai08-outputs.json) -l swedencentral
rm -f /tmp/ai08-outputs.json records*.jsonl; deactivate; rm -rf .venv
```

The Application Insights resource, workspace and alert rule go with the resource group. Check the workspace isn't
left in a soft-deleted state you care about (it doesn't hold anything beyond this demo).
