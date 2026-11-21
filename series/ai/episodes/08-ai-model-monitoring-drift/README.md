# DEVLADLOG AI #8 — Model monitoring and drift: the HR bot after go-live

Episode 6 gated the HR bot's release and episode 7 proved its controls. Then Contoso launched a **hybrid work
allowance** and opened a **Porto office**: the questions changed, the model didn't. This episode builds the
monitoring that notices — on **Application Insights / Log Analytics** with the **Microsoft OpenTelemetry Distro**,
keyless end to end — and separates four things that people call "drift":

| Signal | What changed | How we measure it |
|---|---|---|
| **Data (input) drift** | who asks and how: language, length | PSI + Jensen-Shannon distance per feature, baseline vs current window |
| **Prediction drift** | what the bot answers: category, urgency, needs_human | same metrics on the model's outputs |
| **Quality** | whether the answers are still *right* | accuracy on a small labelled golden set, re-run in every window |
| **Model version** | which model actually served the calls | `response.model` recorded per call; any change alerts |

```
traffic.py ── question ──► gpt-5-mini (DataZoneStandard, pinned) ──► category / urgency / needs_human
    │  local features: lang hint, length bucket (the question text is never logged)
    └─ logging.info("triage", extra={hr_window, hr_lang, ..., hr_category, hr_model, hr_latency_ms, tokens})
         └─► Microsoft OpenTelemetry Distro (Entra credential) ─► Application Insights (local auth off) ─► AppTraces

monitor.py ── LogsQueryClient (KQL on AppTraces) ──► drift per feature + golden accuracy + model versions
    ├─ prints the report, exit 1 on alert
    └─ logging.info("drift_report", hr_max_psi=...) ─► scheduled query rule (PSI >= 0.2) ─► Azure Monitor alert
```

- **Metrics from the Azure ML playbook**: Learn lists Jensen-Shannon distance and Population Stability Index among
  the categorical data-drift and prediction-drift metrics of Azure Machine Learning model monitoring. We compute
  them ourselves on the bot's telemetry, because an LLM app has no feature table. PSI bands come from Learn's Azure
  Databricks data profiling page (< 0.1 no significant change, < 0.2 moderate, ≥ 0.2 significant); that page defines PSI
  for numeric columns, Azure ML lists it for categorical ones too, so applying the same bands to our categorical
  features is a convention, not a documented threshold.
- **Keyless telemetry**: Application Insights has `DisableLocalAuth: true`, so the exporter must present an Entra
  token; the developer gets **Monitoring Metrics Publisher** on it, **Log Analytics Reader** on the workspace and
  **Cognitive Services OpenAI User** on the model.
- **Privacy by design**: features are derived locally; only the features and the model's answer are logged.
- **Pinned model**: `versionUpgradeOption: NoAutoUpgrade`. The model-version check catches it if someone changes that.

| Path | What it is |
|---|---|
| [`infra/main.bicep`](infra/main.bicep) | Log Analytics, workspace-based App Insights (local auth off), Azure OpenAI (keys off) + `chat` = gpt-5-mini 2025-08-07 DataZoneStandard pinned, request-usage logs + metrics to the workspace, the drift alert rule (`scheduledQueryRules`), 3 role assignments |
| [`src/hrmon/triage.py`](src/hrmon/triage.py) | Episode 6's triage contract on the v1 endpoint (Entra token, strict schema); returns answer, served model, latency, tokens |
| [`src/hrmon/features.py`](src/hrmon/features.py) | Local input features: Portuguese/English hint (stopwords + diacritics heuristic), length bucket |
| [`src/hrmon/telemetry.py`](src/hrmon/telemetry.py) | `use_microsoft_opentelemetry(...)` with an Entra credential and `logger_name="hrmon"`; validated `hr_*` attributes; `flush()` |
| [`src/hrmon/traffic.py`](src/hrmon/traffic.py) | CLI: replays a window of questions through the deployment, records telemetry, runs the golden set |
| [`src/hrmon/drift.py`](src/hrmon/drift.py) | PSI, Jensen-Shannon distance, smoothing, minimum sample size, bands |
| [`src/hrmon/logs.py`](src/hrmon/logs.py) | KQL on `AppTraces` (`Properties["hr_*"]`) and `LogsQueryClient.query_workspace`; partial results are errors |
| [`src/hrmon/monitor.py`](src/hrmon/monitor.py) | CLI: drift table, model versions, golden accuracy, exit code; emits `drift_report` for the alert |
| [`data/`](data) | 40 baseline and 40 current fictional HR questions (the current window adds the hybrid allowance and more Portuguese), 16 labelled golden questions |
| [`tests/`](tests) | 36 pytest tests |

