# Demo shot list — SharePoint #3 Modern sites and pages

The code scenes are real output from this folder (lint, Pester). The four `screen` scenes need the lab tenant.
**Needs tenant:** `Invoke-MgSiteTemplateRegistration`, `Invoke-MgSiteTemplateApply`, `Get-MgSiteTemplateRunReport`,
`Invoke-MgPageProvisioning`, `Export-MgSiteScript`, and every non-lint path of `Invoke-ModernSite.ps1`. Locally they
are covered only by Pester tests that mock the real PnP cmdlets (parameter names and types are checked), and the
entry script only by a parse check and its lint-only mode.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Lab Microsoft 365 tenant with SharePoint | existing lab tenant | €0 (existing licences) |
| **SharePoint admin** role for the recording account | registering site scripts / site templates is tenant-level (exists) | €0 |
| Entra app for PnP with **delegated** permissions | the existing "MG Lab PnP" app (or `episodes/06-sharepoint-migration-pnp/setup/register-pnp-app.sh`) | €0 |
| PowerShell 7.4+ with PnP.PowerShell 3.x and Pester | `Install-Module PnP.PowerShell, Pester -Scope CurrentUser` | €0 |
| Free slots: the tenant must have fewer than 100 site scripts and 100 site templates | `Get-PnPSiteScript`, `Get-PnPSiteDesign` (connected to the admin URL) | €0 |
| One hand-built site for the export scene | e.g. the existing MGLabDemo site, or the episode 1 `ListsDemo` site | €0 |

## Set-up (before recording)
```powershell
cd series/sharepoint/episodes/03-modern-sites-pages
Invoke-Pester ./tests -Output Detailed                                # expect 40 passed
$admin = 'https://<lab-tenant>-admin.sharepoint.com'                  # never on screen unmasked
$site  = 'https://<lab-tenant>.sharepoint.com/sites/Purchasing'       # must not exist yet (or reuse it)
$app   = '<MG Lab PnP client id>'
./src/Invoke-ModernSite.ps1 -TemplatePath ./src/purchasing/template.json -AdminUrl $admin -SiteUrl $site -ClientId $app -CreateSite -WhatIf
```
The `-WhatIf` run signs in to the admin URL (device code: do it before recording) and prints AddScript, AddTemplate,
then the page plan. Three device-code sign-ins happen in a full run (admin, then site); check whether PnP reuses the
token, and if not, do the sign-ins off camera and cut. Dark terminal theme, font 18+, clear the screen before each
capture.

## Screens to capture (match the `screen` scenes in script.yaml)

1. **`screens/apply-run.jpg` — scene `apply`**
   ```powershell
   ./src/Invoke-ModernSite.ps1 -TemplatePath ./src/purchasing/template.json -AdminUrl $admin -SiteUrl $site -ClientId $app -CreateSite
   ```
   Capture: "Lint ... No findings", AddScript / AddTemplate, CreateSite, QueueTemplate, the **Template run:** block
   (one line per action), then AddPage ... SetHomePage. **If any action reports Failure, record it as is** and update
   the README gotchas and the narration — don't stage it. If the run block is empty (still running after
   `-WaitSeconds 180`), run `./src/Invoke-ModernSite.ps1 -RunReport -AdminUrl $admin -SiteUrl $site -ClientId $app`
   and capture that instead. Verify the report shows *this* run (we take the first run returned for the template ID).

2. **`screens/site-settings.jpg` — scene `site`**
   Browser on the new site: compact header, mega menu with **How to buy** and **FAQ**, footer link **Purchasing
   policy**. Optional second capture for the same scene: Settings → Site information → View all site settings →
   **Regional settings** (locale Portuguese (Portugal), time zone GMT, 24-hour). If the locale shows something else,
   record it and fix the narration.

3. **`screens/home-page.jpg` — scene `home`**
   Browser on the site home (should now be `purchasing-home.aspx`): the two text columns, the **News** web part with
   "New approval limits from January", and the **Purchasing FAQ** list web part. Add two or three FAQ items first
   (fictional questions, e.g. "Who approves a request above 1,000 EUR?"). **Check the List web part shows the FAQ
   list**: the property names `isDocumentLibrary` / `selectedListId` are not verified; if it renders empty, open the
   web part, select the list, compare with `Get-PnPPageComponent`/the page JSON, fix the page design and re-run with
   `-Force`.

4. **`screens/export-lint.jpg` — scene `export`**
   ```powershell
   cd $env:TEMP   # the export is written to the current folder
   <repo>/series/sharepoint/episodes/03-modern-sites-pages/src/Invoke-ModernSite.ps1 -ExportFrom https://<lab-tenant>.sharepoint.com/sites/MGLabDemo -ClientId $app
   ```
   Capture "Exported to ..." and whatever the lint reports. Add `-Lists 'Lists/<name>'` to include a list. Don't
   commit the exported file if it contains real names or URLs.

After capturing, add `crop`/`highlight` to each screen scene if needed (see episode 07's script for the format).

## Masking
- Tenant host in every URL (`pipeline/mask.js` in the browser; blur the terminal lines with `$admin`, `$site`).
- The PnP client id, device-login codes, account avatars and names (use the demo account shown as "Alex Demo").
- The exported site script may contain the real site's list names and URLs: review before showing.

## Tear-down
```powershell
Connect-PnPOnline -Url $admin -ClientId $app -DeviceLogin
Get-PnPSiteDesign | Where-Object Title -eq 'Contoso Purchasing' | ForEach-Object { Remove-PnPSiteDesign -Identity $_.Id -Force }
Get-PnPSiteScript | Where-Object Title -like 'Contoso Purchasing - *' | ForEach-Object { Remove-PnPSiteScript -Identity $_.Id -Force }
Remove-PnPTenantSite -Url $site -Force          # goes to the deleted sites list; keep it if episode 7 (hubs) reuses it
```
Removing the template doesn't undo what it already applied to the site; deleting the site does.
