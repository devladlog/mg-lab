# Demo shot list — Power BI #6 Dashboards & Publishing

## Lab environment

Same as episode 5: no VM and no Azure resource. Record right after episode 5 (or redo its setup steps 1–6).

| What | Details | Cost |
|---|---|---|
| Recording laptop (Windows) | Power BI Desktop (current), PowerShell 7, Windows Terminal, browser with an InPrivate window | free |
| PowerShell module | `MicrosoftPowerBIMgmt` (`Install-Module MicrosoftPowerBIMgmt -Scope CurrentUser`) | free |
| Lab tenant: capacity | Fabric + Power BI 60-day trial (West Europe), `series/LAB.md` | trial, €0 |
| Lab tenant: workspace | **Contoso Sales (Lab)** from episode 5 (trial capacity, admin `labadmin`), episode 5 model published, role members set | €0 |
| Lab tenant: users | `labadmin` (records), `alex.demo`, `sam.demo`, `riley.demo`, `taylor.demo` (app audience), `jordan.demo` (optional Head office audience) | trial |
| Tenant settings (check only) | *Create workspaces*, *Publish apps to ...* allowed for labadmin; **Publish to web stays off** | €0 |

Screens are recorded in Power BI Desktop and the browser on the laptop (lab tenant), plus Windows Terminal.

## What was verified where

| Step | Verified in the container | Needs the tenant |
|---|---|---|
| Preflight (`-ProjectPath`) | real run on the episode 5 project (output in script.yaml) and on fixtures; Pester | — (B-roll only) |
| Inventory + rules (`-WorkspaceId`) | Pester with responses shaped like the Learn samples | **real run** |
| `Copy-PbiDashboard` | Pester: call order, bodies, cross-workspace guard, `-WhatIf` | **real copy** |
| Publish, pin, alert, app | — | **all of it** |

## Prerequisites (on the laptop)
1. Episode 5 project at `C:\MGLab\power-bi\ep05\src` with `UpnDomain` set to the lab domain (not committed), star CSVs
   and `store_access.csv` in `C:\MGLab\power-bi\star\`.
2. This episode's folder at `C:\MGLab\power-bi\ep06\`.
3. In the terminal, before recording: `Connect-PowerBIServiceAccount` (as labadmin),
   `Import-Module C:\MGLab\power-bi\ep06\src\PbiPublishing\PbiPublishing.psd1`, and `$ws = '<workspace id>'`
   (from the workspace URL). Never type IDs on camera.

## Steps and screens (match the `screen` scenes in script.yaml)

| Scene id | File | Steps and what must be on screen |
|---|---|---|
| `publishscreen` | `screens/pub-publish-desktop.jpg` | Desktop with the episode 5 project open. **Home > Publish** > *Contoso Sales (Lab)* > **Select**. The model is already there from episode 5, so the **Replace this semantic model** dialog should appear with the impact summary: capture it, then **Replace**. Then **Success!** with the link. Cut to the workspace list in the browser: report and semantic model *ContosoSales*. |
| `dashboardscreen` | `screens/pub-dashboard.jpg` | Open report *ContosoSales* > **Edit**, page *Sales overview*, Year slicer **with no selection**. Hover the *Sales amount* card > pin icon > **New dashboard** *Contoso Bikes - Daily* > **Pin**. Pin to the existing dashboard: *Orders* card, *Sales amount and prior year by month*, *Sales amount by category*, *Sales amount by store*. If asked to save the report, Save. **Go to dashboard**, arrange: two cards on top (Sales amount **1,862,401.98**, Orders **2,440**), charts below. Then *Orders* tile > **…** > **Manage alerts** > **Add alert rule**: title *Orders above 2,500*, condition **Above 2500**, at most once a day, **Save and close**. |
| `inventoryscreen` | `screens/pub-inventory.jpg` | Terminal in `C:\MGLab\power-bi\ep06`: `./src/Invoke-PublishingCheck.ps1 -WorkspaceId $ws`. First line `1 report(s), 1 semantic model(s), 1 dashboard(s), 5 tile(s)`, then findings and the count. Expected: **WS004** (RLS). Also note whether **WS002** (untitled tiles), **WS003** (gateway) and **WS006** (not refreshable) appear, and send the output to the maintainer so the narration of `inventory`/`gotcha` matches. |
| `copyscreen` | `screens/pub-copy-dashboard.jpg` | Set `$daily = '<id of Contoso Bikes - Daily>'` off camera. Record `Copy-PbiDashboard -WorkspaceId $ws -DashboardId $daily -NewName 'Contoso Bikes - Store managers' -WhatIf` (prints the What if line with *5 tiles*), then the same without `-WhatIf`: `Dashboard Contoso Bikes - Store managers, Tiles 5, SameWorkspace True`. Browser: refresh the workspace, open the new dashboard: same five tiles and values. |
| `appscreen` | `screens/pub-app-rls.jpg` | Workspace **Manage access**: remove Alex, Sam, Riley, Taylor (they get the app instead; Jordan can stay). **Create app**: Setup name *Contoso Bikes*, a description; Content: report *ContosoSales* and dashboard *Contoso Bikes - Store managers*; Audience: rename to *Store managers*, add Alex Demo, Sam Demo, Riley Demo, Taylor Demo; **Publish app**, capture *Successfully published* (blur the link). Then an **InPrivate** window signed in as `sam.demo`: **Apps** > *Contoso Bikes* (or the copied link) > report page *Store security*: Contoso Madrid only, Visible stores **1**, Sales amount **366,058.87**. Open the dashboard in the app and note what the *Sales amount* tile shows (expected **366,058.87** if tiles follow RLS; tell the maintainer either way). |

Optional B-roll for the `gotcha` scene (code scene, rendered from the preflight output): semantic model **Settings**
> *Gateway and cloud connections* / *Refresh* showing that the CSV source needs a gateway before a schedule can be
set. Terminal B-roll (no sign-in needed):

```powershell
pwsh -NoProfile -File src/Invoke-PublishingCheck.ps1 -ProjectPath ../05-row-level-security/src
pwsh -NoProfile -Command "Invoke-Pester ./tests -Output Detailed"
```

## Masking
- Workspace, dashboard and model IDs: only in variables set off camera; blur browser URLs (`pipeline/mask.js`).
- The tenant domain shows in the app audience picker, Manage access and the InPrivate account menu: blur it.
- The app link in *Successfully published*: blur.
- Account picture / name: *Lab Admin* or blurred; Sam's InPrivate window shows *Sam Demo* only.
- The audit output has names only (no IDs, no e-mail); check it anyway before publishing the video.

## Tear-down
- Delete the alert (*Orders above 2,500*) from **Settings > Alerts** or the tile.
- **Unpublish** the app (workspace > **…** > *Unpublish app*) and delete the dashboard copy *Contoso Bikes - Store
  managers*; keep or delete *Contoso Bikes - Daily* as the maintainer prefers.
- If no later episode needs the workspace now: remove remaining users, clear role members, delete workspace
  *Contoso Sales (Lab)*. Otherwise keep it and tell the maintainer what is left in it.
- Don't commit the episode 5 project with the real `UpnDomain`; nothing to remove in Azure, no cost beyond the trials.
