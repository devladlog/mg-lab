# DEVLADLOG Copilot & AI #21 - Claude in the Microsoft Ecosystem

Claude (Anthropic) is now a model choice inside several Microsoft products and a first-class partner model in Microsoft Foundry.
This episode shows each place, then builds the developer part for real on Contoso's renewal data:

- `src/infra/main.bicep`: Foundry resource (AIServices, project management on, Entra-only), a project, and one **Anthropic**
  deployment per entry of `deployments`, with the Marketplace attestation (`modelProviderData`) and an optional
  *Cognitive Services User* role assignment. `bicep build` and `build-params` pass with no warnings.
- `claude_ms` (Python): `client.py` (the Anthropic SDK's `AnthropicFoundry` client, Entra ID or API key), `triage.py` (a
  client-executed tool and the tool-use loop over the Contoso vendor renewals, with an injection attempt in the data),
  `fallback.py` (client-side fallback across deployments), `claude_code_env.py` (the environment that points Claude Code at
  Foundry), CLI `triage | fallback | code-env`.

Series plan: [`../../README.md`](../../README.md). Shared lab: [`../../../LAB.md`](../../../LAB.md). Previous in series:
[episode 20, Foundry Agent Service with multiple models](../20-azure-ai-foundry-agent-service-with-multiple-model/) (it left Claude
models in Foundry to this episode; same Contoso vendor data, total 45,000 euros). Next: episode 22, *OpenAI and Google Gemini APIs
Side by Side*. Related category episodes: [Azure OpenAI enterprise patterns](../../../ai/episodes/02-azure-openai-enterprise-patterns/),
[AI agents orchestration](../../../ai/episodes/05-ai-agents-orchestration/),
[AI governance and compliance](../../../ai/episodes/07-ai-governance-compliance/), and episode 19 of this series
([Copilot governance](../19-copilot-governance-purview-dspm-for-ai-and-admin-c/)) for the admin side.

