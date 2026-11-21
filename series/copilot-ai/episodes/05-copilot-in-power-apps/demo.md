# Demo shot list - Copilot & AI #5 Copilot in Power Apps

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Tenant | The Momento Galático lab tenant, Power Platform environment `DEV` (Dataverse). `DEV` must be a production or sandbox environment: developer environments can no longer be created (series/LAB.md). Note its **region** in the Power Platform admin center (Environments): the lab tenant is in Portugal, so Europe is expected, which means the "Generative AI features" card of the environment may show **Move data across regions** (Learn: not shown for US environments). Write down its state before recording; if it is cleared and "Create new data" is missing or refuses, tick it, record that you did, and untick it in tear-down |
| Accounts | `labadmin` (Global Administrator, the recording account) creates the tables and the app. Learn requires the **system customizer** role in the environment to create tables with Copilot: check in the admin center (`DEV`, Users) that `labadmin` holds System Administrator or System Customizer there, and add it if not. No other account is needed |
| Licences / purchases | **Nothing bought, cost 0.** Learn (Power Apps licensing FAQ): no licence is needed to build canvas apps; running an app on Dataverse tables needs premium use rights, so `labadmin` starts the self-service **Power Apps trial** the first time Studio or the player asks (there are no spare Power Apps Premium licences, LAB.md). **Not recorded, need licences the lab does not have:** Microsoft Copilot in canvas apps (preview; Learn: users need a Microsoft 365 Copilot licence, US$30 per user per month, paid yearly, per series/LAB-REQUESTS.md, pricing page read 21 Nov 2026) and apps built in Copilot Studio (usage-based billing in Copilot Credits; Learn: US$1 buys 100 Copilot Credits; no pay-as-you-go plan is set in the lab). The owner decides whether either is ever bought |
| Azure | none |
| Recording machine | Windows lab laptop: browser on the lab tenant (labadmin profile) for `make.powerapps.com`, Power Apps Studio and `admin.powerplatform.microsoft.com`; PowerShell 7 terminal; **.NET 8 SDK or later** (the project targets net8.0); this repo cloned |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the lab tenant |
|---|---|---|
| Formula extraction from `*.pa.yaml` (App, Screens, Children, Properties, multi-line blocks, unzipped `.msapp` layout) | yes: xUnit, 40 tests | - |
| Check with the real Power Fx engine (Microsoft.PowerFx.Core and .Interpreter 1.8.1 from NuGet): syntax, names, result type, host functions, the extra rules PF001 to PF007 | yes | - |
| `run` on sample rows (Filter, CountRows, Concat, relative dates) | yes | - |
| Everything Copilot does (tables, formula bar, explain) and everything Studio shows (delegation triangle) | **no** | **record it** |
| The real `.pa.yaml` of a Copilot-built app, and whether the real formulas check cleanly | **no**: the samples in `src/samples/Src` are hand-written in the documented shape (schema read from the PowerApps-Tooling repository that Learn links to) | **first real run** |

Open points to confirm on the tenant, each can change the script:
1. Is "Create new data" with the Copilot panel available in `DEV` (region, data movement, system customizer)? If not, the
   `data-screen` scene must be rewritten around what the environment really offers.
2. What column names Copilot generates. Display names with spaces (for example `Due Date`) are written in single quotes in
   formulas (`'Due Date'`), and `context.json` takes them as they are. Adapt the samples in the terminal take to the real names.
3. Whether the formula bar offers **Explain this formula** and the comment-to-formula suggestion in this environment and
   browser language (Learn: create-from-request is English only and preview; the other two list many languages).
4. Whether Studio shows the yellow delegation triangle for `FirstN(Sort(Filter(..., Len(...) > 2), ...), 10)` on a Dataverse
   table. Learn says not every nondelegable case shows a warning. Keep whatever happens.
5. `Expand-Archive` on a `.msapp`: Learn gives that command with the `.msapp` path; if PowerShell refuses the extension, copy the file to `.zip` first.
   Learn also says an older `.msapp` has no `src` folder: open and save the app again in Studio first.

