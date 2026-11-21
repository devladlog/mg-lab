# DEVLADLOG AI #17 — Azure AI services as a platform: one resource, one identity, one place to look

Blog guide: [Azure AI Services: The Complete Guide (2025)](https://www.devladlog.com/articles/ai/2025-01-01-azure-ai-services-complete-guide-2025/)

Episodes 4, 6, 12 and 13 each created their own Azure resource for the Contoso Porto service desk (Document Intelligence,
Content Safety, Language, Vision). That is fine for a demo and wrong for running it. This episode builds the **platform
layer**: one **Foundry resource** (kind `AIServices`, keyless, logs to Log Analytics), and four small tools in Python that
answer the questions a platform owner has: *which service for which job*, *who may call it*, *what happened*, and
*which of our code has a retirement date*.

```
                     data/catalog.json ──► catalog      (no Azure call)   which service, which host, which lifecycle
infra/main.bicep ──► ONE Foundry resource (AIServices, S0, custom subdomain, keys off) + Log Analytics + Cognitive Services User
                              │ same Entra token, <name>.cognitiveservices.azure.com
                              ├─► probe     Language · Translator · Content Safety · Document Intelligence: the cheapest real call of each, verdict + hint
                              ├─► audit     ARM: kind, subdomain, keys, network, diagnostics, who holds a data-plane role  (PASS / WARN / FAIL, exit 1 on FAIL)
                              ├─► usage     Azure Monitor metrics: calls, errors, latency per ApiName, billable units
                              └─► lifecycle data/lifecycle.json + a scanner over your code: which retiring service, which file, how many days left (no Azure call)
```

| Question | Answer in this episode |
|---|---|
| One resource or many? | Learn: the Foundry resource (kind `AIServices`) is the one to create for the multi-service case; Azure OpenAI and Foundry Tools are reachable through one endpoint. It answers on three FQDNs under the same custom subdomain (`openai.azure.com`, `services.ai.azure.com`, `cognitiveservices.azure.com`). The Tools (Language, Translator, Content Safety, Document Intelligence, Vision) are on the last one. Speech uses regional `stt` / `tts` hosts; search (Foundry IQ / Azure AI Search) is a separate `Microsoft.Search` resource. `catalog` says so per job |
| Who may call it? | Entra ID only (`disableLocalAuth`), against the custom subdomain, role **Cognitive Services User**. Learn: Owner and Contributor have management permissions only, so **an Owner without a data role gets 403** (the first screen of the demo) |
| Can we see the calls? | Diagnostic setting: `Audit` + `RequestResponse` logs and `AllMetrics` to a Log Analytics workspace (Learn's supported logs/metrics for `Microsoft.CognitiveServices/accounts`). `usage` reads `TotalCalls`, `TotalErrors`, `ClientErrors`, `ServerErrors`, `Latency` split by `ApiName`, plus `ProcessedTextRecords`, `TextCharactersTranslated`, `ContentSafetyTextAnalyzeRequestCount` |
| Is the resource configured as intended? | `audit` (pure function over three ARM documents). Each rule is tagged *Learn* or *our policy* (e.g. the `owner` and `costcenter` tags are ours) |
| What has a retirement date? | `lifecycle`: a register of nine retirement entries, every date copied from a Learn page; a line-by-line scanner; status by days left (`RETIRED`, `URGENT` < 180, `PLAN` < 730, `TRACK`; thresholds are ours). Exit 1 when something retired is still used |

## What it found in this series (real run, 21 Nov 2026)

`python -m aiplatform lifecycle ../` over the earlier episodes of this series:

- **Episode 13** (`photoscan`) uses `ImageAnalysisClient`. Learn: the Image Analysis API retires on **25 September 2028**
  (674 days left on 21 Nov 2026). Learn's migration page also asks for a transition plan by **25 September 2026**, which has
  passed; we report it as written.
- **Episode 12** (`ticketnlp`) uses `analyze_sentiment` with opinion mining and `extract_key_phrases`. Learn: sentiment
  analysis and opinion mining, key phrase extraction, summarization, entity linking, CLU and CQA **retire from Azure Language
  on 31 March 2029** (861 days left). Language detection, PII detection and prebuilt NER are listed as supported. So episode 12's
  PII and language-detection path is fine; its sentiment and key-phrase calls are the ones to move to a Foundry model.

Nothing is broken today and the scanner exits 0; the point is that the work becomes a plan with a date.

| Path | What it is |
|---|---|
| [`infra/main.bicep`](infra/main.bicep), [`main.bicepparam`](infra/main.bicepparam) | Foundry resource (`AIServices`, S0, West Europe, custom subdomain, keys off, system-assigned identity), Log Analytics workspace, diagnostic setting, Cognitive Services User for the developer (only if `developerPrincipalId` is given) |
| [`src/aiplatform/http.py`](src/aiplatform/http.py), [`endpoints.py`](src/aiplatform/endpoints.py) | The azure-core pipeline with a bearer-token policy (data plane and ARM scopes, retries off by default); the three FQDNs, refusal of regional endpoints |
| [`src/aiplatform/probe.py`](src/aiplatform/probe.py) | Four probes (Language detect, Translator v3.0 translate, Content Safety `text:analyze`, Document Intelligence resource details through the **real SDK**), verdict and hint per HTTP status |
| [`src/aiplatform/audit.py`](src/aiplatform/audit.py), [`usage.py`](src/aiplatform/usage.py) | Rules over the ARM documents; Azure Monitor metrics query and roll-up |
| [`src/aiplatform/lifecycle.py`](src/aiplatform/lifecycle.py), [`catalog.py`](src/aiplatform/catalog.py), [`cli.py`](src/aiplatform/cli.py) | Register loader, scanner, status arithmetic; catalog; `python -m aiplatform catalog / probe / audit / usage / lifecycle` |
| [`data/lifecycle.json`](data/lifecycle.json), [`data/catalog.json`](data/catalog.json) | The register and the catalog: data, each row with its Learn URL |
| [`tests/`](tests) | 85 pytest tests |

Tested with Python 3.13, `azure-core 1.41.0`, `azure-identity 1.27.0`, `azure-ai-documentintelligence 1.0.2`, Bicep CLI 0.49.2.

## Test locally (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q                                       # 85 passed
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep     # no warnings
bicep build-params infra/main.bicepparam --stdout > /dev/null
PYTHONPATH=src python -m aiplatform catalog --task image        # no Azure call
PYTHONPATH=src python -m aiplatform lifecycle ../ --today 2026-11-21   # no Azure call, scans the sibling episodes
```

What the tests cover. The **real azure-core pipeline and the real Document Intelligence SDK** send their real requests
(Entra bearer token, the documented paths and api-versions) through a stand-in transport, and a rule-based fake answers in
the documented response shapes. It proves the plumbing, **not** what the real services return; the numbers in the fixtures
(a limit of 500 models, latencies, counts) are invented.
- `test_endpoints_http_probe.py`: the three FQDNs resolve to one name, regional and non-https endpoints refused with Learn's
  reason, bearer token on every call and **never a key header**, the right scope per plane, the exact route and host of each
  probe, details read from the responses, 403 / 429 / transport error / unexpected shape each becoming a verdict with a hint,
  no retries by default, a probe failing does not stop the others.
- `test_audit_usage.py`: each audit rule in pass, warn and fail form, Owner alone is not data-plane access, unreadable
  diagnostics or roles degrade to `info`, ARM routes and api-versions, the metrics request shape and the roll-up arithmetic.
- `test_lifecycle_catalog_cli_bicep.py`: every register date we cite, the scanner (file, line, skipped folders, supported
  Language features not flagged), status thresholds and days-left arithmetic, exit codes, catalog and register agree, CLI
  behaviour, and the compiled Bicep (keyless, S0 `AIServices`, the two log categories, only Cognitive Services User and only
  when asked, and the deployed shape satisfies our own audit).

Script code scenes were checked by a throwaway script to be contiguous excerpts of `src/` and `infra/`.

## Deploy and run (needs a subscription)

```bash
az group create -n rg-mglab-ai-17 -l westeurope
# 1. WITHOUT a data-plane role first: the owner gets 403
az deployment group create -g rg-mglab-ai-17 -f infra/main.bicep -p infra/main.bicepparam --query properties.outputs -o json > /tmp/ai17.json
export AIPLATFORM_ENDPOINT=$(jq -r .endpoint.value /tmp/ai17.json) AIPLATFORM_RESOURCE_ID=$(jq -r .resourceId.value /tmp/ai17.json) PYTHONPATH=src
python -m aiplatform probe ; echo $?                            # expected 1: four times 403 forbidden
# 2. Give the signed-in user Cognitive Services User, wait ~5 minutes
az deployment group create -g rg-mglab-ai-17 -f infra/main.bicep -p infra/main.bicepparam -p developerPrincipalId=$(az ad signed-in-user show --query id -o tsv)
python -m aiplatform probe ; echo $?                            # 0: four services, one identity
python -m aiplatform audit ; echo $?                            # PASS x N, WARN (public network); 0
python -m aiplatform usage --minutes 30
python -m aiplatform lifecycle ../ --no-lines
az group delete -n rg-mglab-ai-17 --yes
```

Needs the lab subscription: every result of `probe`, `audit` and `usage` is a real call. `catalog` and `lifecycle` need no Azure
and run for real on this repo. Nothing in this folder claims a result the services have not produced; the numbers on
screen come from the run recorded in `demo.md`.

## What we learned / gotchas

- **Owner is not a developer role.** Learn (Foundry quickstart): "Azure Owner and Contributor roles do only include management
  permissions, and not development permissions." The built-in **Cognitive Services User** has data actions
  `Microsoft.CognitiveServices/*` and also reads metrics and diagnostic settings, so one role covers `probe`, `usage` and the ARM
  reads of `audit`. Reading *role assignments* needs more (Reader or Owner); `audit` reports `info` when it cannot.
- **That role can also list keys** (`accounts/listkeys/action` is in its actions). With `disableLocalAuth` the keys do not
  authenticate any call, but a keyless design should not rely on nobody ever turning local auth back on. `audit` checks the flag.
- **Entra needs the custom subdomain, never a regional endpoint** (Learn). `endpoints.py` refuses `*.api.cognitive.microsoft.com`
  and `api.cognitive.microsofttranslator.com` before any call. The Translator *global* endpoint can still take an Entra token,
  but then needs an `Ocp-Apim-ResourceId` header (Learn); we use the custom-domain form `/translator/text/v3.0/translate`.
- **Role assignments take up to five minutes** to propagate (Learn). A 403 right after the deployment is not a bug.
- **Three FQDNs, three private DNS zones.** Learn (upgrade guide): the resource exposes `openai`, `services.ai` and
  `cognitiveservices` FQDNs and a private-endpoint setup must resolve all three. This episode keeps the public endpoint on
  (the audit warns, Learn calls "All networks" a prototype setting); private networking is a follow-up, not tested here.
- **Retirement dates move and some are in the past.** Anomaly Detector, Metrics Advisor and Personalizer retired on 1 Oct 2026
  (Learn lifecycle page); Content Moderator retires 15 Mar 2027; Language Studio moves to Foundry on 20 Mar 2027 (the migration
  page says projects, data and endpoints are not affected; the register does not scan for it). The Learn migration pages for
  Image Analysis and Custom Vision ask for a plan by 25 Sep 2026 *and* retirement on 25 Sep 2028; we report both as written.
- **The scanner finds use, not importance.** It is a line-by-line regex over `.py .cs .ts .js .java .kt .bicep .json .yaml .yml .ps1`,
  skips `tests`, `.venv`, `node_modules`, `bin`, `obj`, `script.yaml` and the register itself. It misses calls built from strings,
  other languages and things in a notebook; it can also hit a comment (`--include-tests` scans this episode's own tests).
- **A passing probe says "it answers", not "it answers well".** Accuracy is what episodes 4, 6, 12 and 13 measured per service.
- **Test doubles must behave like the SDK.** The Document Intelligence SDK speaks `azure.core.rest`, whose response must already be
  read; the legacy fake transport of the earlier episodes did not work here (`'RequestsTransportResponse' object has no attribute 'json'`).
  The new fake mirrors what the real transport does for a non-streamed request.
- **One AIServices resource is one blast radius.** Learn says each pricing tier specifies a maximum number of transactions per
  second. Our inference (not tested here): callers that share a resource share that headroom and the same role assignments, so
  teams with very different load or sensitivity may deserve their own resource.
- **The Translator API has a newer version** (`2026-06-06`, LLM-capable, token-billed for LLM models per Learn). The probe uses the
  documented v3.0 path; moving to the new version is a change in `probe.py` and in the billing model.

Out of scope on purpose: private endpoints, customer-managed keys, projects and agents on the same resource, Speech, deployments and
quota for models (episodes 2 and 5), and Content Understanding (preview per Learn).

## References

- [What are Foundry Tools?](https://learn.microsoft.com/azure/ai-services/what-are-ai-services) — the service list, tiers and billing, retiring services
- [Quickstart: Set up your first Foundry resource](https://learn.microsoft.com/azure/ai-services/multi-service-resource) — kind `AIServices`, developer roles, Owner/Contributor note
- [Authenticate requests to Foundry Tools](https://learn.microsoft.com/azure/ai-services/authentication) — Entra needs the custom subdomain; keys and tokens; disable local auth
- [Custom subdomain names](https://learn.microsoft.com/azure/ai-services/cognitive-services-custom-subdomains) — regional endpoints, subdomain cannot be changed
- [Foundry SDKs and endpoints](https://learn.microsoft.com/azure/foundry/how-to/develop/sdk-overview#foundry-tools-sdks) — which endpoint for which tool; Language features retiring 31 Mar 2029
- [Upgrade from Azure OpenAI to Foundry](https://learn.microsoft.com/azure/foundry/how-to/upgrade-azure-openai#private-network-configuration) — the three FQDNs
- [Foundry architecture](https://learn.microsoft.com/azure/foundry/concepts/architecture#azure-ai-resource-types-and-providers) — resource kinds under `Microsoft.CognitiveServices`
- [Cognitive Services User role](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/ai-machine-learning) — actions and data actions
- [Translator: Microsoft Entra authentication](https://learn.microsoft.com/azure/ai-services/translator/how-to/microsoft-entra-id-auth) and [Translate 3.0](https://learn.microsoft.com/azure/ai-services/translator/text-translation/reference/v3/translate)
- [Content Safety: analyze text (REST)](https://learn.microsoft.com/azure/ai-services/content-safety/quickstart-text) — `2024-09-01`
- [Document Intelligence SDK: resource details](https://learn.microsoft.com/dotnet/api/azure.ai.documentintelligence.documentintelligenceadministrationclient.getresourcedetails) — custom model count and limit
- [Supported metrics](https://learn.microsoft.com/azure/azure-monitor/reference/supported-metrics/microsoft-cognitiveservices-accounts-metrics), [supported logs](https://learn.microsoft.com/azure/azure-monitor/reference/supported-logs/microsoft-cognitiveservices-accounts-logs) for `Microsoft.CognitiveServices/accounts`; [Azure Monitor REST walkthrough](https://learn.microsoft.com/azure/azure-monitor/metrics/rest-api-walkthrough#retrieve-metric-values)
- Retirements: [Image Analysis](https://learn.microsoft.com/azure/ai-services/computer-vision/migration-options), [Custom Vision](https://learn.microsoft.com/azure/ai-services/custom-vision-service/migration-options), [Content Moderator](https://learn.microsoft.com/azure/ai-services/content-moderator/overview), [Anomaly Detector / Metrics Advisor / Personalizer](https://learn.microsoft.com/lifecycle/end-of-support/end-of-support-2026), [Sentiment analysis](https://learn.microsoft.com/azure/ai-services/language-service/sentiment-opinion-mining/overview), [Key phrase extraction](https://learn.microsoft.com/azure/ai-services/language-service/key-phrase-extraction/overview), [CLU](https://learn.microsoft.com/azure/ai-services/language-service/conversational-language-understanding/overview), [Language Studio to Foundry](https://learn.microsoft.com/azure/ai-services/language-service/migration-studio-to-foundry)
- Blog: [Azure AI Services: The Complete Guide (2025)](https://www.devladlog.com/articles/ai/2025-01-01-azure-ai-services-complete-guide-2025/)
