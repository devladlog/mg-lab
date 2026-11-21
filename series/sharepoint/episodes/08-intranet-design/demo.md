# Demo shot list — SharePoint #8 Intranet design

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure / Power Platform | none |
| Tenant | **SharePoint** in the lab tenant, with the episode 7 result in place: hub `/sites/Operations`, associated `/sites/Purchasing` and `/sites/Facilities`, the three Entra groups. Created here: communication site `/sites/Intranet` (the home site), library `BrandImages` on it, the tenant theme *Contoso Operations*, the home site setting, one organization news site, one organization assets library, the home site navigation |
| Entra groups | **Purchasing Team** (alex.demo, labadmin) from episode 7; nothing new |
| Lab users | `labadmin` records (SharePoint Administrator role, exists); `alex.demo` for the browser screens |
| Entra app | The existing "MG Lab PnP" app (delegated). For audiences by name it needs Microsoft Graph **Group.Read.All** (delegated, admin consent; added in episode 7), otherwise paste the group object ID into the blueprint's `audiences` (never commit it) |
| Licences / trials | lab E5 licences; cost €0. No SharePoint Advanced Management, no Premium |
| Recording machine | The Windows lab laptop: PowerShell 7.4+ with PnP.PowerShell 3.x and Pester; browser with `pipeline/mask.js` |

The code scenes are real output from this folder (lint, contrast, Pester). The four `screen` scenes need the lab tenant.
**Needs tenant:** `Invoke-MgTenantTheme`, `Invoke-MgHomeSite`, `Invoke-MgOrgNews`, `Invoke-MgOrgAssets`,
`Invoke-MgGlobalNavigation`, `Get-MgIntranetState` and the `-Provision` / `-Check` paths of `Invoke-IntranetDesign.ps1`.
Locally they are covered only by Pester tests that mock the real PnP cmdlets (parameter names and types are checked).

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Episode 7 in place | hub, `/sites/Purchasing` (with `how-to-buy`, `SupplierDocuments`), `/sites/Facilities` (with `office-moves`), group *Purchasing Team*. The navigation links to their pages | €0 |
| SharePoint Administrator for `labadmin` | home site, news sites, assets library, tenant theme | €0 |
| PowerShell 7.4+, PnP.PowerShell 3.x, Pester | `Install-Module PnP.PowerShell, Pester -Scope CurrentUser` | €0 |
| A decision about the home site | **The home site is a tenant-wide setting.** First note whether the lab already has one (`Get-PnPHomeSite` below). Setting `/sites/Intranet` replaces it; tear-down restores the old value, or removes it if there was none | — |

## Set-up (before recording)
```powershell
cd series/sharepoint/episodes/08-intranet-design
Invoke-Pester ./tests -Output Detailed                                     # expect 22 passed
$tenant = 'https://<lab-tenant>.sharepoint.com'                             # never on screen unmasked
$t = @{ TenantUrl = $tenant; AdminUrl = 'https://<lab-tenant>-admin.sharepoint.com'; ClientId = '<MG Lab PnP client id>' }

Connect-PnPOnline -Url $t.AdminUrl -ClientId $t.ClientId -DeviceLogin
Get-PnPHomeSite                       # NOTE THE VALUE (empty = none). Needed for tear-down
Get-PnPOrgNewsSite                    # note too
Get-PnPOrgAssetsLibrary               # note too: all organization asset libraries must be on the same site
New-PnPSite -Type CommunicationSite -Title 'Contoso Intranet' -Url "$tenant/sites/Intranet" -Wait

./src/Invoke-IntranetDesign.ps1 -BlueprintPath ./src/intranet/contoso-intranet.json @t -Provision -WhatIf
```
- If the lab already has organization asset libraries on another site, **stop**: the blueprint's library must be on
  the same site (IN004). Either record on a tenant without them, or change the blueprint's library URL to that site.
- Share the home site with everyone: browser, `/sites/Intranet` → Share → **Everyone except external users** as
  *visitors* (read). This is what IL005 checks and what the organization assets library requires. Do it before the
  `-Provision` run.
- The `-WhatIf` run must show `AddTheme`, two `ApplyTheme`, `SetHomeSite`, `AddOrgNews`, `CreateLibrary`, two `Upload`,
  `AddOrgAssets`, `SetWeb` and twelve `AddNode` lines (plus `RemoveNode` for the default nodes of the new site). Three
  device-code sign-ins happen (admin, home site, Graph for the group): do them off camera. Dark terminal, font 18+,
  clear before each capture.
- Do the global navigation switch and `-Provision` **the day before** the browser screens: Learn says global
  navigation can take up to 24 hours to reach users (and "a few minutes" after saving the settings).

## Screens to capture (match the `screen` scenes in script.yaml)

