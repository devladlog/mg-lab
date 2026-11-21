# 14 · AI models in both apps

Three models do the same job, summarise an inspection finding and classify its severity, in the canvas field app (episode 11) and the model-driven back-office app (episode 12):

1. an **AI Builder prompt** (needs Copilot Credits to run in an app: **marked as credit based**),
2. an **Azure OpenAI** deployment in the lab subscription through a **custom connector with Entra sign-in**,
3. one **non-Microsoft model, Claude**, through the official Anthropic API: a no-auth custom connector, with the key in a **secret environment variable** (Azure Key Vault) read by a cloud flow.

All three must return the same JSON contract, and are scored on the same 13-note golden set. The suggestion is saved in five new columns of an **extension solution** (`ContosoInspectionsAI`);
the base ContosoInspections schema from episode 12 is used as it is, and the person's own Severity is never overwritten.

**Honest status.** Everything was tested offline. The model routes were **never run against a real model**: the tests use local test doubles (a mock HTTP server for `evaluate.py`, record stubs for the Power Fx
connector calls), so this repo contains **no accuracy result** and no model output. The real run is recorded in `demo.md`. Nothing was imported into a tenant or deployed to Azure. The AI Builder route cannot run in an app in
our lab (no credits, no pay-as-you-go plan).

## What we build

