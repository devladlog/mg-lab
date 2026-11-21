# DEVLADLOG AI #7 — AI governance and compliance, as code: a register, guardrails and evidence

Six episodes in, Contoso has four AI systems (helpdesk triage, the HR bot, invoice intake, the AP agent) built by
different people. The compliance officer asks three questions: **what AI do we run, who owns it, and can you prove
the controls are on?** This episode answers them with three layers that check each other:

```
governance/register.yaml          Azure Policy (resource group)                 aigov.evidence
 one entry per AI system   ──►     keyless .............. Deny          ──►      register + live ARM state
 owner, tier, approved models      approved models ...... Deny                    → PASS/FAIL per control
 oversight, last RAI gate          diagnostic logs ...... AuditIfNotExists        → evidence-<system>.txt  ──► Compliance Manager
        ▲                                                                         → exit code (pipeline gate)     (EU AI Act assessment,
        └── resources point back with the tag  ai-system-id                                                        Evidence tab)
```

- **The register is code.** `governance/register.yaml` lists every system with an accountable owner, an internal
  impact tier (agreed with legal; this repo classifies nothing under any law), approved model **versions**, human
  oversight and the date and verdict of the last responsible-AI gate (episode 6). It is validated in tests and
  changed through pull requests.
- **Azure Policy stops the obvious mistakes before any code runs.** Three built-in definitions assigned on the
  resource group by Bicep: *Azure AI Services resources should have key access disabled* (Deny), *Foundry model
  deployments should only use approved models* (Deny, exact asset IDs) and *Diagnostic logs in Azure AI services
  resources should be enabled* (AuditIfNotExists).
- **The evidence pack compares promises with reality.** `aigov.evidence` reads the live state with read-only ARM
  calls (accounts, deployments, guardrail policies, diagnostic settings, Policy states), runs 11 controls per
  account, flags **AI resources nobody registered**, writes one report per system and exits 1 on any FAIL.
- **Purview Compliance Manager is where the compliance officer works.** Its premium AI templates (EU Artificial
  Intelligence Act, ISO/IEC 42001, ISO/IEC 23894, NIST AI RMF) give the assessment; our report is uploaded as
  evidence on the improvement actions it supports.

| Control | Checks | Source |
|---|---|---|
| GOV-01 | Account tagged `ai-system-id` with an id that exists in the register (else **UNREGISTERED**) | ARM tags |
| GOV-02 | Named owner, `next_review` not in the past | register |
| SEC-01 | `disableLocalAuth = true` | ARM |
| SEC-02 | Diagnostic setting sends the `Audit` category to a Log Analytics workspace | ARM diagnostic settings |
| MOD-01 | Every deployment's model **and version** is in `approved_models` | ARM deployments |
| MOD-02 | `versionUpgradeOption = NoAutoUpgrade` (a silent model change is a change nobody approved) | ARM deployments |
| MOD-03 | `data_residency: eu` → regional or DataZone deployment types only, no Global | ARM deployments |
| RAI-01 | Custom guardrail policy; Jailbreak on, plus Indirect Attack for RAG systems | ARM raiPolicies |
| RAI-02 | Last responsible-AI gate PASS and ≤ 90 days old | register (episode 6 report) |
| RAI-03 | Human oversight described (tier high) | register |
| POL-01 | No `NonCompliant` Azure Policy state on the account or its deployments | Policy Insights |

Tier decides what applies: `low` gets GOV/SEC/MOD-01/MOD-02/POL; `medium` adds MOD-03, RAI-01, RAI-02; `high` adds
RAI-03. Anything not required is reported as `N/A`, never silently skipped.