| Path | What it is |
|---|---|
| [`src/infra/main.bicep`](src/infra/main.bicep), [`main.bicepparam`](src/infra/main.bicepparam) | Foundry resource + project + Claude deployments (needs an eligible Azure subscription to deploy) |
| [`src/claude_ms/client.py`](src/claude_ms/client.py) | `AnthropicFoundry` client factory: Entra ID (`https://ai.azure.com/.default`) or API key |
| [`src/claude_ms/triage.py`](src/claude_ms/triage.py) | Tool definition, tool implementation and the tool-use loop |
| [`src/claude_ms/fallback.py`](src/claude_ms/fallback.py) | Client-side fallback (429, 5xx and connection errors move on; 404 and 400 are raised) |
| [`src/claude_ms/claude_code_env.py`](src/claude_ms/claude_code_env.py) | PowerShell / bash activator for Claude Code on Foundry (never writes a key) |
| [`src/claude_ms/cli.py`](src/claude_ms/cli.py) | `python -m claude_ms triage \| fallback \| code-env` |
| [`src/samples/vendors.json`](src/samples/vendors.json) | The Contoso vendor list (same four vendors as episode 20) plus one supplier note that tries to inject instructions |
| [`tests/`](tests) | 31 pytest tests (the real `anthropic` SDK against a scripted HTTP transport) |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (15 scenes, about 890 words) and shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/21-claude-in-the-microsoft-ecosystem
python3 -m pip install -r src/requirements.txt        # anthropic, azure-identity, pytest
python3 -m pytest -q                                   # 31 passed
cd src && python3 -m claude_ms code-env --resource mglabfoundry21 --sonnet claude-sonnet-5-5 --haiku claude-haiku-5-5
bicep build infra/main.bicep && bicep build-params infra/main.bicepparam
```

Live (needs the lab Azure subscription and a Claude deployment; sends a handful of short requests):

```bash
az login                                              # off camera; DefaultAzureCredential picks it up
export ANTHROPIC_FOUNDRY_RESOURCE=mglabfoundry21      # the resource NAME, not a URL
python3 -m claude_ms triage --deployment claude-sonnet-5-5 --vendors samples/vendors.json
python3 -m claude_ms fallback --deployments claude-sonnet-5-5,claude-haiku-5-5 --prompt "One sentence: why renegotiate before January?"
```

Verified here (Linux container, Python 3.13, `anthropic` 2.12.0, `azure-identity` 1.27.0, Bicep 0.49.2): pytest **31 passed**;
`bicep build`/`build-params` succeed and the compiled template carries `format: Anthropic` and `modelProviderData`. The tests drive the
real SDK against a scripted HTTP endpoint, so URL (`/anthropic/v1/messages`), headers (`x-api-key` or `Authorization: Bearer`), the
`model` = deployment name, the tool-use round trip, thinking-block pass-through and the fallback behaviour are really exercised.
**Not verified without the tenant:** any call to a real Claude deployment, which models and versions the lab subscription can
deploy (region, quota, billing-country eligibility), real prices, what the admin centre and Copilot Studio screens look like in the
lab tenant, and whether the model ignores the injected supplier note (that is model behaviour: the episode records it, it does not
assert it).

## What we learned / gotchas

- **Admin first.** Anthropic is a Microsoft *subprocessor*: with the setting on, the Microsoft Product Terms, DPA and Enterprise Data
  Protection apply to Claude in Microsoft Copilot, Researcher, Copilot Studio, Power Platform and Copilot in Microsoft 365 apps.
  Path: Microsoft 365 admin center, Copilot > Settings > View all > *AI providers operating as Microsoft subprocessors* > Anthropic.
  On by default for most commercial customers, **off in the EU, EFTA and UK** (the lab tenant is in Portugal). Claude in these offerings is
  currently **excluded from the EU Data Boundary** and in-country processing commitments; not available in GCC High, DoD or other
  sovereign clouds (non-federal GCC has its own opt-in since 22 July 2026). A change on **9 December 2026** retires the EU/UK option
  "All users for Microsoft 365 apps only" (Claude then enabled for all users for tenants that had it or no option selected).
- **Two switches for Copilot Studio.** The Microsoft 365 admin center setting does not make Claude appear in Copilot Studio by itself:
  a Power Platform admin must also allow the provider in each environment or environment group (Power Platform admin center).
  "Anthropic models with data retention" (the Fable models) are a separate opt-in, off everywhere by default, under Anthropic's own
  terms (data stored by Anthropic, up to 30 days for most inputs and outputs).
- **Copilot Studio model lifecycle.** The Learn table lists Claude Sonnet 5.5, Haiku 5.5, Opus 5.5 and the Fable models as GA, and Sonnet 4.6,
  Sonnet 5, Opus 4.8 and Opus 5 as *retiring 15 February 2027* (replacements Sonnet 5.5 and Opus 5.5). Check the page on the recording day.
- **Microsoft 365 Copilot add-on.** Researcher, Copilot in Excel/Word/PowerPoint and Copilot Cowork are part of the paid add-on
  (episode 1's catalogue: US$30 per user per month, paid yearly, en-US page). Not licensed in the lab: the episode only states what Learn says.
- **Foundry hosting.** Claude comes as version 1 (*hosted on Anthropic infrastructure*) or version 2 (*hosted on Azure*, all GA); not every model
  has both. Billing is the **Claude Consumption Unit** (CCU) through an Azure Marketplace offer, metered hourly, invoiced monthly in arrears, no
  prepaid credits, MACC-eligible. You need a **paid subscription with an active pay-as-you-go method**; Cloud Solution Provider, free-trial,
  student, credit-only and sponsored-credit-only subscriptions are not supported, and Anthropic's supported-regions policy may apply.
- **Attestation.** Deploying from Bicep sends `organizationName`, `countryCode` and `industry` and accepts the Anthropic Marketplace terms for you.
  Use real values. The Learn page lists the `industry` values (`technology`, `finance`, `healthcare`, `education`, `retail`, `manufacturing`,
  `government`, `media`, `other`), which `main.bicep` enforces with `@allowed`. The property is **not in the published ARM type** for
  `accounts/deployments`: the Azure Verified Module `avm/res/cognitive-services/account` 0.19.3 sends it as `properties.modelProviderData`
  (api-version 2026-05-01), which is what `main.bicep` does, with a `#disable-next-line BCP037`.
