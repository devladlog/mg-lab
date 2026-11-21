# Demo shot list - Copilot & AI #20 Microsoft Foundry Agent Service with Multiple Models

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Tenant / accounts | Momento Galático lab tenant, `labadmin` (Owner of the lab Azure subscription) for the portal and the run. No M365 licence is involved |
| Azure resources | Resource group `rg-mglab-copilot-ai-20`, **Sweden Central** (LAB.md: Azure OpenAI region) unless the model check below says otherwise, deployed from `src/infra/main.bicep`: (1) Microsoft Foundry resource, kind `AIServices`, SKU `S0`, Entra-only (local auth disabled); (2) one project; (3) 2 or 3 model deployments, SKU `GlobalStandard`, capacity 1 (the unit is not verified here: read it in the portal), one of them `gpt-4.1-mini`; (4) an Application Insights resource connected to the project for tracing (portal steps in the Learn quickstart, "Connect Application Insights for agent tracing") |
| Estimated cost | **Not verified:** pricing is per token and per model, and is not copied here. A run sends 3 models x 5 tasks x 1 repeat = 15 short requests (a few thousand tokens per model); read each model's price on the Azure pricing page before recording and write the figure here. App Insights ingestion is minimal for this volume. The lab budget `mglab-monthly` (EUR 30) alerts at 50/80/100 %. Delete the resource group right after |
| Licences | none beyond the subscription. Models from other publishers may need Marketplace terms or have quota limits per subscription type: check in the portal first (open point 1) |
| Recording machine | Windows lab laptop: browser on the Foundry portal as `labadmin`, PowerShell 7 or bash terminal, Azure CLI signed in off camera (`az login`), Python 3.10+, Bicep CLI |

## What was verified where

| Step | Build container (Linux) | Needs the lab tenant |
|---|---|---|
| Scoring, runner, routing, report, CLI | yes: pytest with a scripted fake backend | - |
| Call shapes of the real SDK (`azure-ai-projects` 2.11.0) | yes: signatures bound against the installed package | **first real run** |
| `main.bicep` / `main.bicepparam` | `bicep build` and `build-params` pass | **`az deployment group create`**: deployment succeeds, model names/versions/regions accepted |
| Portal screens, traces, real scores | no | **record them** |

Open points that change the script: (1) which 2 or 3 models can be deployed in the lab subscription (region, quota,
Marketplace terms): if only OpenAI-format models are available, say so on camera and compare two of them (for example a mini and
a larger model); the script claims "several models", not any specific publisher; (2) whether `agents.create_version` accepts the
agent names the tool generates; (3) whether tracing shows token counts for these requests; (4) whether `--keep-agents` agents
appear in the portal Agents page as in the script.

## Prerequisites and setup
1. `az login` off camera; choose the lab subscription. Create the group: `az group create -n rg-mglab-copilot-ai-20 -l swedencentral`.
2. Find deployable models: in the Foundry portal model catalogue, filter by agent support (Learn links the catalogue with `capabilities=agentsv2`), pick 2 or 3 and
   note each model's **Format, Name, Version** (after the account exists: `Get-AzCognitiveServicesAccountModel -ResourceGroupName rg-mglab-copilot-ai-20 -AccountName <account>`).
   Edit the `deployments` parameter in a copy of `main.bicepparam` (keep `gpt-4.1-mini` if it deploys).
3. Deploy: `az deployment group create -g rg-mglab-copilot-ai-20 -f src/infra/main.bicep -p accountName=<unique-name> deployments=@deployments.json`
   (or `-p main.bicepparam`). Note the `projectEndpoint` and `projectResourceId` outputs. If a deployment fails on quota or region, change the model: do not edit the script around it.
4. Role: give `labadmin` **Foundry User** on the project (`az role assignment create --assignee <labadmin object id> --role "Foundry User" --scope <projectResourceId>`;
   if the CLI does not know the new name use the earlier name, Azure AI User; Owner on the subscription alone is not the documented requirement for creating agents).
5. Connect Application Insights to the project (portal, per the Learn quickstart) and make sure `labadmin` can read traces.
6. Copy `src/samples/config.json` and `tasks.json` next to a working folder; in `config.json` put the real deployment names, and the real per-token prices from the Azure pricing page for each (so the cost column means something). `python -m pip install -r src/requirements.txt`; `python -m pytest -q`.
7. `export FOUNDRY_PROJECT_ENDPOINT=<projectEndpoint>`. First run **off camera** (`python -m foundry_multimodel run ... --out safety.json`) and keep it as the safety take. Read the failures: a model that fails because of the *tool* (bad JSON extraction rule) is a script bug to fix, not a lesson.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `models-screen` | `screens/foundry-models.jpg` | Foundry portal, the project, Models + endpoints: all deployments of the run with their deployment names. Mask subscription/resource names that contain the tenant name |
| `report-screen` | `screens/run-report.jpg` | Terminal: `python -m foundry_multimodel plan --config config.json --tasks tasks.json`, then `run ... --out results.json --keep-agents`. Visible: plan line, scorecard table, routing lines, failed checks. Real output only. If every model scores 1.00 on everything, say the tasks were too easy and add one harder task before publishing; if a deployment errors, show the setup-errors line |
| `agents-screen` | `screens/foundry-agents.jpg` | Foundry portal, Agents: one `mglab-ep20-<model>` agent per model, open one to show model + instructions. Do this before tear-down |
| `trace-screen` | `screens/foundry-trace.jpg` | Foundry portal, Tracing (Application Insights): one request from the run with duration and token counts. If tracing is not connected or shows nothing, drop the scene and its narration |

Optional extra take (not in the script): in the portal, change one agent's model to another deployment and ask the same question
in the playground, to show "swap the model without changing your agent code".

## Tear-down
1. Delete the resource group, which removes the project, its agents and the deployments: `az group delete -n rg-mglab-copilot-ai-20 --yes --no-wait`.
2. Confirm in the portal (Resource groups) that `rg-mglab-copilot-ai-20` is gone; Cognitive Services accounts are normally soft-deleted, which can block reusing the account name: if the next deployment complains, list deleted accounts and purge this one (`az cognitiveservices account list-deleted`, `az cognitiveservices account purge`; not verified on Learn in this build).
3. Remove the `Foundry User` role assignment if it was scoped outside the resource group (it goes with the group otherwise).
4. Delete `results.json`, `safety.json` and the copied config (they contain the resource name); do not commit them.