1. **`screens/provision.jpg` — scene `provision`**
   ```powershell
   ./src/Invoke-IntranetDesign.ps1 -BlueprintPath ./src/intranet/contoso-intranet.json @t -Provision
   ```
   Capture: the three contrast ratios (12.98, 7.38, 7.38), `0 error(s), 0 warning(s)`, `Theme:` (AddTheme, ApplyTheme ×2),
   `Home site and news:` (SetHomeSite, AddOrgNews), `Organization assets:` (CreateLibrary, Upload ×2, AddOrgAssets),
   `Global navigation (home site navigation):` (SetWeb, RemoveNode lines, 12 AddNode lines).
   **Record what really happens.** Check in particular:
   - Whether `Set-PnPHomeSite -Force` is needed or accepted when the tenant has no home site yet.
   - The shape of `Get-PnPOrgAssetsLibrary` output (README "Not verified yet"); the module reads
     `OrgAssetsLibraries[].LibraryUrl.DecodedUrl`. If a second run registers the library again, fix `Invoke-MgOrgAssets`.
   - That `Add-PnPOrgAssetsLibrary` asks to enable the CDN (private by default) and what it prints.
   - Which default nodes the new site had in its navigation, and whether links to the hub's sites work without `-External`
     (same question as episode 7).
   - That `Set-PnPWebTheme` applies the theme to `/sites/Intranet` and `/sites/Operations`; open `/sites/Purchasing` and
     `/sites/Facilities` and note whether they follow the hub's theme and how long it takes.

2. **`screens/app-bar.jpg` — scene `appbar`**
   First, as `labadmin` in the browser on `/sites/Intranet` home: **Settings → Global navigation**, *Enable global navigation*
   on, Title `Contoso`, Logo: `contoso-globalnav-20.png` from the Brand Images library (20×20 PNG), Navigation source
   *Home site navigation*, Save. Capture that panel (short, 3 s) or do it off camera. Then, as **Alex Demo**, on any
   SharePoint page (for example `/sites/Purchasing`): the app bar on the left, the Contoso logo selected, the panel open
   with *Work* (*Operations* → Contoso Operations, Purchasing, Facilities) and *How do I* (*Everyday tasks* → Buy something,
   Move office; *Purchasing team* → Supplier documents). If the panel is empty or missing, wait (up to 24 hours) and retry;
   write the observed delay in README. A second capture as Sam Demo (no *Purchasing team* label) is optional if targeting
   works the same as in episode 7.

3. **`screens/picker.jpg` — scene `picker`**
   Browser as **Alex Demo**, `/sites/Purchasing`: edit a page, add an **Image** web part, *Change* → in the file picker,
   left pane **Your organization**: the card for the library (the thumbnail is the Contoso logo; Learn: the name shown is
   the organization's name), open it: the two logos. If "Your organization" doesn't appear yet, wait and retry (the library
   is served from a CDN; Learn gives no delay for images). Discard the page edit afterwards.

4. **`screens/check.jpg` — scene `check`**
   ```powershell
   ./src/Invoke-IntranetDesign.ps1 -BlueprintPath ./src/intranet/contoso-intranet.json @t -Check      # expect "No findings."
   ```
   Then in the browser on the home site: navigation **Edit** → rename *How do I* to *How to* → Save; run `-Check` again:
   expect `IL006  How do I  Title: tenant has 'How to'.` and `1 error(s), 0 warning(s)`. Capture both runs. Run
   `-Provision` once more afterwards to restore the plan (expect RemoveNode + AddNode lines).
   If `-Check` reports differences right after provisioning (for example IL005 because the visitors group isn't listed
   as *Everyone except external users*, or IL003 because of the library URL format), record them: they are the gaps in
   README "Not verified yet". Fix the module (`Get-MgKey`, the visitor title) and the README rather than hiding them.

After capturing, add `crop`/`highlight` to each screen scene if needed (see `episodes/07-pcf-code-component/script.yaml` in the repo root for the format).

## Code scenes to rehearse (no tenant)
```powershell
cd src
./Invoke-IntranetDesign.ps1 -BlueprintPath ./bad/bad-intranet.json           # 6 error(s), 6 warning(s)
./Invoke-IntranetDesign.ps1 -ThemePath ./bad/custom-cyan.theme.json          # 1.25:1, 2 errors
./Invoke-IntranetDesign.ps1 -ThemePath ./fixtures/learn-default-themes.json  # ten themes ok
./Invoke-IntranetDesign.ps1 -BlueprintPath ./intranet/contoso-intranet.json  # 12.98 / 7.38 / 7.38, no findings
```

## Masking
- Tenant host in address bars and in `$t`; PnP client id; device-login codes; the group object ID if printed.
- The org name shown in the image picker card if it is the real tenant's name (Learn: the library is shown under the
  organization's name): blur it or use the masking script's selector.
- Account pictures/initials of real people (only lab users should appear); the admin account name.
- Site, group and user names are fictional.

## Tear-down
Keep the hub from episode 7 if episode 9 builds on it. For this episode:
```powershell
Connect-PnPOnline -Url $t.AdminUrl -ClientId $t.ClientId -DeviceLogin
Remove-PnPOrgAssetsLibrary -LibraryUrl "$tenant/sites/Intranet/BrandImages"
Remove-PnPOrgNewsSite -OrgNewsSiteUrl "$tenant/sites/Operations"
Remove-PnPHomeSite -Force                                   # if there was no home site before; otherwise
# Set-PnPHomeSite -HomeSiteUrl '<the value noted in set-up>' -Force
Remove-PnPTenantTheme -Identity 'Contoso Operations'
Remove-PnPTenantSite -Url "$tenant/sites/Intranet" -Force
```
Restore the theme of `/sites/Operations`, `/sites/Purchasing` and `/sites/Facilities` from the browser (*Change the look*)
if they should go back to a default theme. Switch global navigation off first if it is still on (home site → Settings →
Global navigation) so the app bar doesn't point at a deleted site. If the organization news list had other sites before,
make sure they are still there.
