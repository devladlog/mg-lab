# DEVLADLOG Power BI #6: Dashboards & Publishing

This episode publishes the **Contoso Bikes** project from [episode 5](../05-row-level-security/) (star schema,
measures, two-page report, dynamic RLS) and covers what happens around Publish. There's no new model or report
here: dashboards and apps live only in the Power BI service, so the code is a PowerShell module that checks a
project **before** publishing and audits and copies dashboards **after** publishing, through the Power BI REST API.

- **`Test-PbipPublishReadiness`** (offline): reads a PBIP folder and reports what publishing will need. Local file
  sources (`File.Contents`, `Folder.Files`, `Folder.Contents`) need an on-premises data gateway to refresh in the
  service (PUB001), parameters holding local paths (PUB002), RLS roles that need members in the service and rule out
  Publish to web (PUB003), and a report that points to a semantic model folder that doesn't exist (PUB004)
- **`Get-PbiWorkspaceInventory`** (read only): reports, semantic models, dashboards and every tile of a workspace
  (*Get Reports / Datasets / Dashboards / Tiles In Group*)
- **`Test-PbiWorkspacePublishing`**: rules on that inventory. A tile whose report isn't in the workspace (WS001), a
  tile without a title in the API (WS002), semantic models that need a gateway (WS003), have RLS (WS004), aren't
  refreshed (WS006), and dashboards over the team's tile limit (WS005). Output uses names only, never IDs or e-mail
  addresses
- **`Copy-PbiDashboard`**: *Add Dashboard In Group*, then *Clone Tile In Group* for every tile. In the same workspace
  the tiles keep their links; to another workspace it requires the target report and semantic model (Learn: without
  them the cloned tiles are broken), refuses dashboards with tiles from several reports in that case, and supports
  `-WhatIf`
- **`Invoke-PublishingCheck.ps1`**: one entry point for both checks, exit code 1 on errors (usable in a pipeline)

| Path | What it is |
|---|---|
| [`src/PbiPublishing/PbiPublishing.psm1`](src/PbiPublishing/PbiPublishing.psm1) | The module: 5 exported functions, 10 rules |
| [`src/PbiPublishing/PbiPublishing.psd1`](src/PbiPublishing/PbiPublishing.psd1) | Module manifest (PowerShell 7.2+, external dependency `MicrosoftPowerBIMgmt`) |
| [`src/Invoke-PublishingCheck.ps1`](src/Invoke-PublishingCheck.ps1) | `-ProjectPath <PBIP folder>` (offline) or `-WorkspaceId <id>` (signed in) |
| [`tests/PbiPublishing.Tests.ps1`](tests/PbiPublishing.Tests.ps1) | Pester: manifest, readiness on episode 5 + fixtures, inventory, rules, copy (REST cmdlet mocked) |
| [`tests/fixtures/rest/`](tests/fixtures/rest) | REST responses shaped like the Learn samples (zero GUIDs, fictional names) |
| [`tests/fixtures/cloud-project`, `broken-reference`, `live-connection`](tests/fixtures) | Minimal PBIP folders: a SQL source without roles, a report pointing to a renamed model, a live connection |

## Run it

```bash
pwsh -NoProfile -Command "Invoke-Pester ./tests -Output Detailed"      # Tests Passed: 20, Failed: 0

pwsh -NoProfile -File src/Invoke-PublishingCheck.ps1 -ProjectPath ../05-row-level-security/src
#   PUB001 Warning  6 table(s) read local files with File.Contents (...): ... needs an on-premises data gateway
#   PUB002 Info     parameter DataFolder is a local path (C:\MGLab\power-bi\star\): the gateway machine needs the same path
#   PUB003 Warning  RLS roles Head Office, Store Managers: add members ...; Publish to web isn't available
#   0 error(s), 2 warning(s)          exit 0
pwsh -NoProfile -File src/Invoke-PublishingCheck.ps1 -ProjectPath tests/fixtures/broken-reference
#   PUB004 Error ... 1 error(s), 0 warning(s)    exit 1
```

In the lab tenant (needs a sign-in, see [demo.md](demo.md)):

```powershell
Install-Module MicrosoftPowerBIMgmt -Scope CurrentUser
Connect-PowerBIServiceAccount
./src/Invoke-PublishingCheck.ps1 -WorkspaceId <workspace id>
Import-Module ./src/PbiPublishing/PbiPublishing.psd1
Copy-PbiDashboard -WorkspaceId <workspace id> -DashboardId <dashboard id> -NewName 'Contoso Bikes - Store managers' -WhatIf
```

## Expected results in the lab (episode 5 model, Year slicer cleared)

| Where | Expected |
|---|---|
| Dashboard *Contoso Bikes - Daily* (5 tiles) | Sales amount **1,862,401.98**, Orders **2,440**, line chart by month, Sales amount by category, Sales amount by store |
| Workspace audit | 1 report, 1 semantic model, 1 dashboard (2 after the copy), 5 tiles; WS004 for the RLS model; WS002/WS003/WS006 as the service reports them (see gotchas) |
| App, signed in as Sam Demo | *Store security*: Contoso Madrid only, Visible stores 1, Sales amount **366,058.87** |

