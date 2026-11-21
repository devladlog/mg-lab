# Demo shot list - Copilot & AI #16 GitHub Copilot for .NET Modernization

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **CON-SQL01** (shared, `10.50.0.30`, SQL Server 2022 Developer, mixed auth, TCP 1433) for the TLS screen only. No new VM, nothing destructive on shared VMs: only the database `contoso_pricing` and the login `pricing_app` are created and dropped again |
| Recording machine | **The Windows lab laptop** (not a VM): Visual Studio 2026 (or 2022 17.14.17+, per Learn) with workloads **.NET desktop development** (components *GitHub Copilot* and *GitHub Copilot app modernization*) and **ASP.NET and web development** (the MVC web project needs it), plus the individual components *.NET Framework 4.7.2 targeting pack* and *.NET Framework 4.8 targeting pack*. .NET 10 SDK, Git, Python 3.10+ (script test only), SSMS or `sqlcmd` for the SQL script. The laptop reaches the VM at 10.50.0.30 |
| Tenant | Not used. The Microsoft 365 lab tenant plays no part in this episode |
| Accounts | The owner's GitHub account with a GitHub Copilot subscription, signed in to Visual Studio. Learn's install page requires "a GitHub Copilot subscription (paid or free)". **Which plan the owner has is not known; confirm before recording.** A Free plan may run out of allowance during a multi-task upgrade (not verified): if so, say so in the narration and switch to the owner's paid plan. Plan prices: see episode 15 `demo.md` (GitHub plans page) |
| Licences / purchases | Visual Studio: the owner's existing licence or the edition whose terms allow it (**not checked here**; do not install anything on the owner's behalf). No Microsoft 365 Copilot licence is involved. Cost of the recording: the Copilot allowance used by one upgrade (not measured) |
| Azure | none; no resource group |
| Cloud/GitHub | none required: the demo repo is local (Git only). Optional: a throwaway private GitHub repo if you also want the upgrade pushed |
| Secrets | The SQL login password is typed at the console; the connection string lives only in the `PRICING_CONN` environment variable of the terminal session. Never in a file, never on screen |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the lab laptop / VM |
|---|---|---|
| Scanner, upgrade-folder checker, instruction linter | yes: 40 xunit tests | - |
| Characterization tests on legacy, reference and naive implementations | yes: 13 / 14 passed / 5 failed + 8 passed | - |
| Legacy C# sources compile against .NET Framework 4.7.2 reference assemblies with MVC 5.2.9 | yes (throwaway project in a temp folder) | - |
| Old-style `.csproj`/`.sln` open and build in Visual Studio; NUnit tests discover and run | no | **baseline build before recording**; if something does not build, fix the fixture and note it in README "gotchas" |
| The agent: assessment, options, plan, tasks, commits | no | **record it, show what it really produces** |
| `check-upgrade` on the real `.github/upgrades` folder | only on the Learn task-list format | **first real run**; fix `UpgradeFolder.cs` if the real file differs |
| `Impl=agent` characterization run on the agent's library | the mechanism works (pointed at the reference project) | **run on the agent's output** |
| SQL script, `Contoso.Pricing.Probe`, certificate error and the lab-only fix | compile only | **record on CON-SQL01** |

