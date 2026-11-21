# Demo shot list — DEVLADLOG Deep Dive #12, Modern Intranet Platform (SharePoint + Viva + Teams + Power Platform)

Code, test and flow-definition scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs tenant** (Microsoft 365 lab tenant) for everything on screen. No Azure resources are used. Offline (container,
no tenant): 32 Pester tests pass (`Tests Passed: 32, Failed: 0`). **Not yet run against Microsoft 365:** the provisioning
module, the site design, the home site, the Teams pin and the flow. Record the outcome of each in the README ("Not verified
in the lab yet").

## Lab environment

Recorded on the **lab Windows laptop** (host): Windows Terminal with PowerShell 7 for the scripts, Edge for SharePoint, the
SharePoint and Teams admin centers and Power Automate, the Teams desktop app for the last scene. No Hyper-V VM and no Azure
resource group are needed (nothing is deployed to Azure; cost for the recording: **€0**, everything is already in the
Microsoft 365 E5 trial of the lab tenant).

| Need | Where it comes from |
|---|---|
| SharePoint, Teams, Viva Connections (one experience) | Microsoft 365 E5 trial (E licence covers one experience; Learn prerequisites). No Viva Suite licence: do not create a second experience. |
| Power Automate with SharePoint and Approvals | Included standard connectors: **no premium trial is needed** for this flow. |
| Users (lab, fictional) | `labadmin` (recording account: SharePoint administrator and Teams administrator roles; owner of the sites), `alex.demo` (employee, submits the news request and opens Teams), `sam.demo` (communications approver; flow parameter `mgl_CommsApprover` = their e-mail). Departments and manager fields are not needed. |
| Teams | Workflows app is already allowed (checked 21 Nov 2026); the Approvals app must be available to `sam.demo` (check it opens). |

**Local tools:** PowerShell 7.4+, Pester, `PnP.PowerShell` 3.x (`Install-Module PnP.PowerShell -Scope CurrentUser` once), the repo checked out.
Site names in the lab: `contoso-home`, `contoso-hr`, `contoso-it`, `contoso-ops` under the lab tenant (the contract says `contoso`;
you pass the real tenant name with `-TenantName`, and mask it on screen). Pick aliases that are free: if a site with that alias
exists from earlier work, change the aliases in `contract/intranet.json` (tests still pass) instead of reusing it.

## Setup (off camera)

1. **Tests first**
   ```bash
   cd series/deep-dive/episodes/12-modern-intranet-platform-sharepoint-viva-teams-p
   pwsh -NoProfile -c 'Invoke-Pester ./tests'        # expect Tests Passed: 32
   ```
2. **App registration for PnP.PowerShell** (as `labadmin`; PnP 3.x needs an app you own, see the PnP authentication article):
   ```powershell
   Register-PnPEntraIDAppForInteractiveLogin -ApplicationName "contoso-intranet-pnp" -Tenant <tenant>.onmicrosoft.com
   ```
   Note the client id it prints (not a secret). Grant admin consent when asked. **Check and write into the README:** that the
   default permissions of this cmdlet are enough for site creation, hub registration, site designs and `Set-PnPHomeSite`;
   if a call says access denied, add the permission it names, never a client secret.
3. **Plan (no change)**
   ```powershell
   ./provision/Initialize-Intranet.ps1 -TenantName <tenant> -ClientId <client id> -WhatIf
   ```
   Browser sign-in as `labadmin` (once per connection: the admin site, then the hub). Expect a table of 5 groups of steps, all `WhatIf`, no site created.
4. **Dry run of the real build, then undo it** (rehearsal): run without `-WhatIf`, run again (expect `Exists` on every line), run
   `./provision/Test-Intranet.ps1` (expect all `Pass`, exit code 0), then tear down as below so the real take starts from nothing.
   **Check and write into the README:** time for the four sites; whether `Get-PnPHubSiteChild` returned URLs or objects; whether
   the health check passed immediately or waited for the hub delay (Learn: 2 to 4 hours); the result of `Set-PnPHomeSite`.
   If the cmdlet fails because home site management moved to the SharePoint admin center, set the home site there
   (Settings > Home sites > Add > Use an existing communication site > `contoso-home`) and note it.
5. **Build the flow in the designer** (Power Automate, environment `DEV`, as `labadmin`): My flows > New flow > Automated cloud flow,
   name `News request approval`, trigger **SharePoint: When an item is created** (site = the hub site, list = News Requests); action
   **Approvals: Start and wait for an approval** (type: Approve/Reject – first to respond; title `News post: <Title> (<Department>)`;
   assigned to `sam.demo`'s e-mail; details = Summary); then **Condition**: outcome is `Approve`; in **Yes**: **SharePoint: Update item**
   (Id, Title, `News status` = Approved, `News message` = the approver's comments); in **No**: the same with `Rejected`.
   Compare with `flow/news-approval.definition.json` (names of actions, columns and statuses must match). Then export the
   flow (Export > Package, or copy the definition from Peek code), replace `flow/news-approval.definition.json`, and re-run
   `Invoke-Pester ./tests/Flow.Tests.ps1`. **Check and write into the README:** that the tests still pass on the real export;
   fix the test or the definition and say which.
6. **Teams app pin** (off camera first run; on camera in `viva-screen`): in the SharePoint admin center > Settings > Home sites, check
   `contoso-home` is listed; Teams admin center > Teams apps > Setup policies > Global > Pinned apps > Add apps > the SharePoint
   / Viva Connections app > Save. Learn says to revisit the pinning policy for each new experience. **Check and write into the
   README:** the app name shown in Teams and how long the pin took to reach `alex.demo`.
7. **Reset** to the empty tenant (tear-down steps 1 to 4) before the take. Wait for the site deletions to finish.

## Screens to capture (1920×1080, terminal font 18 pt, browser zoom 100 %)

| Scene id | File | What must be on screen |
|---|---|---|
| `provision-screen` | `screens/provision.jpg` | Windows Terminal (PowerShell 7). `./provision/Initialize-Intranet.ps1 -TenantName <tenant> -ClientId <id> -WhatIf` (table: Site ×4, Hub, Association ×3, HubNavigation ×4, HomeSite, all `WhatIf`); same without `-WhatIf` (Created ×4, Registered, Associated ×3, Added ×4, Set); same again (all `Exists`); then `./provision/Test-Intranet.ps1` (all Pass). Browser sign-in windows may flash: do not show passwords or codes. **Mask** the tenant name and the client id. |
| `hub-screen` | `screens/hub.jpg` | Edge, `https://<tenant>.sharepoint.com/sites/contoso-home`: hub navigation (People and Culture, IT Help, Operations, Expenses) on top; click People and Culture: the same bar is on the department site. Then SharePoint admin center > Sites > Active sites: `Contoso Home` shown as hub with the three departments. Hub changes can take 2 to 4 hours: record after the wait. Mask the tenant name in the address bar. |
| `flow-screen` | `screens/flow.jpg` | Power Automate: the flow in the designer (three actions + condition); then as `alex.demo` add an item to `News Requests` (Title, Summary, Department); as `sam.demo` the approval (Approvals app in Teams, or the e-mail, whichever arrives: show the real one) answered with a comment; the item refreshed with `News status` Approved and the message. Also show the run history (Succeeded). Lab users only. |
| `viva-screen` | `screens/viva.jpg` | Teams admin center > Setup policies > Global > Pinned apps with the app; SharePoint admin center > Settings > Home sites with `Contoso Home` (state Draft, then enabled); Teams desktop as `alex.demo`: the app on the left bar, the home site open inside Teams. Mask the tenant name. |

Capture order: provision → hub → flow → viva (the list used by the flow exists from the provision run).

## Masking notes
Tenant name and domain, the client id of the PnP app, the SharePoint admin center URL, the environment URL of Power Automate,
user principal names other than `*.demo`. Never show a certificate, a secret or a token (there are none in the repo).

## Tear-down
1. Flow: Power Automate > My flows > `News request approval` > Delete.
2. Teams admin center: remove the app from the Global pinned apps list, if it was not pinned before.
3. Home site and hub, as `labadmin` (admin connection):
   ```powershell
   Connect-PnPOnline -Url https://<tenant>-admin.sharepoint.com -Interactive -ClientId <client id>
   Remove-PnPHomeSite -Force          # or remove it in SharePoint admin center > Settings > Home sites
   Unregister-PnPHubSite -Site https://<tenant>.sharepoint.com/sites/contoso-home
   ```
4. Sites, site design and site script:
   ```powershell
   'contoso-ops','contoso-it','contoso-hr','contoso-home' | ForEach-Object { Remove-PnPTenantSite -Url "https://<tenant>.sharepoint.com/sites/$_" -SkipRecycleBin -Force }
   Get-PnPSiteDesign | Where-Object Title -eq 'Contoso intranet site' | ForEach-Object { Remove-PnPSiteDesign -Identity $_.Id -Force }
   Get-PnPSiteScript | Where-Object Title -eq 'Contoso intranet site script' | ForEach-Object { Remove-PnPSiteScript -Identity $_.Id -Force }
   ```
   `-SkipRecycleBin` deletes permanently, so the aliases are free again. A hub site may need `Unregister-PnPHubSite` first (step 3).
5. Entra admin center: delete the app registration `contoso-intranet-pnp` (and permanently delete it under Deleted applications).
6. Local: close the PowerShell session (the PnP connections are in memory only).
