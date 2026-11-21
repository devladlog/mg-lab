# DEVLADLOG Copilot & AI #20 - Azure AI Foundry Agent Service with Multiple Models

"Azure AI Foundry" is now **Microsoft Foundry**; its agent runtime is **Foundry Agent Service** (Learn: *Agents in Microsoft
Foundry*). This episode builds one prompt agent per model in a single Foundry resource, with the same instructions, sends
the same Contoso procurement tasks through all of them, scores the answers with plain rules and recommends a model per task
category:

- `src/infra/main.bicep`: Foundry resource (AIServices, project management on, Entra-only), a project, and one
  `accounts/deployments` resource per entry of the `deployments` parameter. `bicep build` and `build-params` pass.
- `foundry_multimodel` (Python): `FoundryBackend` (Azure AI Projects 2.x: `agents.create_version` with
  `PromptAgentDefinition`, `get_openai_client(agent_name=...)`, `conversations` + `responses.create`, usage and cleanup),
  deterministic scoring, runner, report and routing, CLI `plan | run | report`.
- `src/samples/`: five Contoso tasks (extraction, classification, summarisation, a prompt-injection email, arithmetic),
  a config with placeholder prices, and a **fictional** results file used only by the tests and the report format.

Series plan: [`../../README.md`](../../README.md). Shared lab: [`../../../LAB.md`](../../../LAB.md). Previous in series:
[episode 19, Copilot governance](../19-copilot-governance-purview-dspm-for-ai-and-admin-c/) (Purview lists Microsoft Foundry
among the enterprise AI apps it governs). Category episodes this builds on:
[AI agents orchestration](../../../ai/episodes/05-ai-agents-orchestration/),
[Azure OpenAI enterprise patterns](../../../ai/episodes/02-azure-openai-enterprise-patterns/),
[AI governance and compliance](../../../ai/episodes/07-ai-governance-compliance/).
Next: episode 21, *Claude in the Microsoft Ecosystem* (Claude models in Foundry are left to that episode).