## Prerequisites
- Terminal: dark theme, 18 pt, window 1600x900, `function prompt { 'PS> ' }`. Visual Studio: dark theme, zoom so editor text is 16 pt+.
- Pick a model in Copilot Chat with strong reasoning (Learn's advice) and say which one it is on screen.
- Reserve time: the agent's run length is not known; cut waits in editing and say so.

## Setup
1. Make a working copy outside the repo and put it in Git (the agent commits as it works):
   ```powershell
   Copy-Item .\src\legacy-contoso $HOME\contoso-quotes -Recurse
   Set-Location $HOME\contoso-quotes
   git init -b main; git add -A; git commit -m "Contoso Bikes quote service on .NET Framework 4.7.2"
   ```
2. Open `Contoso.sln` in Visual Studio. If a *Target Framework Not Installed* dialog appears (a 4.7.2 targeting pack is
   missing), install the component first; record it only if the dialog is the story. Build the solution and run the NUnit
   tests (3 tests). Note any failure: the fixture, not the agent, is at fault.
3. Pre-scan (terminal, episode `src/`): `dotnet run --project ModernizationScan -- scan <path>\contoso-quotes --md $HOME\prescan.md` and open the Markdown.
4. Baseline behaviour (episode folder): `dotnet test tests/Pricing.Characterization -p:Impl=legacy` -> `13 passed`; and for
   the contrast `-p:Impl=naive` -> `5 failed, 8 passed`.
5. SQL lab database, on `CON-SQL01` through SSMS or `sqlcmd` as the lab SQL admin: run `src/legacy-contoso/sql/001-price-list.sql`;
   at the console create the login `pricing_app` with a password typed by hand (the commented lines in the script), grant read on `contoso_pricing`.
6. Optional custom instruction: copy `upgrade-instructions\replace_newtonsoft_with_system_text_json.md` into the working copy
   and add it to the solution as a solution item (Learn: "Add the file to the solution for visibility"). Run
   `dotnet run --project ModernizationScan -- lint-instruction <that file>` first (passes).

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `start-screen` | `screens/modernize-start.jpg` | Solution Explorer, right-click `Contoso` solution > **Modernize**; Copilot Chat open with the agent; prompt "Upgrade everything to .NET 10"; the pre-initialization questions (target framework, Git strategy, workflow mode). Choose **Guided** mode for the recording. Model name visible |
| `assessment-screen` | `screens/assessment.jpg` | `.github/upgrades/<scenarioId>/assessment.md` open, as generated: summary, project and package compatibility, the Newtonsoft.Json and System.Data.SqlClient rows. Then `upgrade-options.md` (strategy, in-place vs side-by-side for the web app). If the agent offers the custom instruction, show it being retrieved; if not, say so |
| `tasks-screen` | `screens/tasks-progress.jpg` | `tasks.md` mid-run (progress line, `[ ]` to `[✓]`), the Git Changes window with the agent's commits, then in the terminal `dotnet run --project ModernizationScan -- check-upgrade $HOME\contoso-quotes` showing the stage and task counts |
| `gotcha-screen` | `screens/sql-encrypt.jpg` | Terminal in `src/expected-after/Contoso.Pricing.Probe` (our reference code, not the agent's): `$env:PRICING_CONN = '<typed off camera>'` for `Data Source=10.50.0.30;Initial Catalog=contoso_pricing;User ID=pricing_app;Password=...`, `dotnet run -- BIKE-100` shows the real exception (Learn documents a certificate-chain-not-trusted `SqlException`; **show whatever the server really returns**). Then the same with `Trust Server Certificate=True` appended: `BIKE-100: 1299.00`. Say it is lab-only and that production needs a trusted certificate |

Footage for the `lock` scene is terminal only: `dotnet test tests/Pricing.Characterization -p:Impl=legacy`, `-p:Impl=modern`, `-p:Impl=naive`.
Footage worth adding: after the agent finishes, `dotnet test tests/Pricing.Characterization -p:Impl=agent -p:AgentDir=$HOME\contoso-quotes\Contoso.Pricing`
(the agent's own library against the same behaviour tests; report honestly if it fails: that is a finding, not an error in the episode).

## Masking notes
- No passwords, connection strings with passwords, tokens or Visual Studio account emails on screen. `PRICING_CONN` is never echoed.
- The working folder path may show the Windows user name: use `$HOME` aliases or crop.

## Tear-down
1. Close Visual Studio; delete `$HOME\contoso-quotes` and `$HOME\prescan.md`.
2. On `CON-SQL01`: `DROP DATABASE contoso_pricing;` and `DROP LOGIN pricing_app;` (shared VM: nothing else touched).
3. Remove the `PRICING_CONN` environment variable (close the terminal).
4. Optional: sign the GitHub account out of Visual Studio if the laptop is shared.
