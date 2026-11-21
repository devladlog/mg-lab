# Demo shot list — SharePoint #7 Hub sites and navigation

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure / Power Platform | none |
| Tenant | **SharePoint** in the lab tenant. Existing: `/sites/Purchasing` (episode 3, with the episode 4 library). Created here: communication sites `/sites/Operations` (the hub) and `/sites/Facilities`, the hub registration, two associations, the hub navigation. Kept for episode 8 |
| Entra groups (created here) | Security groups **Operations Site Owners** (labadmin, jordan.demo), **Purchasing Team** (alex.demo, labadmin), **Facilities Team** (sam.demo) |
| Lab users | `labadmin` records (SharePoint Administrator role, exists); `alex.demo` and `sam.demo` for the audience screen, each in its own browser profile |
| Entra app | The existing "MG Lab PnP" app (delegated). For audiences by name it needs Microsoft Graph **Group.Read.All** (delegated, admin consent); otherwise paste the three group object IDs into the plan's `audiences` (never commit them) |
| Licences / trials | lab E5 licences; cost €0 |
| Recording machine | The Windows lab laptop: PowerShell 7.4+ with PnP.PowerShell 3.x and Pester; browser with `pipeline/mask.js` |

The code scenes are real output from this folder (lint, hierarchy check, Pester). The four `screen` scenes need the
lab tenant. **Needs tenant:** `Resolve-MgAudience`, `Invoke-MgHubRegistration`, `Invoke-MgHubAssociation`,
`Get-MgLiveNavigation`, `Invoke-MgNavigationTree`, `Invoke-MgHubNavigation`, `Get-MgHubState` and the `-Provision` /
`-Check` paths of `Invoke-HubNavigation.ps1`. Locally they are covered only by Pester tests that mock the real PnP
cmdlets (parameter names and types are checked).

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Lab tenant, Microsoft 365 E5 trial | hub sites and audience targeting: any SharePoint plan; no Premium, no Advanced Management | €0 (until 20 Dec 2026) |
| SharePoint Administrator for `labadmin` | hub registration and association | €0 |
| `/sites/Purchasing` from episode 3 (pages `how-to-buy`, `news-approval-limits`, list *Purchasing FAQ*) and the episode 4 library `SupplierDocuments` | the navigation links to them | €0 |
| Three Entra security groups (above) | Entra admin center → Groups → New group (security, assigned). Do it **the day before**: group membership has to reach SharePoint before targeting works | €0 |
| PowerShell 7.4+, PnP.PowerShell 3.x, Pester | `Install-Module PnP.PowerShell, Pester -Scope CurrentUser` | €0 |

## Set-up (before recording)
```powershell
cd series/sharepoint/episodes/07-hub-sites-navigation
Invoke-Pester ./tests -Output Detailed                                     # expect 27 passed
$tenant = 'https://<lab-tenant>.sharepoint.com'                             # never on screen unmasked
$t = @{ TenantUrl = $tenant; AdminUrl = 'https://<lab-tenant>-admin.sharepoint.com'; ClientId = '<MG Lab PnP client id>' }

# The two new communication sites (Purchasing exists)
Connect-PnPOnline -Url $t.AdminUrl -ClientId $t.ClientId -DeviceLogin
New-PnPSite -Type CommunicationSite -Title 'Contoso Operations' -Url "$tenant/sites/Operations" -Wait
New-PnPSite -Type CommunicationSite -Title 'Contoso Facilities' -Url "$tenant/sites/Facilities" -Wait

# Hub logo, and the Facilities page the navigation links to
Connect-PnPOnline -Url "$tenant/sites/Operations" -ClientId $t.ClientId -DeviceLogin
Add-PnPFile -Path ./src/hub/operations-logo.png -Folder SiteAssets
Connect-PnPOnline -Url "$tenant/sites/Facilities" -ClientId $t.ClientId -DeviceLogin
Add-PnPPage -Name 'office-moves' -Title 'Office moves' -LayoutType Article -Publish

./src/Invoke-HubNavigation.ps1 -PlanPath ./src/hub/operations.hub.json @t -Provision -WhatIf
```
Check `SiteAssets` exists on the new communication site (if `Add-PnPFile` says the folder doesn't exist, create the
library from the browser by adding an image to a page once, or use `Shared Documents` and change `logoUrl`).
The `-WhatIf` run must show `RegisterHub`, two `Associate` lines and 15 `AddNode` lines. Three device-code sign-ins
happen (admin, hub site, Graph for the groups): do them off camera. Dark terminal, font 18+, clear before each capture.