| Path | What it is |
|---|---|
| [`src/infra/main.bicep`](src/infra/main.bicep), [`main.bicepparam`](src/infra/main.bicepparam) | Foundry resource + project + N model deployments (needs the tenant's Azure subscription to deploy) |
| [`src/foundry_multimodel/backend.py`](src/foundry_multimodel/backend.py) | The real Foundry calls (needs a Foundry project and a signed-in credential) |
| [`src/foundry_multimodel/scoring.py`](src/foundry_multimodel/scoring.py) | Rule checks: JSON fields, numbers, contains/not-contains, regex, word limit |
| [`src/foundry_multimodel/runner.py`](src/foundry_multimodel/runner.py) | Run, summarise, cost estimate (your prices), routing, markdown report, cleanup in `finally` |
| [`src/foundry_multimodel/cli.py`](src/foundry_multimodel/cli.py) | `python -m foundry_multimodel plan\|run\|report` |
| [`src/samples/`](src/samples) | `tasks.json`, `config.json` (placeholder prices), `results-sample.json` (fictional) |
| [`tests/`](tests) | 17 pytest tests |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (14 scenes, about 750 words) and shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/20-azure-ai-foundry-agent-service-with-multiple-model
python3 -m pip install -r src/requirements.txt        # azure-ai-projects>=2.3.0, azure-identity, pytest
python3 -m pytest -q                                   # 17 passed (15 passed + 2 skipped if azure-ai-projects is not installed)
cd src
python3 -m foundry_multimodel plan --config samples/config.json --tasks samples/tasks.json
python3 -m foundry_multimodel report samples/results-sample.json
bicep build infra/main.bicep && bicep build-params infra/main.bicepparam
```

Live (needs the tenant's Azure subscription; creates and deletes agents, sends `models x tasks x repeats` requests):

```bash
az login                                              # off camera; DefaultAzureCredential picks it up
export FOUNDRY_PROJECT_ENDPOINT="https://<resource>.services.ai.azure.com/api/projects/<project>"
python3 -m foundry_multimodel run --config config.json --tasks tasks.json --out results.json
```

Verified here: pytest 17 passed with `azure-ai-projects` 2.11.0 installed (Python 3.13); `bicep build` and `build-params` succeed.
The backend is tested against stub SDK objects and its call shapes are bound against the real installed SDK signatures
(`create_version`, `delete_version`, `get_openai_client`, `PromptAgentDefinition`). **Not verified without the tenant:** any
real call to Foundry, which models can be deployed in the lab subscription's region and quota, and any real score or price.

## What we learned / gotchas

- **Renamed.** Azure AI Foundry became Microsoft Foundry; RBAC roles *Azure AI User/Owner/Account Owner/Project Manager* became
  *Foundry User/Owner/Account Owner/Project Manager* with unchanged role IDs and permissions ("you might still see the previous
  names in some places"). The earlier agents experience is **Agents (classic)**: deprecated, retiring on **31 March 2027**; the new
  GA service is Foundry Agent Service. Python `azure-ai-projects` **2.x** is incompatible with 1.x.
- **The prompt agent's `model` is a deployment name** in your Foundry resource (Learn's sample passes `gpt-5-mini`, commented
  "supports all Foundry direct models"). To compare models you deploy each one first; the Bicep does that in a loop with
  `@batchSize(1)`.
- **Permissions:** to create agents the identity needs **Foundry User** at the project (Learn quickstart); to call an agent endpoint
  **Foundry Agent Consumer** is the least-privilege role; Foundry User also allows it. An agent-scope role assignment authorizes
  calling the agent but does **not isolate project files**: any caller who can invoke a prompt agent can reference any file ID in
  the project. Use separate projects to separate callers.
- **Tracing prerequisite:** the quickstart lists Application Insights connected to the project and permission to read traces.
- **Tool support varies by region and model** (Learn, *limits, quotas, and regional support*): check the matrix before promising web
  search, code interpreter, file search, MCP and so on on a given model. This episode uses no tools on purpose.
- **Non-OpenAI models:** the overview says Agent Service works with many models from the Foundry model catalog, for example
  GPT-4o, Llama and DeepSeek, "swap models without changing your agent code". The classic regional page lists Foundry Models sold by
  Azure (for example Llama-3.3-70B-Instruct, grok and DeepSeek families, gpt-oss-120b); that list is for the classic experience
  and may change, so we do not hard-code any non-OpenAI name. Take `Format`, `Name` and `Version` from
  `Get-AzCognitiveServicesAccountModel`, and check quota and region.
- **Model router** is a Foundry model that chooses a model per request; Learn has a page for using it with agents. Measure it
  with the same task file instead of trusting it.
- **Prices are never hard-coded.** `config.json` carries placeholder zeros on purpose; copy real per-token prices from the Azure
  pricing page for your deployments. The cost column is an estimate from your numbers and the tokens the service reports.
- **Scoring is deterministic, and honest about its size.** A task without rules scores 0 (a test guards this), five tasks is a
  smoke test, and answers vary between runs: use `repeats` in the config.
- **Cleanup:** agents and conversations are deleted in `finally`, including after `KeyboardInterrupt` (tested); `--keep-agents`
  keeps them for the portal screen, so delete them (or the resource group) afterwards.
- **Agent naming:** the tool lowercases and hyphenates names. The quickstart page does not state a character or length rule for
  agent names; the 63-character cut is our own caution.

## References

Microsoft Learn
- [Agents in Microsoft Foundry (overview)](https://learn.microsoft.com/azure/foundry/agents/overview)
- [Quickstart: Create a prompt agent](https://learn.microsoft.com/azure/foundry/agents/quickstarts/prompt-agent)
- [Quickstart: Deploy a Microsoft Foundry resource by using a Bicep file](https://learn.microsoft.com/azure/foundry/how-to/create-resource-template)
- [Foundry Agent Service limits, quotas, and regional support](https://learn.microsoft.com/azure/foundry/agents/concepts/limits-quotas-regions)
- [Agent endpoint authorization in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-endpoint-authorization)
- [Agent identity concepts](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-identity)
- [Use model router with agents](https://learn.microsoft.com/azure/foundry/openai/how-to/model-router-agents)
- [Azure OpenAI models and regions for Foundry Agent Service (classic)](https://learn.microsoft.com/azure/foundry-classic/agents/concepts/model-region-support)
- [Quickstart: Create a new agent (classic): deprecation notice](https://learn.microsoft.com/azure/foundry-classic/agents/quickstart)
- [Microsoft.CognitiveServices accounts/deployments (Bicep)](https://learn.microsoft.com/azure/templates/microsoft.cognitiveservices/accounts/deployments) and [accounts/projects](https://learn.microsoft.com/azure/templates/microsoft.cognitiveservices/accounts/projects)
- [Get-AzCognitiveServicesAccountModel](https://learn.microsoft.com/powershell/module/az.cognitiveservices/get-azcognitiveservicesaccountmodel)
- [Microsoft Purview data security and compliance protections for generative AI apps](https://learn.microsoft.com/purview/ai-microsoft-purview) (Foundry among enterprise AI apps)

Foundry samples (template shape): github.com/microsoft-foundry/foundry-samples, `infrastructure/infrastructure-setup-bicep/00-basic`.

No devladlog.com blog guide: this series is built from vendor documentation only.