## Test locally (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q            # 36 passed (test_bicep.py is skipped without the Bicep CLI)
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep    # no warnings
```

What the tests cover (the model double answers with **fixed keyword rules**; its numbers are not the model's):
- `test_drift_and_features.py`: PSI equals the formula; JS distance symmetric and bounded; identical windows → 0;
  a category never seen in the baseline stays finite (smoothing) and is significant; the bands; small windows are
  `insufficient`; two halves of the same population give a small non-zero PSI below 0.1; the repo datasets really
  shift language.
- `test_triage_traffic_telemetry.py`: the **real `openai` SDK** against a local stub of the v1 endpoint (Entra bearer
  token, scope `https://ai.azure.com/.default`, strict schema, no `temperature`); records contain features and
  answers but **never the question text**; a failed call is recorded and the window continues; golden accuracy
  drops when the model behaves differently; records reach a real OpenTelemetry `LoggerProvider` with their
  attributes; Azure Monitor setup passes the Entra credential, `logger_name` and `enable_sensitive_data=False`;
  the CLI writes local records.
- `test_logs_and_monitor.py`: the **real `azure-monitor-query` LogsQueryClient** through azure-core with a canned
  Log Analytics response: URL `https://api.loganalytics.io/v1/workspaces/{id}/query`, token scope
  `https://api.loganalytics.io/.default`, timespan; KQL injection through a window label is refused; partial
  results raise; the analysis flags language and category drift; the same population doesn't alert; a model
  version change plus quality drop alerts **even when inputs and outputs look the same**; CLI exit codes.
- `test_bicep.py`: App Insights local auth off and workspace-based, pinned deployment, alert rule query and
  criteria, exactly three data-plane roles, request-usage logs.

Tested with Python 3.13, `openai 3.57.0`, `azure-monitor-query 2.0.0`, `microsoft-opentelemetry 1.6.0`
(`opentelemetry-sdk 1.45.2`), `azure-identity 1.27.0`, Bicep CLI as installed in the build container.

## Deploy and run (needs a subscription)

```bash
az group create -n rg-mglab-ai-08 -l swedencentral
az deployment group create -g rg-mglab-ai-08 -f infra/main.bicep -p infra/main.bicepparam \
   -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv) --query properties.outputs
export AOAI=<aoaiEndpoint> APPINSIGHTS="<appInsightsConnectionString>" WS=<workspaceId>
PYTHONPATH=src python -m hrmon.traffic --data data/baseline.jsonl --window baseline --aoai-endpoint $AOAI \
   --appinsights "$APPINSIGHTS" --golden data/golden.jsonl
PYTHONPATH=src python -m hrmon.traffic --data data/current.jsonl --window current --aoai-endpoint $AOAI \
   --appinsights "$APPINSIGHTS" --golden data/golden.jsonl
# wait a few minutes for ingestion, then:
PYTHONPATH=src python -m hrmon.monitor --workspace-id $WS --baseline baseline --current current --appinsights "$APPINSIGHTS"
echo $?    # 1 = alert
```

## What we learned / gotchas

- **PSI explodes on a value the baseline never saw.** `ln(actual/0)` is infinite. Empty bins get a small epsilon
  (1e-4) and are renormalised; a test proves a new language stays finite and still counts as significant.
- **Small windows drift by chance.** Two halves of the *same* 400 messages give a non-zero PSI. Below 30 records per
  window the monitor says `insufficient` instead of guessing; 40 per window (the demo) is still small — treat the
  numbers as a smoke alarm, not a measurement.
- **Drift says "different", not "worse".** The current window drifts a lot, and that may be fine: new topics are
  real. Only the golden set says whether answers got worse, and a model change can make answers worse *without*
  visible drift (a test shows exactly that). Monitor all four signals.
