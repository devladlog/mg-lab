# Demo shot list — DEVLADLOG Power Apps #14, AI models in both apps

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | none |
| Azure | resource group **`rg-mglab-powerapps-14`**, region **Sweden Central** (Azure OpenAI Standard deployment; West Europe is fine for the vault but keep one region), deployed by `src/infra/main.bicep`. Resources and SKUs below. Deleted in tear-down |
| Tenant environment | Power Platform **`DEV`** with *Contoso Inspections* (episodes 11 and 12) and the new solution *Contoso Inspections AI* (5 columns on Inspection item, 1 secret environment variable, 1 flow, 2 custom connectors, 1 AI Builder prompt in Part B, 1 custom page). Entra: one app registration `contoso-lab-foundry-connector` (name is fictional) |
| Lab users | `labadmin` builds. `alex.demo` runs the canvas app. `sam.demo` runs the model-driven app. Alex and Sam each start the self-service **Power Apps Premium trial** (custom connectors and Dataverse are premium) the first time: say so on camera |
| Licences / trials | Power Apps Premium self-service trial for the demo users; Power Automate Premium self-service trial for `labadmin` (the flow uses a custom connector, Learn: "You must have a premium or trial license to run any flow that uses a custom connector"). **No AI credits and no pay-as-you-go plan** (`series/LAB.md`): the **AI Builder route cannot run in an app**; it is shown in the prompt builder, where testing is free (Learn: *Licensing and Copilot Credits*, rule 4) |
| **Needs the owner** | An **Anthropic API account with a small prepaid balance** and one API key, created by the owner and typed by the recorder off camera. Not in `series/LAB.md` today. Without it, skip the Claude route and say so |
| Recording machine | Windows lab laptop: Azure portal, maker portal, Power Apps Studio and the running apps in the browser (use `pipeline/mask.js`); WSL terminal with Python 3, .NET 10 SDK, `pac` (offline only), `az` and `bicep` |

### Azure resources and estimated cost for a one-day recording window

| Resource | SKU | Cost note (**not verified**: read the Azure pricing pages on the day) |
|---|---|---|
| Azure OpenAI account | S0, custom subdomain, local auth disabled | no standing fee expected for the account itself |
| Model deployment `triage` | Standard, capacity 10 (thousand tokens per minute), model `gpt-4.1-mini` 2025-04-14 (**lifecycle "Deprecated", retirement 2027-04-14** when researched: use the `modelName`/`modelVersion` parameters for a current model if the deployment is refused) | pay per token; the 13-note run is about 6,500 input and 800 output tokens, so expect cents |
| Key Vault | Standard, Azure RBAC, soft delete 7 days | per-operation pricing, expect cents |
| Role assignments | lab user: Cognitive Services OpenAI User + Key Vault Secrets Officer; Dataverse service principal: Key Vault Secrets User | free |

Budget alert `mglab-monthly` is EUR 30. The Anthropic side is billed by Anthropic per token (about 6,500 input tokens for the run): read their price page the day you record.

Everything under `src/` and `tests/` was built and tested locally: `cd tests/python && python3 -m pytest -q` (see README for the count) and
`cd tests/ContosoInspections.AI.Tests && dotnet test -m:1` (see README). **Every step marked "needs tenant" or "needs Azure" has never been run.** In particular: the
Bicep was only compiled and linted, never deployed; the connector files were only validated as Swagger 2.0, never imported; the flow file was never imported;
the extension solution was only unpacked and packed with `pac`, never imported; the canvas and page call shapes were only run against test doubles.

Never run `pac auth`. Use the browser for imports and `az` only on the recording laptop, off camera, for the deployment and the token.

## Prerequisites

| What | Notes | Cost |
|---|---|---|
| Episodes 11 and 12 solutions in `DEV` | the AI columns extend `cin_inspectionitem` | existing |
| `Microsoft.PowerPlatform` resource provider registered on the lab subscription | Learn: required for Key Vault secret environment variables | 0 |
| An Entra app registration for the Foundry connector | redirect URI from the connector's Security tab; a client secret typed in the portal, never saved to a file | 0 |
| The owner's Anthropic API key | typed off camera | per token |

## Setup (off camera)