| Path | What it is |
|---|---|
| [`governance/register.yaml`](governance/register.yaml) | The AI system register (3 fictional systems; hr-bot is the one deployed in this episode) |
| [`infra/main.bicep`](infra/main.bicep) | 3 policy assignments (built-in IDs, non-compliance messages), Log Analytics, the HR bot's keyless Azure OpenAI account (tags, audit logs, guardrail with prompt shields, gpt-5-mini pinned on DataZoneStandard), and an optional untagged "shadow" account |
| [`src/aigov/register.py`](src/aigov/register.py) | Loads and validates the register; reports every problem at once |
| [`src/aigov/arm.py`](src/aigov/arm.py) | Read-only ARM client on the azure-core pipeline (Entra token, retries, `nextLink` / `@odata.nextLink` paging) |
| [`src/aigov/inventory.py`](src/aigov/inventory.py) | Collects accounts, deployments, guardrail filters, diagnostic settings and non-compliant policy states into a JSON snapshot |
| [`src/aigov/controls.py`](src/aigov/controls.py) | The 11 controls, each returning PASS/FAIL/N/A with the evidence that decided it |
| [`src/aigov/evidence.py`](src/aigov/evidence.py) | CLI: console table, `reports/evidence-<system>.txt`, `reports/evidence.json`, exit code; `--snapshot` replays offline |
| [`tests/`](tests) | 30 pytest tests |

## Test locally (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q            # 30 passed (test_bicep.py is skipped without the Bicep CLI)
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep    # no warnings
```

What the tests cover:
- `test_register.py`: the repo's register is valid; a broken file reports **all** problems in one error (bad tier,
  unpinned model version, high tier without oversight, bad date, duplicate id, missing fields).
- `test_arm_inventory.py`: the **real azure-core pipeline** (`RequestsTransport`, bearer token policy over HTTPS,
  retry policy) with a `requests` adapter that answers with canned JSON in the documented REST shapes (written for
  the tests, not captured from Azure): token scope `https://management.azure.com/.default`, the api-version of each
  call, `nextLink` paging, the POST + `$filter` for Policy states, case-insensitive resource-ID matching, 403 errors.
- `test_controls_and_evidence.py`: a compliant HR bot passes all 11 controls; each control fails on its own
  violation (key auth on, no audit category, unapproved version, auto-upgrade, GlobalStandard for an EU system,
  default guardrail, RAG without document-attack shield, stale or failed RAI gate, overdue review, non-compliant
  policy state); low tier gets N/A; shadow and mistyped tags are UNREGISTERED; the CLI writes `.txt` reports,
  saves a snapshot, replays it and returns 1 / 0.
- `test_bicep.py`: the three built-in definition IDs and effects, exact-version asset IDs, keyless accounts, the
  shadow account is conditional and untagged, audit categories to the workspace, both prompt shields.

Tested with Python 3.13, `azure-core 1.41.0`, `azure-identity 1.27.0`, `PyYAML 6.0.4`, Bicep CLI as installed in the
build container.

## Deploy and run (needs a subscription)

```bash
az group create -n rg-mglab-ai-07 -l swedencentral
az deployment group create -g rg-mglab-ai-07 -f infra/main.bicep -p infra/main.bicepparam --query properties.outputs
# wait at least 15 minutes for the policy assignments to take effect, then:
az policy state trigger-scan --resource-group rg-mglab-ai-07
SUB=$(az account show --query id -o tsv)
PYTHONPATH=src python -m aigov.evidence --register governance/register.yaml --subscription $SUB \
   --resource-group rg-mglab-ai-07 --save-snapshot reports/snapshot.json
echo $?    # 1 while the shadow account exists
```

The evidence pack never writes to Azure. A least-privilege identity needs read access to the resources plus
`Microsoft.PolicyInsights/policyStates/queryResults/action` (the Policy states query is a POST); we didn't verify
whether **Reader** alone covers that action, so the recording uses the lab admin. Deploying the policy assignments
needs Owner or Resource Policy Contributor (Learn).

## What we learned / gotchas

- **Approved-model asset IDs match with `contains`.** The built-in definition compares `model.assetId` with each
  allowed ID using `contains`; Learn warns that `.../models/gpt-5` also matches GPT-5.2 and GPT-5.4. Add a trailing
  slash for one model, or the full `/versions/<version>` for one version. We pin full versions, and a test enforces it.
- **`allowedPublishers: []` is deliberate.** The rule denies when the publisher is *not in* the list **and** no asset
  ID matches; with an empty publisher list only the exact asset IDs pass. Adding `OpenAI` there would allow every
  OpenAI model.