## What we learned / gotchas

- **Published isn't refreshed.** Desktop uploads the data when you publish (Learn). Our model reads CSV files from
  `C:\MGLab\...`, so a refresh in the service needs an on-premises data gateway, and Learn's data alerts page says
  alerts "only work on refreshed data". Without a gateway the dashboard and its alert never change. Preflight
  (PUB001) says so before publishing; the gateway is episode 14.
- **The Tiles API doesn't return every title.** Learn: "Titles that are edited in the report before the visual is
  added to the dashboard, are not returned." All our visual titles are set in the report, so expect WS002 until the
  titles are set in the dashboard (*Edit details*). Not yet observed in the lab.
- **Cloning a tile to another workspace without a target report breaks it** (Learn, *Clone Tile In Group*).
  `Copy-PbiDashboard` throws instead, and also when the dashboard mixes tiles from several reports, because one
  target report can't rebind them all.
- **Dashboards have no file format.** They're a service feature (not in Desktop), so they can't be kept in git like
  the PBIP; the REST inventory is how this episode keeps track of them.
- **Pinning drops formatting.** Learn: a pinned tile ignores border, shadow, background and title formatting (only
  the text stays) and conditional formatting; a visual type changed later in the report doesn't change the tile.
- **Q&A experiences are going away in February 2027** (Learn, *View and interact with dashboards*): we don't pin Q&A
  tiles.
- **Apps don't notify internal users** (Learn): send the app link. App audiences get RLS; workspace Contributors and
  above don't (episode 5).
- **`isRefreshable` semantics** (Learn): "true when the dataset is either recently refreshed or is configured for
  automatic refresh". Whether the upload from Desktop counts as "recently refreshed" isn't documented; WS006 reports
  what the service says.
- **PowerShell formatting in this container:** `Format-Table` output written straight to the pipeline came out empty
  under `pwsh -Command` here; piping through `Out-String -Width 140 | Write-Host` (as `Invoke-PublishingCheck.ps1`
  does) prints reliably.
- **Not verified on this machine (needs the lab tenant):** every REST call is tested against the documented response
  shapes with the cmdlet mocked, never against the service. demo.md records the real output.

## References
- [Publish semantic models and reports from Power BI Desktop (replace, impact message)](https://learn.microsoft.com/power-bi/create-reports/desktop-upload-desktop-files)
- [Introduction to dashboards for designers (one page, service only, dashboards vs reports)](https://learn.microsoft.com/power-bi/create-reports/service-dashboards) · [Create a dashboard from a report (pinning, formatting dropped)](https://learn.microsoft.com/power-bi/create-reports/service-dashboard-create) · [View and interact with dashboards (Q&A going away in February 2027)](https://learn.microsoft.com/power-bi/explore-reports/end-user-dashboard-open)
- [Data alerts in the Power BI service (gauges, KPIs, cards; only you see them; only on refreshed data; 250 alerts)](https://learn.microsoft.com/power-bi/create-reports/service-set-data-alerts)
- [Refresh semantic models created from local Power BI Desktop files (gateway for File/Folder)](https://learn.microsoft.com/power-bi/connect-data/refresh-desktop-file-local-drive) · [Data refresh in Power BI](https://learn.microsoft.com/power-bi/connect-data/refresh-data)
- [Publish a workspace app (audiences, up to 25, no e-mail to internal users)](https://learn.microsoft.com/power-bi/collaborate-share/service-create-distribute-apps) · [Publish to web (not for reports with RLS)](https://learn.microsoft.com/power-bi/collaborate-share/service-publish-to-web)
- REST: [Get Dashboards In Group](https://learn.microsoft.com/rest/api/power-bi/dashboards/get-dashboards-in-group) · [Get Tiles In Group](https://learn.microsoft.com/rest/api/power-bi/dashboards/get-tiles-in-group) · [Add Dashboard In Group](https://learn.microsoft.com/rest/api/power-bi/dashboards/add-dashboard-in-group) · [Clone Tile In Group](https://learn.microsoft.com/rest/api/power-bi/dashboards/clone-tile-in-group) · [Get Datasets In Group (isRefreshable, isOnPremGatewayRequired, isEffectiveIdentityRolesRequired)](https://learn.microsoft.com/rest/api/power-bi/datasets/get-datasets-in-group) · [Get Reports In Group](https://learn.microsoft.com/rest/api/power-bi/reports/get-reports-in-group) · [Invoke-PowerBIRestMethod](https://learn.microsoft.com/powershell/module/microsoftpowerbimgmt.profile/invoke-powerbirestmethod)
- Blog: [Dashboards & Publishing — Complete Guide](https://www.devladlog.com/articles/power-bi/2025-03-05-dashboards-publishing-complete-guide-2025/)