1. **Local checks.** Both test commands above. Delete `bin`, `obj`, `__pycache__`, `.pytest_cache` afterwards.
2. **Deploy Azure (needs Azure).**
   ```bash
   az group create -n rg-mglab-powerapps-14 -l swedencentral
   az deployment group create -g rg-mglab-powerapps-14 -f src/infra/main.bicep -p principalId=$(az ad signed-in-user show --query id -o tsv)
   ```
   Add `-p dataverseServicePrincipalId=<object id of the Dataverse enterprise app>` to grant the vault role in one go, otherwise grant *Key Vault Secrets User* to
   the application with id `00000007-0000-0000-c000-000000000000` in the portal (Learn lists both). If the deployment is refused for the model, check the catalogue and pass
   `-p modelName=... modelVersion=...`.
3. **Run the golden set against Azure OpenAI (needs Azure).**
   ```bash
   export AZURE_TOKEN=$(az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv)
   python3 src/eval/evaluate.py run --route foundry --endpoint https://<account>.openai.azure.com --model triage --token-env AZURE_TOKEN --price-in <usd per M> --price-out <usd per M> --save /tmp/foundry.jsonl
   ```
   The prices come from the Azure pricing page on the day. Do not show the token or the endpoint.
4. **Put the Claude key in the vault, off camera (needs Azure and the owner's key).**
   ```bash
   read -rs KEY && az keyvault secret set --vault-name <vault> --name anthropic-api-key --value "$KEY" >/dev/null; unset KEY
   export ANTHROPIC_API_KEY=...   # typed off camera in a fresh shell; the same key, for evaluate.py only
   python3 src/eval/evaluate.py run --route claude --model <current Claude model id> --key-env ANTHROPIC_API_KEY --price-in <usd per M> --price-out <usd per M> --save /tmp/claude.jsonl
   ```
   The model id **claude-haiku-5-5** is what a pricing page showed on the research day; it is a parameter everywhere (`ClaudeModel` in the app formulas, the flow input, `--model`).
   `anthropic-version` is `2026-10-21` (Anthropic's versioning page lists 2026-10-21, 2023-06-01 and 2023-01-01).
5. **Extension solution (needs tenant).** `python3 src/solution/build_extension.py --zip /tmp/cin-ai.zip` (or `pac solution pack` on `src/solution/ContosoInspectionsAI`, offline),
   then Solutions > Import in the browser into `DEV`. Open Inspection item > Forms > add the five *AI ...* columns to the main form and a view. Publish.
6. **Foundry connector (needs tenant + Azure).** Solutions > Contoso Inspections AI > New > Automation > Custom connector > Import an OpenAPI file: `src/connectors/foundry/apiDefinition.swagger.json`.
   General: host = the account's `<name>.openai.azure.com`. Security: OAuth 2.0, identity provider Azure Active Directory, client id and secret of the app registration (typed off camera),
   resource URL `https://cognitiveservices.azure.com`, add the redirect URL to the app registration. Test tab: create a connection as `alex.demo`, call `TriageFinding` with model `triage`.
   **Unverified:** that the `.default` scope in `apiProperties.json` is what the wizard wants (the wizard may take the resource URL instead), that blank/extra fields in the body are accepted, and
   the `TriageFinding` Power Fx call shape in `TriageScreen`.
7. **Claude connector and flow (needs tenant).** Import `src/connectors/anthropic/apiDefinition.swagger.json` as a second custom connector (no authentication). In the solution add an
   environment variable **`cin_AnthropicApiKey`**: type Secret, store Azure Key Vault, your subscription id, `rg-mglab-powerapps-14`, the vault name, secret `anthropic-api-key`. Then build the
   flow `ClaudeTriage` as `src/flows/ClaudeTriage/workflow.json` describes (button trigger with `notes`, `photo`, `model`; Dataverse *Perform an unbound action* `RetrieveEnvironmentVariableSecretValue`;
   the connector action; two *Respond to a PowerApp* actions) and turn on *Secure inputs* and *Secure outputs* where the JSON says so. Learn: a secret environment variable does not appear in the
   dynamic content picker, so use the unbound action. **Unverified:** the exact action and parameter names for `RetrieveEnvironmentVariableSecretValue`, and that Power Apps sees the flow's
   outputs as `text` and `error`.
8. **AI Builder prompt (needs the tenant; credits only to run in an app).** AI hub > Prompts > Build your own prompt, from `src/prompts/aibuilder-prompt.md`: inputs Notes (text) and Photo
   (image), output JSON with `src/eval/sample-output.json`. Test it in the builder with each golden note and a real photo from the lab: testing there is free. Type the 13 answers into
   `/tmp/aibuilder.jsonl` (lines `{"id": "g01", "text": "<what the builder returned>"}`) and score them with `evaluate.py score --answers /tmp/aibuilder.jsonl`. Do not type answers from memory.
9. **Canvas app (needs tenant).** Add the connectors and the flow as data sources (and the prompt for Part B only). Paste the formulas from `src/app/Src/App.ai-formulas.pa.yaml` and
   `App.ai-prompt.pa.yaml` into App > Formulas and the screen from `TriageScreen.pa.yaml`; add a button on the item screen: `Navigate(TriageScreen)`. Part B is the AI Builder route,
   which needs credits: leave that route out of the recording (the dropdown can stay) and say it.
10. **Model-driven app (needs tenant).** In the Inspection Back Office app add the custom page from `src/custompage/Src` (App.pa.yaml and TriagePage.pa.yaml, named *Item AI triage*) and the command
    *AI suggestion* from `src/custompage/commands.yaml` on the Inspection item main form.

## Screens to record (match the `screen` scenes)

### Screen 1: `screens/azure-foundry.jpg` (scene *azurescreen*)
Azure portal > `rg-mglab-powerapps-14`: the resource list, then Azure OpenAI > Model deployments (`triage`, Standard, capacity 10), then Access control (IAM). Mask subscription id, tenant name, avatar.

### Screen 2: `screens/claude-secret-flow.jpg` (scene *claudescreen*)
make.powerapps.com > Contoso Inspections AI: environment variable `cin_AnthropicApiKey` (Secret, Azure Key Vault, no value visible), then the flow ClaudeTriage > Run history > one succeeded run: Get key
outputs and the Triage inputs show as hidden. Mask the vault name and the subscription id. If the key is visible anywhere, stop, rotate it and re-record.

### Screen 3: `screens/eval-run.jpg` (scene *evalscreen*)
WSL terminal: the two `evaluate.py run` results (accuracy, invalid, under calls, tokens, estimated cost) and the `score` result for the AI Builder answers. Read the numbers as they are: with 13 examples
the differences are noise-sized, so do not declare a winner.

### Screen 4: `screens/canvas-triage.jpg` (scene *appscreen*)
Field app as `alex.demo` (InPrivate): item "Fire door wedged open" > AI suggestion > Azure OpenAI > Suggest > banner and summary > Save suggestion; then Claude. Then in the model-driven app as `sam.demo`,
the same item with the five AI columns filled and Severity untouched. Also open the custom page via *AI suggestion* once. Mask the environment name and avatars.

## What not to claim

- No accuracy claim before the real run; none for AI Builder in the app (it cannot run without credits).
- No price from this repo. Read each provider's page on the day.
- The photo route: Learn documents only a text argument for `.Predict`; photos go through the Claude flow (base64) in the app. The Azure OpenAI connector is text only in the app (the swagger takes a string `content`).
- Gemini is not used; the non-Microsoft model is Claude.

## Masking notes

Subscription id, tenant name and domain, vault name, account endpoint, app registration ids, environment name and URL, avatars (use `pipeline/mask.js`). Never show a token, a client secret or the API key.
All names are fictional (`contoso-lab-foundry-connector`, Alex Demo, Sam Demo).

## Tear-down

1. `az group delete -n rg-mglab-powerapps-14 --yes --no-wait`, then purge the soft-deleted vault (`az keyvault purge --name <vault> --location swedencentral`) and the deleted Azure OpenAI account
   (`az cognitiveservices account purge --name <account> --resource-group rg-mglab-powerapps-14 --location swedencentral`) if you want the names back.
2. Revoke or delete the Anthropic API key in Anthropic's console. Remove the client secret and the app registration in Entra.
3. In DEV: delete the solution *Contoso Inspections AI* (removes the connectors, the flow, the variable; the 5 columns go with it: warn first, they hold the recorded rows), the AI Builder prompt, the connections, and the added canvas screen and formulas.
   Remove the page and command from the back-office app.
4. Delete the recorded test rows. Stop the self-service trials only if no other episode needs them.
5. Delete local `bin`, `obj`, `__pycache__`, `.pytest_cache`.