## Prerequisites
- Terminal: dark theme, 18 pt, window 1600x900, short prompt (`function prompt { 'PS> ' }`). Browser dark theme, 125 %.
- `cd series/copilot-ai/episodes/05-copilot-in-power-apps/tests/PowerFxReview.Tests; dotnet test -m:1` -> `Passed: 40`.
- Sample run (no tenant): from the episode folder,
  `dotnet run --project src/PowerFxReview -- review src/samples/Src --context src/samples/context.json` -> `15 formulas: 5 clean, 4 with warnings, 5 partly checked, 3 with errors` and exit code 1.

## Setup
1. Admin center: open `DEV` (Environments), confirm Dataverse, region and the Generative AI features card (see the table above). Do not capture this card in the video unless it is useful; mask the environment URL either way.
2. As `labadmin` on `make.powerapps.com` switch to `DEV`. Accept the Power Apps trial if asked.
3. Rehearse the Copilot prompt off camera once, delete what it created, so the recording starts from a clean `DEV`.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `copilot-data` - Tables from a sentence
Home, **Start with data**, **Create new data**: the *Create new tables* workspace with the Copilot panel on the right.
Prompt (copy exactly):
`Create tables to track equipment loans at Contoso: item, borrower, borrower email, due date, returned on date and status (Out, Returned, Lost)`
Capture the prompt, the generated table, its columns and the sample rows. Then **Save and open app** (Learn: this creates
draft tables and relationships and opens the app for editing). Name the app `Equipment loans`.
If the table has an unexpected shape (extra tables, different columns), keep it and say so in the narration: that is the lesson.

### 2. `copilot-formula` - comment in, formula out
In Studio, on the gallery set **Items**. In the formula bar type
`// show the loans that are not returned and are due before today`, wait for the grey suggestion (or press Enter), capture it,
press **Tab**. Then the Copilot menu next to **fx**, **Explain this formula**, capture the explanation. Copy the accepted
formula to a text file: it goes into the terminal take. If the suggestion is wrong or empty, capture that: Learn says
"If Copilot doesn't provide a suggestion, then it couldn't generate a formula" and suggests rephrasing.

### 3. `check-run` - check and run (terminal)
Write `context.mylab.json` (outside the repo, never committed) with the real table and column names, in the format of
`src/samples/context.json` (`datasource: true` for the table; add the gallery or inputs the formula mentions under `controls`).
```powershell
dotnet run --project src/PowerFxReview -- check '<formula from screen 2>' --property Items --context context.mylab.json
dotnet run --project src/PowerFxReview -- run   '<formula wrapped in CountRows(...)>' --context context.mylab.json --data data.mylab.json
```
`data.mylab.json` has the same shape as `src/samples/sample-data.json` (dates as `today-5`, `today`, `today+7`), with the
real column names. Visible: `OK ... -> a table`, then the count. If the checker reports an error on the real formula, keep
the take and explain it (that is the point of the episode).
Optional bonus take: `Save` drop-down in Studio, **Download a copy** (Learn: this downloads the `.msapp`), unzip it
(see open point 5) and `dotnet run ... review <folder> --context context.mylab.json`. Expect many `Name isn't valid` lines for
controls until they are added to the context file: say so, do not hide it.

### 4. `delegation` - Studio has the last word
Gallery **Items** = `FirstN(Sort(Filter('<table>', Len(<borrower column>) > 2), '<due date column>'), 10)` with the real
names. Capture Studio (yellow triangle and its message, or its absence). Then the terminal:
`dotnet run --project src/PowerFxReview -- check '<same formula>' --property Items --context context.mylab.json` -> `PF004 warning`.
Then undo the change in Studio.

## Masking notes
Mask the environment URL, the tenant name and the e-mail domain in every capture (browser and terminal). Fictional names only
(Alex Demo, Sam Demo ...). Never show passwords or tokens: sign in off camera. `context.mylab.json` and `data.mylab.json` stay local.

## Tear-down
1. In Studio close the app without publishing; on `make.powerapps.com` delete the `Equipment loans` app.
2. **Tables**: delete the tables Copilot created (and their sample rows), and any solution or relationship it added.
3. If you ticked **Move data across regions**, put it back to the state you wrote down.
4. Delete the downloaded `.msapp`, the unzipped folder and `*.mylab.json`.
5. Nothing else was created: no Azure resources, no purchases. The Power Apps trial, if started, expires on its own.