- **Keyless ingestion needs a credential and a role.** With `DisableLocalAuth: true` the exporter must pass an Entra
  credential and the identity needs **Monitoring Metrics Publisher**; Learn's troubleshooting lists 400 (no
  credential) and 403 (no role) for Python.
- **One distro only.** Learn recommends the Microsoft OpenTelemetry Distro (`microsoft-opentelemetry`) for new Python
  apps and says not to initialise it together with the Azure Monitor OpenTelemetry Distro. `logger_name="hrmon"`
  limits log collection to our logger.
- **The distro also traces the OpenAI SDK.** `microsoft-opentelemetry` 1.6.0 turns on its OpenAI instrumentation by
  default (calls appear as dependencies). We pass `enable_sensitive_data=False` explicitly so message content stays
  out of those spans too; check `AppDependencies` once after the first run (demo.md) rather than trusting a default.
- **Short scripts must flush.** OpenTelemetry batches log records; `telemetry.flush()` calls `force_flush()` on the
  logger provider before the process exits, otherwise the last records can be lost.
- **Logs aren't instant.** Learn: average ingestion latency is under 10 seconds once data reaches Azure Monitor, but
  end-to-end it varies, and Azure resource logs usually take 3 to 10 minutes. The alert rule evaluates every
  5 minutes over 15. Wait before running the monitor.
- **Partial query results are data loss.** `query_workspace` can return a partial result; `fetch()` raises instead of
  computing drift on half the data.
- **SDK details we hit in the tests:** `LogsQueryClient` sends a `timedelta` timespan as ISO seconds (`PT21600.0S`),
  and `LoggingHandler` in `opentelemetry-sdk` is deprecated in favour of the one in
  `opentelemetry-instrumentation-logging`.

## References

- [Azure Machine Learning model monitoring: signals and metrics](https://learn.microsoft.com/azure/machine-learning/concept-model-monitoring?view=azureml-api-2#monitoring-signals-and-metrics) — data drift, prediction drift, JS distance, PSI
- [Data profiling metric tables (Azure Databricks)](https://learn.microsoft.com/azure/databricks/data-governance/unity-catalog/data-quality-monitoring/data-profiling/monitor-output#column-schemas-for-generated-tables) — PSI bands 0.1 / 0.2
- [Enable OpenTelemetry with Application Insights](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-enable) and [Configure OpenTelemetry](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-configuration) — Microsoft OpenTelemetry Distro, Entra credential, don't initialise two distros
- [Add and modify OpenTelemetry: custom dimensions on Python logs](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-add-modify#modify-telemetry) — `extra=`
- [Microsoft Entra authentication for Application Insights](https://learn.microsoft.com/azure/azure-monitor/app/azure-ad-authentication) — `DisableLocalAuth`, Monitoring Metrics Publisher
- [Troubleshoot missing telemetry: Entra issues (Python)](https://learn.microsoft.com/troubleshoot/azure/azure-monitor/app-insights/telemetry/investigate-missing-telemetry#troubleshoot-microsoft-entra-authentication-issues) — 400 / 403
- [AppTraces table](https://learn.microsoft.com/azure/azure-monitor/reference/tables/apptraces) and [telemetry data model](https://learn.microsoft.com/azure/azure-monitor/app/data-model-complete#trace-telemetry)
- [LogsQueryClient (Python)](https://learn.microsoft.com/python/api/azure-monitor-query/azure.monitor.query.logsqueryclient?view=azure-python) — `query_workspace`, partial results
- [Log data ingestion time](https://learn.microsoft.com/azure/azure-monitor/logs/data-ingestion-time)
- [Azure built-in roles: Monitor](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles#monitor) — Monitoring Metrics Publisher, Log Analytics Reader
- [Azure OpenAI monitoring data reference](https://learn.microsoft.com/azure/foundry/openai/monitor-openai-reference#resource-logs) — AzureOpenAIRequestUsage
- [Structured outputs](https://learn.microsoft.com/azure/foundry/openai/how-to/structured-outputs) and [reasoning models](https://learn.microsoft.com/azure/foundry/openai/how-to/reasoning)
- Blog: [AI Model Monitoring & Drift — Complete Guide](https://www.devladlog.com/articles/ai/2025-06-08-model-monitoring-complete-guide-2025/)
