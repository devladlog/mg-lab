# Demo shot list — DEVLADLOG Microsoft 365 #11: SharePoint Online Administration

Everything in `src/` and `tests/` already ran in the build container (53 Pester tests, an offline report from fictional data). This file lists what the human-supervised
session must set up and record in the **lab tenant**. Every Graph call below is **needs tenant**; every screen shows the real product (the real SharePoint admin center, the script
talking to the real Graph). `tests/fixtures/*` and `sample/` are for the automated tests only and never appear on screen.

The demo only uses what the lab already has: **no purchase, no cost, no new VM**. SharePoint Advanced Management is **not** in the lab and is not used.

## Lab environment

No VM. Recorded on the **lab Windows desktop**: a browser on the lab tenant (SharePoint admin center, Microsoft 365 admin center) and PowerShell 7.2+ on the host.

| Cloud item | Notes | Cost / requirement |
|---|---|---|
| Microsoft 365 E5 trial (already in the lab, until 20 Dec 2026) | Includes SharePoint Online; see `series/LAB.md` | in the lab |
| Lab users | `labadmin` (recording account, Global Administrator), `alex.demo` (uploads a few files so a site has activity) | none |
| Roles | `labadmin` as Global Administrator covers SharePoint Administrator (settings read and write), Reports Reader (usage report) and the Reports org setting (Learn: only a Global Administrator changes it) | none |
| Graph scopes (delegated, consent for `labadmin`) | Audit: `SharePointTenantSettings.Read.All`, `Reports.Read.All`, `ReportSettings.Read.All`. Remediate/restore add `SharePointTenantSettings.ReadWrite.All` | none |
| Three demo sites | Created in setup step 3, deleted in tear-down | none |
| Host PowerShell | PowerShell 7.2+, `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser` | none |

## Setup (before recording, at least three days before: the usage report needs data and an old enough site)

1. **Module.** `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser`.
2. **Remember the real values.** Off camera, with `labadmin`:
   ```powershell
   Connect-MgGraph -Scopes SharePointTenantSettings.Read.All, Reports.Read.All, ReportSettings.Read.All -NoWelcome
   (Invoke-MgGraphRequest -Uri /v1.0/admin/sharepoint/settings -OutputType PSObject) | Select-Object sharingCapability, isResharingByExternalUsersEnabled, isRequireAcceptingUserToMatchInvitedUserEnabled, isLegacyAuthProtocolsEnabled, sharingDomainRestrictionMode, isSitesStorageLimitAutomatic
   ```
   Write them down: tear-down puts `isResharingByExternalUsersEnabled` back to its original value. The consent screen for `Microsoft Graph Command Line Tools` appears the first time: record it masked or skip it.
