# Demo shot list — SharePoint #1 Lists & libraries best practices

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure / Power Platform | none |
| Tenant | **SharePoint** in the lab tenant: test site `/sites/ListsDemo` (communication or team site, created by `labadmin` if missing). Created here: lists *Purchase Requests* (kept for episode 2), *Contracts*, *Legacy Requests* |
| Lab users | `labadmin` (the recording account): site owner, PnP device-code sign-in off camera. **`alex.demo` (Alex Demo)**: the requester for the 40 seeded items (`-RequesterEmail` = Alex's UPN, masked) |
| Entra | The existing "MG Lab PnP" app registration (delegated permissions) |
| Licences / trials | lab E5 licences; cost 0 |
| Recording machine | The Windows lab laptop: PowerShell 7.4+ with PnP.PowerShell 3.x and Pester; browser with `pipeline/mask.js` for the SharePoint screens |

Everything except the four `screen` scenes is already real output from this folder (lint, tests). The screens need
the lab tenant. **Needs tenant:** `Invoke-MgListProvisioning`, `Get-MgListAudit`, seeding, and the end-to-end run of
`Invoke-ListDesign.ps1` with `-SiteUrl` — locally they are covered only by Pester tests that mock the real PnP cmdlets.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Lab Microsoft 365 tenant with SharePoint | existing lab tenant | €0 (existing licences) |
| A test site, e.g. `/sites/ListsDemo` (communication or team site) | site owner is enough; no SharePoint admin role needed | €0 |
| Entra app for PnP with **delegated** permissions | the existing "MG Lab PnP" app (or `episodes/06-sharepoint-migration-pnp/setup/register-pnp-app.sh`) | €0 |
| PowerShell 7.4+ with PnP.PowerShell 3.x and Pester | `Install-Module PnP.PowerShell, Pester -Scope CurrentUser` | €0 |
| A lab user to act as requester | **Alex Demo** (`alex.demo`) | €0 |

## Set-up (before recording)
```powershell
cd series/sharepoint/episodes/01-lists-libraries-best-practices
Invoke-Pester ./tests -Output Detailed                        # expect 31 passed
$site = 'https://<lab-tenant>.sharepoint.com/sites/ListsDemo'  # never on screen unmasked
$app  = '<MG Lab PnP client id>'
./src/Invoke-ListDesign.ps1 -DesignPath ./src/designs/purchase-requests.json -SiteUrl $site -ClientId $app -WhatIf
```
Check the `-WhatIf` plan lists 2 lists, 2 versioning settings, 10 columns, 5 views (RemoveView only appears on a real
run, once the lists exist). Use a terminal with a dark theme and font size 18+. Clear the screen before each capture.

## Screens to capture (match the `screen` scenes in script.yaml)

1. **`screens/provision.jpg` — scene `provision`**
   Run (device-code sign-in happens before the capture; don't record the code):
   ```powershell
   ./src/Invoke-ListDesign.ps1 -DesignPath ./src/designs/purchase-requests.json -SiteUrl $site -ClientId $app `
       -SeedItems 40 -RequesterEmail <alex.demo UPN>
   ```
   Capture: "Lint ... No findings", the provisioning log (CreateList, SetVersioning, AddField ... indexed, AddView,
   RemoveView), "Seeded 40 items", and both "Audit (live)" blocks ending in "No findings".
   If the live audit reports anything, **record what it says** and update the script/README — don't edit the output.

2. **`screens/indexed-columns.jpg` — scene `indexes`**
   Browser: Purchase Requests → Settings → List settings → **Indexed columns** (four: Status, Requester, Department,
   Due date). Optional second capture for the same scene: Contracts → Library settings → **Versioning settings**
   showing automatic version history limits.

3. **`screens/open-requests.jpg` — scene `view`**
   Browser: Purchase Requests, view **My open requests**, view picker open (Open requests / My open requests /
   Due in 7 days). Rows show fictional titles ("Laptop #003" …) and the requester.

4. **`screens/audit.jpg` — scene `audit`**
   ```powershell
   ./src/Invoke-ListDesign.ps1 -DesignPath ./src/designs/audit-demo.json -SiteUrl $site -ClientId $app -Force
   cls
   ./src/Invoke-ListDesign.ps1 -AuditList 'Legacy Requests' -ExpectedItems 60000 -SiteUrl $site -ClientId $app
   ```
   Expected: LD012 on "All Items" and "Everything", LD013 on "Big ones". Capture only the audit output.

After capturing, add `crop`/`highlight` to each screen scene if needed (see episode 07's script for the format).

## Masking
- Tenant host in URLs and in `$site` (use `pipeline/mask.js` in the browser; blur the terminal line if it shows).
- The PnP app client id, the device-login code, account avatars and the real UPN of the requester (seed with the demo
  account whose display name is fictional).
- Nothing in the seeded data is real (fixed seed, fictional item names).

## Tear-down
```powershell
Connect-PnPOnline -Url $site -ClientId $app -DeviceLogin
Remove-PnPList -Identity 'Purchase Requests' -Recycle -Force   # keep it if episode 02 is recorded next: it formats this list
Remove-PnPList -Identity 'Contracts' -Recycle -Force
Remove-PnPList -Identity 'Legacy Requests' -Recycle -Force
```
With `-Recycle` the lists go to the site recycle bin (without it they are deleted directly); empty it if the site is reused for other demos.