## Screens to capture (match the `screen` scenes in script.yaml)

1. **`screens/provision.jpg` — scene `provision`**
   ```powershell
   ./src/Invoke-HubNavigation.ps1 -PlanPath ./src/hub/operations.hub.json @t -Provision
   ```
   Capture: plan tree, `0 error(s), 0 warning(s)`, `RegisterHub`, `SetHub`, `Associate` ×2, `SetWeb
   NavAudienceTargetingEnabled=True`, the `RemoveNode` lines for the new site's default nodes, 15 `AddNode` lines.
   **Record what really happens.** Check in particular:
   - Labels: `Add-PnPNavigationNode -Url 'http://linkless.header/'` creates a non-clickable label. If it errors or the
     label renders as a link, try without `-Url` and fix `$script:LabelUrl` (README "Not verified yet").
   - Which default nodes the new site had (note them in README).
   - Whether links to other site collections work with `-External` (open one).

2. **`screens/hub-nav.jpg` — scene `hubnav`**
   Browser as **Alex Demo**, `/sites/Purchasing` home: hub bar *Contoso Operations* with logo, Purchasing mega menu
   open (*Buy something*, *Purchasing team*), the site's own links from episode 3 below. Optionally a second capture
   on `/sites/Facilities` with the same hub bar. The hub theme can take a while to show on associated sites
   ("changes made to the theme may not appear right away").

3. **`screens/audience.jpg` — scene `audience`**
   Two browser profiles side by side, both on `/sites/Purchasing`, Purchasing menu open: **Alex Demo** sees
   *Purchasing team*; **Sam Demo** doesn't, and sees *Facilities team* under Facilities. If targeting hasn't applied
   yet (new group membership), wait and retry later; note the delay in README. If targeted hub links don't filter on
   the associated site at all, record it and update the narration and README.

4. **`screens/check.jpg` — scene `check`**
   ```powershell
   ./src/Invoke-HubNavigation.ps1 -PlanPath ./src/hub/operations.hub.json @t -Check      # expect "No findings."
   ```
   Then in the browser on the hub: hub navigation **Edit** → rename *Facilities* to *Facility* → Save; run `-Check`
   again: expect `HL004  Facilities  Title: tenant has 'Facility'.` and `1 error(s), 0 warning(s)`. Capture both
   runs. Run `-Provision` once more afterwards to restore the plan (expect RemoveNode + AddNode lines).
   If `-Check` reports differences right after provisioning, record them: they are the gaps in "Not verified yet"
   (e.g. how SharePoint stores label URLs or relative links) — fix `Get-MgUrlKey` and the README.

After capturing, add `crop`/`highlight` to each screen scene if needed (see episode 07's script for the format).

## Masking
- Tenant host in address bars and in `$t`; PnP client id; device-login codes; group object IDs if printed.
- Account pictures/initials of real people (only lab users should appear); the admin account name.
- Site, group and user names are fictional.

## Tear-down
Keep everything if episode 8 is recorded next (it applies the theme to this hub and links it from global
navigation). Otherwise:
```powershell
Connect-PnPOnline -Url $t.AdminUrl -ClientId $t.ClientId -DeviceLogin
Remove-PnPHubSiteAssociation -Site "$tenant/sites/Purchasing"
Remove-PnPHubSiteAssociation -Site "$tenant/sites/Facilities"
Unregister-PnPHubSite -Site "$tenant/sites/Operations"
Remove-PnPTenantSite -Url "$tenant/sites/Facilities" -Force
Remove-PnPTenantSite -Url "$tenant/sites/Operations" -Force
```
Delete the three Entra groups, and remove the Graph permission from the PnP app if it was added only for this episode.