- **Policy assignments aren't instant.** Learn: wait at least 15 minutes before testing a Deny, and compliance
  results for existing resources can take up to 24 hours unless you trigger an on-demand scan
  (`az policy state trigger-scan`). The evidence pack reports what Policy Insights says *now*.
- **Deny stops the bad resource; it doesn't find the forgotten one.** The shadow account is keyless, so the
  keyless policy lets it through. Only the register comparison (GOV-01) and the AuditIfNotExists logs policy catch
  it. You need both layers.
- **Compliance Manager's Evidence tab doesn't take `.md`.** Accepted types (Learn): .doc, .xls, .ppt, .txt, .pdf,
  images, .mkv, .zip/.rar. The reports are Markdown saved as `.txt`.
- **AI regulation templates are premium.** Learn: the four AI templates count toward premium regulation licences;
  A5/E5/G5 customers can use any three premium regulations for free. Check the licence counter on the Regulations
  page before creating the assessment (the lab is on an E5 trial).
- **`PipelineClient.send_request()` doesn't join relative paths.** Generated SDKs call `format_url()` first; with a
  bare `/subscriptions/...` path the bearer policy sees a non-HTTPS URL and refuses to send the token. `Arm._send()`
  calls `format_url()` (we hit this in the tests).
- **Data zone vs global** (Learn, deployment types): Global may process prompts in any geography where the model is
  deployed; DataZone keeps processing inside the data zone (EU member nations for an EU resource); data at rest
  stays in the resource's geography for all types. MOD-03 encodes that for `data_residency: eu`.

## References

- [Built-in policies for model deployment in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/how-to/model-deployment-policy) — approved models / eligibility, parameters, prefix matching, 15 minutes, compliance
- [Azure Policy built-in definitions: Azure AI Services](https://learn.microsoft.com/azure/governance/policy/samples/built-in-policies#azure-ai-services) and [Foundry Tools policy reference](https://learn.microsoft.com/azure/ai-services/policy-reference) — definition IDs `71ef260a…`, `1b4d1c4e…`, `aafe3651…`
- [Get compliance data of Azure resources](https://learn.microsoft.com/azure/governance/policy/how-to/get-compliance-data) — evaluation triggers, `az policy state trigger-scan`
- [Create a policy assignment with REST: identify non-compliant resources](https://learn.microsoft.com/azure/governance/policy/assign-policy-rest-api#identify-non-compliant-resources) — `policyStates/latest/queryResults`, api-version 2019-10-01
- [Azure OpenAI monitoring data reference](https://learn.microsoft.com/azure/foundry/openai/monitor-openai-reference#resource-logs) — log categories Audit, RequestResponse, AzureOpenAIRequestUsage, Trace
- [Deployment types](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/deployment-types) — Global vs DataZone vs regional processing locations
- [Compliance Manager: assessments for AI regulations](https://learn.microsoft.com/purview/compliance-manager-assessments#assessments-for-ai-regulations) and [regulations list](https://learn.microsoft.com/purview/compliance-manager-regulations-list) — EU AI Act, ISO/IEC 42001, ISO/IEC 23894, NIST AI RMF; three free premium regulations with E5
- [Working with improvement actions: storing evidence](https://learn.microsoft.com/purview/compliance-manager-improvement-actions#storing-evidence) — accepted file types
- [Govern AI apps and data for regulatory compliance](https://learn.microsoft.com/security/security-for-ai/govern) — Compliance Manager and Defender for Cloud Apps for AI
- [Purview for Microsoft Foundry](https://learn.microsoft.com/purview/ai-azure-foundry) — DSPM for AI, audit, retention for AI interactions (next step, not in this demo)
- [Configure content filters with Bicep](https://learn.microsoft.com/azure/foundry-classic/foundry-models/how-to/configure-content-filters?pivots=programming-language-bicep) — `raiPolicies`
- Blog: [AI Governance & Compliance — Complete Guide](https://www.devladlog.com/articles/ai/2025-07-09-ai-governance-complete-guide-2025/)