| Piece | File |
|---|---|
| Output contract (JSON Schema), the same for every route | [`src/contract/triage.schema.json`](src/contract/triage.schema.json) |
| System prompt (rubric, prompt-injection rule) and the AI Builder prompt instructions | [`src/prompts/system.md`](src/prompts/system.md), [`src/prompts/aibuilder-prompt.md`](src/prompts/aibuilder-prompt.md) |
| Golden set: 13 labelled notes covering every severity and category, one injection trap | [`src/eval/golden.jsonl`](src/eval/golden.jsonl) |
| Scorer and runner (Azure OpenAI v1 API, Anthropic Messages API, OpenAI-compatible); keys only from environment variables | [`src/eval/triage.py`](src/eval/triage.py), [`src/eval/evaluate.py`](src/eval/evaluate.py) |
| Azure: Azure OpenAI S0 + Standard deployment + Key Vault + role assignments (Bicep, region Sweden Central) | [`src/infra/main.bicep`](src/infra/main.bicep) |
| Custom connector, Azure OpenAI, Entra OAuth (Swagger 2.0 + apiProperties) | [`src/connectors/foundry/`](src/connectors/foundry) |
| Custom connector, Anthropic, no auth, key as an internal header parameter | [`src/connectors/anthropic/`](src/connectors/anthropic) |
| Flow `ClaudeTriage`: reads the secret variable (secure outputs), calls the connector (secure inputs); generated | [`src/flows/`](src/flows) |
| Extension solution: 5 columns on Inspection item (generated with episode 12's `attribute_xml`, depends on the base) | [`src/solution/`](src/solution) |
| Canvas: formulas, generated prompt formula, *AI suggestion* screen | [`src/app/Src/`](src/app/Src) |
| Model-driven: custom page *Item AI triage* (generated from the canvas files) and the command | [`src/custompage/`](src/custompage) |
| The base schema, byte for byte | `src/schema/contosoinspections.schema.json` (copy of episode 12's) |

## Run the tests

```bash
cd tests/python && python3 -m pytest -q                              # 61 passed (needs pac, bicep, openapi-spec-validator, jsonschema)
cd tests/ContosoInspections.AI.Tests && dotnet test -m:1             # 50 passed (Microsoft.PowerFx.Interpreter 1.8.1)
```

Clean up afterwards: delete `bin`, `obj`, `__pycache__` and `.pytest_cache`.

What the tests prove: the contract's labels equal the base schema's choices; every golden row is valid and every label is covered; the scorer separates invalid answers from wrong labels and counts under-calls of Major/Critical;
`evaluate.py` sends the right path, headers and body per vendor, never prints a secret, refuses a missing environment variable and has no secret command-line flag; both connector files are valid Swagger 2.0, the Anthropic one has no
connection auth and takes the key as an internal header, the Foundry one asks for the Cognitive Services scope and holds no secret; the flow file is what the generator writes, with secure inputs/outputs where the key travels; the Bicep
compiles and lints clean and creates exactly what it should; the extension is new columns only, with the base option values, and survives `pac solution unpack` and `pack`; the Power Fx functions, both screens and the custom page behave on the
interpreter (route per button, only the AI columns are written, a bad answer saves nothing); the pa.yaml files validate against Microsoft's official schema.
What they do **not** prove: that any model answers well, that a connector imports, that the flow imports, that the deployment works.

## Cost and credits

- **AI Builder prompt:** needs Copilot Credits. Learn's *Licensing and Copilot Credits* page lists AI tools rates of 0.1 (basic), 1.5 (standard) or 10 (premium) Copilot Credits per 1,000 tokens, or per image or page. Credits = tokens / 1,000 x rate. For 13 notes of about 500
  tokens that is 0.65 credits at the basic rate or about 10 at the standard rate. Which tier a prompt uses is **not verified** here. Testing in the prompt builder is free (Learn). Our lab has no credits.
- **Azure OpenAI (Standard):** billed per token. Cost = (input tokens x input price + output tokens x output price) / 1,000,000. `evaluate.py run` takes `--price-in` and `--price-out` and prints the estimate; **no price was verified**, read the Azure pricing page on the day.
  The 13-note run is about 6,500 input and 800 output tokens. Key Vault Standard is per operation. Lab budget: EUR 30 per month. Everything is in `rg-mglab-powerapps-14` and goes with `az group delete`.
- **Claude:** billed by Anthropic per token with the same formula. Price per million tokens was shown on a pricing page on the research day; it is not repeated here because it was not cross-checked.
- **Licences:** a custom connector needs a premium (or trial) licence to run in a flow (Learn, *Limits of automated, scheduled, and instant flows*); demo users use the self-service premium trials.

## Gotchas

- **Secret environment variables only reach flows and a connector's Security tab.** Learn: they are not available in other customisations or via the API, and not in the flow dynamic content picker. So the Claude key goes Key Vault, flow (unbound action
  `RetrieveEnvironmentVariableSecretValue`, secure outputs), connector parameter. The app never sees it.
- **Key Vault for secret variables** (Learn): register the `Microsoft.PowerPlatform` provider, use Azure RBAC, give *Key Vault Secrets User* to the Dataverse service principal (`00000007-0000-0000-c000-000000000000`) and to the user who creates the variable.
- **Azure OpenAI with Entra needs a custom subdomain** and the *Cognitive Services OpenAI User* role (id `5e0bd9bd-7b93-4f28-af87-19fc36ad61bd`, on Learn's built-in roles page). `disableLocalAuth` is on, so a key is not an option.
- **The default model is already deprecated.** `gpt-4.1-mini` 2025-04-14 was available in Sweden Central (Standard) but its lifecycle was "Deprecated" with retirement 2027-04-14 when researched. It is a Bicep parameter.
- **`anthropic-version`:** Anthropic's versioning page lists `2026-10-21`, `2023-06-01` and `2023-01-01`; the repo uses `2026-10-21` and exposes it as a parameter. The Claude model id `claude-haiku-5-5` is the one a pricing page showed on the research day; treat it as a parameter.
- **AI Builder prompts from Power Fx:** Learn documents `'<Prompt>'.Predict(<text>)` returning a record with `.text`; it does not document image arguments or the JSON output option, so the prompt returns JSON as text and the app sends text only.
- **A custom connector body with mixed `content` types** (string for text, array for photos) is hard to model in Power Fx tables, so the Azure OpenAI connector is text-only in the app and photos go through the Claude flow as base64.
- **Custom code in connectors** was considered for the body shaping and not used: Learn gives conflicting limits (5 seconds on one page, 2 minutes on another) and the code can only be tested here with stubs.
- **Models can echo instructions in the notes.** The golden set has one prompt-injection case, and the system prompt says to treat notes and photos as data.
- **Power Fx engine quirks:** `Set` swallows errors inside `IfError` (use `With` + `IfError`); `IfError(value, fallback)` takes two arguments; `Min(1, Blank())` is 1 so test `IsBlank` first. App.Formulas in several files are joined by the test loader like pasted text.

## Unverified

- Real behaviour of all three routes: no model was called. No accuracy, latency or cost figure exists in this repo.
- The Bicep was not deployed (API versions `2024-10-01` for Cognitive Services, `2023-07-01` Key Vault, `2022-04-01` role assignments); the Key Vault Secrets Officer (`b86a8fe4-...`) and Secrets User (`4633458b-...`) role ids were not re-checked against Learn.
- That the connector wizard accepts the OAuth settings as written (the `.default` scope, `IsFirstParty`, the resource URL) and the Power Fx call shapes `ContosoFoundryTriage.TriageFinding({...})` and `ClaudeTriage.Run(notes, photo, model)` with outputs `text` and `error`.
- The `RetrieveEnvironmentVariableSecretValue` action and parameter names in the flow, and that "secure data" is respected as written.
- That `Patch` of the extension columns works with the display names `AI severity`, `AI provider`, ... and the choice name `AI severity (Inspection items)`; that the extension imports cleanly on top of the base.
- Photos in the canvas via `JSON(selectedItem.Photo, JSONFormat.IncludeBinaryData)` (the data URL is split on the comma in `PhotoBase64`); photo size limits per vendor for large camera pictures.
- Whether the AI Builder prompt can take the Photo input in a Power Fx call.

## References

- Use your prompt in Power Apps (`.Predict`, `.text`): https://learn.microsoft.com/ai-builder/use-a-custom-prompt-in-app
- Licensing and Copilot Credits (AI Builder rates, testing is free): https://learn.microsoft.com/ai-builder/message-management
- Environment variables for Azure Key Vault secrets: https://learn.microsoft.com/power-apps/maker/data-platform/environmentvariables-azure-key-vault-secrets
- Key Vault errors and roles for environment variables: https://learn.microsoft.com/troubleshoot/power-platform/dataverse/working-with-solutions/environment-variable-key-vault-auth-error
- Custom connectors, create from scratch: https://learn.microsoft.com/connectors/custom-connectors/define-blank
- Use custom code in a custom connector: https://learn.microsoft.com/connectors/custom-connectors/write-code
- Limits of automated, scheduled, and instant flows (custom connector needs premium or trial): https://learn.microsoft.com/power-automate/limits-and-config
- Azure built-in roles (Cognitive Services OpenAI User): https://learn.microsoft.com/azure/role-based-access-control/built-in-roles
- Foundry tools authentication using Entra ID: https://learn.microsoft.com/dotnet/ai/azure-ai-services-authentication
- Anthropic API versioning: https://platform.claude.com/docs/en/api/versioning
- Blog Complete Guide (AI Builder integration): https://www.devladlog.com/articles/powerapps/2026-03-11-ai-builder-integration-complete-guide-2026/
