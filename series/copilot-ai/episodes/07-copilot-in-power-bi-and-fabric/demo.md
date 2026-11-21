# Demo shot list - Copilot & AI #7 Copilot in Power BI and Fabric

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Tenant | Momento Galático lab tenant. `labadmin` (Global Administrator, therefore Fabric administrator) is the recording account. The Fabric + Power BI 60-day trial (West Europe) is used **only** for screen `trial-no-copilot` |
| Licences | `labadmin` needs a Power BI Pro licence or a Power BI individual trial to create a workspace and publish (Learn: capacities below F64 need Pro or PPU to view or create content). Check in the Microsoft 365 admin center; the Microsoft 365 Business Standard and E5 trials do not include Power BI Pro unless assigned. No Microsoft 365 Copilot licence is used |
| **Paid capacity (owner decision)** | **Fabric capacity F2**, resource group `rg-mglab-copilot-07`, West Europe, name `mglabcopilotf2`, capacity administrator `labadmin`. **Cost: 0.395 EUR per hour while running** (Azure Retail Prices API, West Europe, 0.1975 EUR per CU hour, 2 CU, read 21 Nov 2026; recheck in the Azure pricing calculator). Plan 3 hours of running time: about 1.2 EUR. Left running all month it would be about 288 EUR against the 30 EUR `mglab-monthly` budget, so **pause it after every take** and delete the resource group in tear-down. Copilot adds no separate meter: it uses the capacity units (Learn) |
| Lead time | **Create the F2 at least 24 hours before recording.** Learn: after buying or scaling a capacity, Copilot can take up to 24 hours to recognise it |
| Azure resources | `rg-mglab-copilot-07`: Microsoft.Fabric/capacities F2 (West Europe). Nothing else |
| Recording machine | Windows lab laptop: Power BI Desktop (current release; *Prep data for AI* is a preview feature, Options > Preview features), Edge/Chrome profile for `labadmin`, Windows Terminal with PowerShell 7 and Python 3.10+, `Az.Accounts` for the capacity script |
| Data | Star-schema CSV files of Power BI episode 1 in `C:\MGLab\power-bi\star\` (see that episode's demo.md), uploaded again to a Fabric lakehouse for the notebook screen |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the lab tenant / Windows |
|---|---|---|
| `lint`, `describe`, `golden`, `cost` | yes: 25 pytest tests, including the real Contoso Bikes model before and after | - |
| `Get-FabricCopilotCapacity.ps1` | yes: 15 Pester tests with a mocked `Invoke-RestMethod` (paging, personal workspaces, trial, no capacity, invisible capacity) | **first real run** against the tenant |
| The prepared copy opens in Power BI Desktop, `Orders Shipped` evaluates, `Date`/ship relationship works | no (TMDL syntax follows Learn; no Desktop in the container) | **check before recording** |
| Everything Copilot answers, the Prep data for AI dialogs, the Fabric notebook | no | **record it** |

Open points to settle on the tenant (each can change the script):
1. Does the Fabric **trial** workspace show Copilot at all? Learn says no on four pages and yes on one (Data Engineering
   overview). Record what really happens. If Copilot works on the trial, stop: rewrite scene `trial-screen`, the `needs`
   slide and the README, and the F2 is no longer needed for this episode (it would still be needed for Premium/PPU users).
2. Does Copilot ask "which country" after the instructions? Does it use `[Orders Shipped]`? Whatever it does is the
   take; if it still answers wrongly, keep it and say so (Learn: nondeterministic, no guarantee).
3. Orders shipped in January 2026 (9) are outside the date table: if Copilot reports 149 for June 2025 it is right;
   do not extend the date table on camera.

## Prerequisites
- Terminal: dark theme, 18 pt, 1600x900, prompt `PS> `. Browser dark theme, 125 %.
- `python -m pip install -r src/requirements.txt`; `python -m pytest -q` -> `25 passed`.
- Day before: create the F2 (Setup 1), wait 24 hours, then do Setup 2 to 7 and rehearse once with prompts written down.

## Setup
1. **Azure portal** as `labadmin`: create resource group `rg-mglab-copilot-07` (West Europe), then *Microsoft Fabric*
   > *Fabric capacities* > Create: name `mglabcopilotf2`, size **F2**, region West Europe, administrator `labadmin`.
   Tag `purpose=mglab-copilot-ep07`. Note the estimated price shown in the portal. Leave it **Paused** until a take.
2. **Fabric admin portal** > *Tenant settings* > *Copilot and Azure OpenAI Service*: confirm *Users can use Copilot and other
   features powered by Azure OpenAI* is on (default). Learn requires the cross-geo setting only for capacities outside
   the US and EU data boundary; West Europe needs no change. Change nothing; screenshot for the notes.
3. **Workspaces**: `Contoso Copilot Lab` assigned to `mglabcopilotf2` (Workspace settings > License info > Fabric capacity)
   and `Contoso Trial Lab` assigned to the trial capacity.
4. **Working copy of the model** (Windows): copy `series/power-bi/episodes/01-data-modeling-star-schema/src` to
   `C:\MGLab\work\copilot-07\before`. In `expressions.tmdl` the `DataFolder` parameter is `C:\MGLab\power-bi\star\`
   (change it if the CSV folder is elsewhere; keep the trailing backslash).
5. **Lint and prepare** (terminal in `src` of this episode): `python -m copilot_pbi lint <before>\ContosoSales.SemanticModel`
   -> 0 errors, 7 warnings. `python -m copilot_pbi describe <before>\ContosoSales.SemanticModel data\descriptions-contoso-bikes.json --out C:\MGLab\work\copilot-07\after\ContosoSales.SemanticModel`;
   copy `ContosoSales.pbip` and `ContosoSales.Report` next to it. Lint the result with
   `--instructions data\ai-instructions-contoso-bikes.md --verified data\verified-answers-plan.json --fail-on info` -> exit 0.
6. **Desktop**: open both projects once, add a clustered bar chart *Sales Amount by Category* and a line chart *Margin %
   by Year Month* to the page (needed for verified answers), save. Check `Orders Shipped` shows 149 for June 2025 in
   a table by `Date[Year Month]`. If Desktop rejects the prepared copy, fix the TMDL there and note it.
7. **Golden answers on a second monitor**: `python -m copilot_pbi golden`.
8. **Fabric lakehouse** in `Contoso Copilot Lab`: `lh_contoso`, upload the five CSVs, *Load to tables*; create notebook
   `nb_copilot_demo` attached to it.

## Screens to capture (match the `screen` scenes in script.yaml)
Resume the F2 (Azure portal > the capacity > Resume) before each take, pause it right after.

| Scene id | File | What must be on screen |
|---|---|---|
| `trial-screen` | `screens/trial-no-copilot.jpg` | Fabric portal as `labadmin`, workspace `Contoso Trial Lab` (trial capacity, *License info*), a report open, **the real Copilot state** (button missing, or the message that no workspace has the necessary capacity). Mask the tenant name |
| `before-screen` | `screens/copilot-before.jpg` | Desktop, `before` project, Copilot workspace = `Contoso Copilot Lab` (Settings gear), skill picker *Answer questions about the data*. Prompts: "Show sales by country for 2025", "How many orders were shipped in June 2025?". Open *How Copilot arrived at this*. Validated: store country vs customer country totals differ; 149 shipped vs 145 ordered |
| `prep-screen` | `screens/prep-data-ai.jpg` | Desktop, `after` project: Home > *Prep data for AI* > *Add AI instructions* with the text pasted (turn on Q&A first if the tabs are disabled); then *Simplify data schema*; then a verified answer on the bar chart with 3 trigger phrases from the plan; Apply. Then the Properties pane of `[Sales Amount]` showing the description |
| `after-screen` | `screens/copilot-after.jpg` | Same prompts after closing and reopening the Copilot pane, plus "Which product category made the most margin in 2025?" (validated: Bikes 312,551.80). Terminal with `golden` output beside it |
| `fabric-screen` | `screens/fabric-notebook.jpg` | Fabric notebook `nb_copilot_demo`, Copilot chat pane, starter prompt "Profile my table to check columns, missing values, and duplicates", Copilot asking permission to add a cell, then the result |

Optional extra take (not in the script): Fabric Capacity Metrics app, *Item history*, filter operation *Copilot in Fabric*,
to show the capacity units the takes used (the app needs to be installed from AppSource and has data hours later).
Also optional: `./src/scripts/Get-FabricCopilotCapacity.ps1 | Format-Table -AutoSize` after `Connect-AzAccount` -> the
F2 workspace `True`, the trial workspace `False` with its reason. Mask capacity ids and the tenant domain.

## Masking
Tenant name and domain, subscription id, capacity ids, any URL with the lab tenant. Lab users are fictional (`labadmin`).
Fictional data only (Contoso Bikes).

## Tear-down
1. Pause the F2 after the last take, then delete resource group `rg-mglab-copilot-07` (this deletes the capacity). Confirm in
   Cost Management that nothing else is billed.
2. Delete workspaces `Contoso Copilot Lab` and `Contoso Trial Lab` (and the lakehouse, notebook and semantic model in them).
3. Remove `C:\MGLab\work\copilot-07`. In Desktop clear the Copilot workspace choice.
4. Tenant settings were not changed; the Fabric trial keeps running for other episodes.