3. **Three demo sites.** SharePoint admin center > Sites > Active sites > Create > Team site, owner `labadmin`:
   - `MG Lab Finance`: upload three small files (as `alex.demo` through the browser) and open a page, so it has activity right before recording.
   - `MG Lab Archive`: upload one small file once, then **leave it alone** until the recording (at least as many days as `inactiveDays` below) so it really becomes `InactiveSite`.
   - `MG Lab Empty`: no files at all (it will show `EmptySite` and `NoActivityRecorded`).
   Group-connected team sites also create Microsoft 365 groups (episode 3's subject); say nothing about that on camera.
4. **Config.** Copy `src/sharepoint-baseline.json` to `sharepoint-baseline.lab.json` (outside the repo) and edit:
   - `sites.inactiveDays`: a number of days **smaller** than the age of `MG Lab Archive`'s only activity (for example `3`); say on camera that the lab is days old and the production default is 90.
   - `remediate.allowedSettings`: `["isResharingByExternalUsersEnabled"]`, only that one.
   - `settings`: keep `isResharingByExternalUsersEnabled: false`. If the tenant's real `sharingCapability` is already `externalUserSharingOnly` the audit will not report it: that is fine, the demo's drift is the box ticked in screen 1.
5. **Dry run, off camera.** `./Invoke-SharePointAdmin.ps1 -BaselineFile ./sharepoint-baseline.lab.json` (live, read-only). Check, and fix the config accordingly:
   - **Concealed.** A new tenant should conceal names (Learn: the default since 1 Sept 2021): the run prints the warning with `displayConcealedNames = True`. That is the first beat of screen 2: keep it for the recording, and
     only then clear **Conceal user, group, and site names in all reports** (Microsoft 365 admin center > Settings > Org settings > Services > Reports). Learn: it takes a few minutes. *If the tenant is not concealed, skip the warning beat and edit the narration.*
   - After clearing: the `Report Refresh Date` column of the report (open the CSV once with `Get-SPASiteUsageReport | Format-Table 'Report Refresh Date','Site URL','Last Activity Date','Storage Used (Byte)','Storage Allocated (Byte)'`)
     says how fresh the data is. If the three demo sites are not in it yet, record another day. **Not verified:** how many days the report lags: Learn's pages read for this episode give no figure.
   - **System sites.** Note any site that is not yours (root site, content type hub, app catalog, anything) and add a pattern for it to `sites.ignoreSiteUrlPatterns` (e.g. `"*/sites/contentTypeHub"`). Say "I ignore system sites" on camera if one is shown.
   - **Not verified:** the real `Is Deleted` text (the code expects `True`/`False`) and `Storage Allocated (Byte)` with automatic site storage. If `NearQuota` would never fire, do not claim it in the narration (the script's code scene only
     shows the rule).
6. **Optional `NearQuota` row** (only if the dry run shows a usable `Storage Allocated`): SharePoint admin center > Settings > Site storage limit: manual (this changes `isSitesStorageLimitAutomatic`: write the old value down and restore it in tear-down), then set `MG Lab Finance` to 1 GB and use
   `nearQuotaPercent: 1` in the lab config (say so on camera). Skip if it is not simple.

## Screens to capture (match `script.yaml` screen scenes)

### 1. `screens/sharing-policy.jpg` — "The sharing policy today" (SharePoint admin center)
SharePoint admin center > **Policies > Sharing** as `labadmin`. Show **External sharing** for SharePoint, expand **More external sharing settings**, tick **Allow guests to share items they don't own**, **Save**
(Learn: *Manage sharing settings*). This is the real drift the audit finds. Mask the tenant name. Rewrite the narration to the real level.

### 2. `screens/audit.jpg` — "The audit, on the real tenant" (needs tenant, read-only)
```powershell
./Invoke-SharePointAdmin.ps1 -BaselineFile ./sharepoint-baseline.lab.json                      # while concealed: the warning
# clear the Reports setting, wait a few minutes
./Invoke-SharePointAdmin.ps1 -BaselineFile ./sharepoint-baseline.lab.json -OutFile ./report.lab.md
```
Capture the warning, then the findings table (setting drift first, then the site rows with their rules), the totals line and the remediation plan line (`1 change(s)`).
Rewrite the narration to the real rows. Mask site URLs and UPN domains; `report.lab.md` contains tenant data: show it only cropped.

### 3. `screens/remediate.jpg` — "Preview, change, check" (needs tenant, **writes**)
1. `./Invoke-SharePointAdmin.ps1 -BaselineFile ./sharepoint-baseline.lab.json -Remediate -RollbackFile ./rollback.lab.json -WhatIf` : a "What if" line, nothing changed, no rollback file (show `Test-Path ./rollback.lab.json` is `False`).
2. Same command without `-WhatIf` (needs `SharePointTenantSettings.ReadWrite.All`: the runner asks for consent). It asks to confirm: **Yes**. Expect `Changed`.
3. Reload SharePoint admin center > Policies > Sharing > More external sharing settings: the box is cleared. **Not verified:** how long the change takes to show; if the admin center still shows the box ticked, wait and reload, and say so on camera rather than cutting it.
4. Show `rollback.lab.json` (`previous: true`, `applied: false`).
Rewrite the narration to what really happened.

### 4. `screens/restore.jpg` — "The way back" (needs tenant, **writes**)
`./Invoke-SharePointAdmin.ps1 -Restore ./rollback.lab.json` : `Restored`; reload the admin center: the box is ticked again. If it says `Skipped`, read the message on camera (someone, or a delay, changed the value): that is the guard working.
Then **untick the box by hand** (tear-down 1).

## Masking checklist
- Tenant name and domain, admin UPN, user addresses beyond the lab aliases, site URLs (they contain the tenant name), site and group ids, tenant id on the consent screen.
- `sharepoint-baseline.lab.json`, `report.lab.md`, `rollback.lab.json` contain tenant data: don't show them in full, never commit them.

## Tear-down (before the trial ends on 20 Dec 2026)
1. `isResharingByExternalUsersEnabled` back to the value written down in setup 2 (SharePoint admin center > Policies > Sharing > More external sharing settings, or `Invoke-SharePointAdmin.ps1 -Restore` only if the rollback is still valid). If step 6 was done, restore the site storage limit setting too.
2. Microsoft 365 admin center > Settings > Org settings > Services > Reports: tick **Conceal user, group, and site names in all reports** again (the privacy default).
3. SharePoint admin center > Sites > Active sites: delete the three `MG Lab *` sites; then Sites > Deleted sites: delete permanently; Entra admin center > Groups > Deleted groups: delete permanently the three groups the team sites created.
4. Delete `sharepoint-baseline.lab.json`, `report.lab.md`, `rollback.lab.json` from the recording machine. Optionally remove the consent for `Microsoft Graph Command Line Tools` (Entra admin center > Enterprise applications) and run `Disconnect-MgGraph`.