- **The `model` parameter is the deployment name** (Learn: it can differ from the model id; Anthropic's page adds that it cannot be changed after creation).
- **What is not supported on Foundry** (Anthropic's *Claude in Microsoft Foundry* page): Admin, Compliance and Models APIs, Message Batches API,
  the server-side `fallbacks` parameter (hence `fallback.py`), user profiles. Not supported on Azure-hosted deployments: code execution,
  newer web search/fetch tool versions, Agent Skills, programmatic tool calling, Files API. Foundry does not return `anthropic-ratelimit-*` headers.
- **No built-in content filter.** Learn (Responsible AI considerations): Foundry does not provide built-in content filtering for Claude models at
  deployment time; configure safety yourself.
- **Auth.** Learn's troubleshooting: 401 = bad key or wrong token scope (`https://ai.azure.com/.default`); 403 = missing role (**Cognitive Services User** or
  **Foundry User**). Claude Mythos models are Entra ID only. `AnthropicFoundry` takes `resource` *or* a base URL, not both; this code takes the resource name.
- **Thinking blocks.** Several current models (for example Opus 5.5) run with adaptive thinking when the request omits `thinking`; when you
  continue a tool-use turn the assistant content must go back unchanged (tested in `test_thinking_blocks_are_sent_back_unchanged`).
- **Claude Code on Foundry.** `CLAUDE_CODE_USE_FOUNDRY=1`, `ANTHROPIC_FOUNDRY_RESOURCE`, `ANTHROPIC_DEFAULT_{SONNET,HAIKU,OPUS}_MODEL`; `/login` and
  `/logout` are disabled; `/status` should show *API provider: Microsoft Foundry*. Learn's own table uses `claude-sonnet-4-6` etc. as examples; names must
  match your deployments. Without `CLAUDE_CODE_USE_FOUNDRY` it silently uses the Anthropic API and asks you to log in.
- **Quota and soft delete.** The default quota depends on the subscription tier and can be 0 for a model. Soft-deleted Foundry accounts can hold quota
  for up to 48 hours: `az cognitiveservices account list-deleted`, then purge (Learn, starter kit troubleshooting).
- **GitHub Copilot.** Claude models are in the model picker (Learn lists them for Visual Studio and SSMS; availability depends on the Copilot plan and, for
  Business/Enterprise, the admin's *Preview* policy). Episodes 13 to 15 cover GitHub Copilot in depth.

## References

- Claude models from Anthropic in Microsoft Online Services: https://learn.microsoft.com/copilot/implement/connect-to-ai-subprocessor
- Overview of AI subprocessors: https://learn.microsoft.com/copilot/plan/copilot-subprocessor-overview
- Enable Claude only for Copilot experiences in Microsoft 365 apps (EU/EFTA/UK, 9 Dec 2026 change): https://learn.microsoft.com/copilot/implement/copilot-anthropic-apps
- Anthropic operated models for non-federal GCC customers: https://learn.microsoft.com/copilot/implement/anthropic-non-federal-gcc
- Model availability in Copilot Studio: https://learn.microsoft.com/microsoft-copilot-studio/agents-experience/authoring-agent-model-availability
- Choose a model for Copilot Cowork: https://learn.microsoft.com/copilot/cowork/cowork-models
- Researcher agent FAQ (Claude in Researcher): https://learn.microsoft.com/copilot/manage/faq-researcher
- Claude models in Microsoft Foundry: https://learn.microsoft.com/azure/foundry/foundry-models/concepts/claude-models
- Deploy and use Claude models in Microsoft Foundry: https://learn.microsoft.com/azure/foundry/foundry-models/how-to/use-foundry-models-claude
- Claude Consumption Units (CCU) billing: https://learn.microsoft.com/azure/foundry/foundry-models/concepts/claude-models-billing
- Deploy Claude models using Bicep or Terraform (Claude on Foundry starter kit): https://learn.microsoft.com/azure/developer/ai/how-to/deploy-claude-foundry
- Configure Claude Code for Microsoft Foundry: https://learn.microsoft.com/azure/foundry/foundry-models/how-to/configure-claude-code
- Azure built-in roles (Cognitive Services User a97b65f3-24c7-4388-baec-2e87135dc908): https://learn.microsoft.com/azure/role-based-access-control/built-in-roles
- Anthropic: Claude in Microsoft Foundry: https://platform.claude.com/docs/en/build-with-claude/claude-in-microsoft-foundry
- Anthropic pricing (CCU rates): https://aka.ms/ccu-pricing
- GitHub Copilot models in Visual Studio: https://learn.microsoft.com/visualstudio/ide/copilot-select-add-models
- No devladlog.com Complete Guide exists for this series; all facts are from Microsoft Learn and Anthropic's documentation, read on 21 Nov 2026.
