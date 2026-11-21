# Demo shot list - Copilot & AI #21 Claude in the Microsoft Ecosystem

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Tenant / accounts | Momento Galático lab tenant. `labadmin` (Global Administrator, Owner of the lab Azure subscription, Copilot Studio trial licence) for every screen. Passwords typed off camera |
| Microsoft 365 admin centre | Needs an AI Administrator or Global Administrator (Learn). The tenant is in **Portugal (EU)**, so Anthropic is **off by default** ("No users"). The recording turns it on for the lab users: **the owner must approve this first** (Claude is processed outside the EU Data Boundary) and tear-down turns it off again |
| Power Platform admin centre | Allow external LLMs for the `DEV` environment (or an environment group) so Claude shows in Copilot Studio (Learn: "Allow external language models for generative responses"). Turned back off in tear-down |
| Azure resources | Resource group `rg-mglab-copilot-ai-21`, **Sweden Central** (Learn's starter kit says `eastus2` and `swedencentral` host Haiku, Sonnet and Opus; **not verified for the 5.5 models**: check the live catalogue in the portal and change the region if needed), deployed from `src/infra/main.bicep`: (1) Microsoft Foundry resource, kind `AIServices`, SKU `S0`, Entra-only; (2) one project; (3) two Claude deployments, `GlobalStandard`, capacity 25 (25,000 tokens per minute, Learn's QuickStart value; **not verified** that the lab subscription's default quota allows it: lower it if the deployment reports quota) |
| Estimated cost | **Not verified:** billing is per token in Claude Consumption Units on the Azure invoice at Anthropic's published rates (https://aka.ms/ccu-pricing); read the Sonnet 5.5 and Haiku 5.5 rates there on the recording day and write the figure here. The run sends fewer than 30 short requests. Budget `mglab-monthly` (EUR 30) alerts at 50/80/100 %. Idle Claude deployments do not incur charges (Learn), the resource group is deleted anyway |
| Licences | Azure: a **paid subscription with an active pay-as-you-go method** (the lab subscription is pay-as-you-go: eligible if its billing country is in Anthropic's supported regions, **to be checked**: https://aka.ms/supported_anthropic_regions). Contributor or Owner on the resource group and Azure Marketplace permission to subscribe to Foundry Models from partners. **Microsoft 365 Copilot (the add-on, US$30 per user per month paid yearly, en-US page, see episode 1) is NOT licensed and not bought**: Researcher, Copilot in Excel/Word/PowerPoint and Copilot Cowork with Claude are therefore not recorded; the script only states what Learn says. Copilot Studio: trial licence on `labadmin`; agent usage can consume Copilot Credits (Learn), nothing is published |
| Attestation | `main.bicepparam` has `organizationName`, `countryCode`, `industry`. They must describe the real organisation using Claude (Learn). Deploying accepts the Anthropic Marketplace terms on its behalf: the owner approves this once |
| Recording machine | The Windows lab laptop: Edge/Chrome on the lab tenant for the three portal screens; PowerShell 7 terminal (dark theme, 18 pt) for the Python run; Python 3.10+, Bicep CLI, Azure CLI signed in off camera; **Claude Code** installed with the native installer (`irm https://claude.ai/install.ps1 \| iex`) for the last screen |

## What was verified where

| Step | Build container (Linux) | Needs the lab tenant |
|---|---|---|
| Client factory, tool-use loop, fallback, env activator | yes: 31 pytest tests, the real `anthropic` SDK against a scripted HTTP endpoint | **first real call** to a deployment |
| `main.bicep` / `main.bicepparam` | `bicep build` and `build-params` pass; compiled output checked for `Anthropic` and `modelProviderData` | **`az deployment group create`**: accepted model names, `version` handling, quota, region, attestation |
| Whether Claude ignores the injected supplier note | no (model behaviour) | **record the real result**, whatever it is |
| Admin centre, Copilot Studio selector, Foundry portal, Claude Code `/status` | no | **record them** |

Open points that change the script: (1) whether the lab subscription is eligible and has Claude quota (Learn: a default quota of 0 gives a
"subscription eligibility error"): if not, the three Foundry/terminal screens cannot be recorded and the owner must fix eligibility first; (2) the
`version` to use for the Hosted-on-Azure models (read it in the portal catalogue or the account's model list, put it in `main.bicepparam`; if the deployment
fails without it, set it); (3) whether Copilot Studio shows Claude in `DEV` for `labadmin` (otherwise drop `studio-screen` and its narration); (4) the
Claude model names in the narration (Sonnet 5.5, Haiku 5.5, Opus 5.5, the four retiring on 15 February 2027) against the Learn page on the recording day.

## Setup
1. `az login` off camera, choose the lab subscription. `az group create -n rg-mglab-copilot-ai-21 -l swedencentral`.
2. In the Foundry portal catalogue (Build > Models, New Foundry on) open Claude Sonnet 5.5 and Haiku 5.5: check **Hosted on** (Azure), availability in the region, and
   the Marketplace dialog text. Note the version if shown.
3. Edit a copy of `src/infra/main.bicepparam`: real attestation values, deployment names, optional `version`.
   `az deployment group create -g rg-mglab-copilot-ai-21 -f src/infra/main.bicep -p main.bicepparam principalId=<labadmin object id>`.
   Model deployments can keep provisioning after a gateway timeout: check the deployment state in the portal before re-running (Learn).
4. `cd` into the episode folder, `python -m pip install -r src/requirements.txt`, `python -m pytest -q` (31 passed).
5. `$env:ANTHROPIC_FOUNDRY_RESOURCE = "<resource name>"` (the name only). First run **off camera**: `cd src; python -m claude_ms triage --deployment claude-sonnet-5-5` and keep the
   output as the safety take. A 401/403 means the token scope or the role (Cognitive Services User, allow a few minutes after the assignment).
6. Microsoft 365 admin centre: approved by the owner, set Anthropic on for the lab users only (do it **on camera** in the `admin-screen` scene, after showing the default).
7. Power Platform admin centre: allow external LLMs for `DEV`.
8. `cd src; python -m claude_ms code-env --resource <name> --sonnet claude-sonnet-5-5 --haiku claude-haiku-5-5 | Invoke-Expression`, then `claude` once off camera to be sure `/status` works.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `admin-screen` | `screens/admin-center-anthropic.jpg` | admin.microsoft.com, Copilot > Settings > View all > AI providers operating as Microsoft subprocessors > Anthropic: first the default state (no users), then "Choose who can access Anthropic models" set to the lab users and saved. Mask the tenant name |
| `studio-screen` | `screens/copilot-studio-model.jpg` | Copilot Studio, an agent using the Microsoft Copilot harness, the model selector open with the Claude entries. Optional: if no Claude entry appears, record the Power Platform admin centre setting instead and change the narration |
| `deploy-screen` | `screens/foundry-claude-deployments.jpg` | Foundry portal, the Claude deployments of `rg-mglab-copilot-ai-21`, then one deployment's Details: target URI and status Succeeded. Mask resource names that contain the tenant name |
| `triage-screen` | `screens/claude-triage-run.jpg` | Terminal: `python -m claude_ms triage --deployment claude-sonnet-5-5`. Visible: `resource=... auth=entra`, the `tool_use` line, the answer, the turns/tokens line. Real output; run it twice and keep the better take only if both are real |
| `claudecode-screen` | `screens/claude-code-status.jpg` | Terminal: `claude`, `/status` showing API provider Microsoft Foundry, resource and model; one short prompt; then the Foundry Monitor tab of the deployment showing the request |

Optional extra take (not in the script): `python -m claude_ms fallback --deployments does-not-exist,claude-haiku-5-5 --prompt ...` shows the 404 being raised on purpose
(a wrong deployment name is not hidden), then a real 429 test is not planned (no way to trigger it safely).

## Tear-down
1. `az group delete -n rg-mglab-copilot-ai-21 --yes --no-wait`. The Foundry account is soft-deleted and can hold Claude quota for up to 48 hours: `az cognitiveservices account list-deleted -o table`, then
   `az cognitiveservices account purge` for this one (Learn, starter kit troubleshooting).
2. Microsoft 365 admin centre: set Anthropic back to **no users** (the lab's default for an EU tenant) unless the owner wants it kept. Power Platform admin centre: turn the external LLM setting back off for `DEV`.
3. Remove the Claude Code environment variables from the terminal profile; `Remove-Item Env:CLAUDE_CODE_USE_FOUNDRY, Env:ANTHROPIC_FOUNDRY_RESOURCE, Env:ANTHROPIC_DEFAULT_*`.
4. Delete the copied `main.bicepparam` and any saved outputs (they contain the resource name). Do not commit them.
