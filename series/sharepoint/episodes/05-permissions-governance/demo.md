# Demo shot list — SharePoint #5 Permissions and governance

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure / Power Platform | none (no Hyper-V VM, no Azure resource group) |
| Tenant | **SharePoint** + **Purview** in the lab tenant (Microsoft 365 E5 trial, until 20 Dec 2026; SharePoint Advanced Management is **not** used). Episode 3's communication site `/sites/Purchasing` (*Contoso Purchasing*) with episode 4's **Supplier Documents** library filed: it must contain a Fabrikam contract (`CTR-* Fabrikam*`) and a Northwind Traders invoice (`INV-* Northwind Traders*`); the *Purchase Requests* list is optional (drift step 3 is skipped without it). Changed here: site sharing settings, a direct Full Control grant, broken inheritance on two lists and one file, an organization edit link, a *Contract Managers* group, the Confidential label on the site (remediation and tear-down undo them) |
| Lab users | `labadmin` (Lab Admin, the recording account): runs every script and the browser steps; site collection admin and the only member of *Contoso Purchasing Owners* (as episode 3 left it, which is what makes GV005 "1 owner(s)" appear). `alex.demo` (**Alex Demo**): the drift script's `-DirectUser` (Full Control on the site, Contribute on Purchase Requests). `sam.demo` (**Sam Demo**): member of *Contoso Purchasing Members* (added in set-up) and `-ShareWithUser` (the Fabrikam contract is shared with Sam). `jordan.demo` (**Jordan Demo**): `-ContractManager`, the only member of the *Contract Managers* group. Alex, Sam and Jordan never sign in; they only need to exist with their E5 licences |
| Roles | `labadmin`: **SharePoint Administrator** (already assigned in episode 3; needed for `Set-PnPTenantSite` and the admin center) and site collection admin on the site. One-time label set-up (below): a **Global Administrator** for the Entra `EnableMIPLabels` group setting and `Execute-AzureAdLabelSync`, and **Compliance Administrator** or **Information Protection Admins** to create and publish the label. If labadmin doesn't hold these, assign them in the Entra admin center before the label set-up and remove them in tear-down |
| Labels | Purview sensitivity label **Confidential**, scope *Groups & sites*, *External sharing and Conditional Access* → *Only people in your organization*, published in a label policy that includes `labadmin`. Created at least a day before recording (a new label needs time to reach SharePoint; label sync to Entra can take up to 24 h). It may stay in the tenant for later episodes |
| Entra | The existing "MG Lab PnP" app registration (delegated SharePoint permissions plus delegated Microsoft Graph permissions for files/sites, used by `Get-PnPFileSharingLink` / `Remove-PnPFileSharingLink`) |
| Licences / trials | lab E5 trial licences for the four users above; cost €0 |
| Recording machine | The Windows lab laptop: PowerShell 7.4+ with PnP.PowerShell 3.x, Pester and ExchangeOnlineManagement (Security & Compliance PowerShell for `Get-Label`); browser with `pipeline/mask.js`, signed in to the lab tenant as labadmin, for the site permissions and admin center screens |

The code scenes are real output from this folder (policy lint, offline audit of the fixture, Pester). The four
`screen` scenes need the lab tenant. **Needs tenant:** `Get-MgPermissionSnapshot`, `Get-MgRoleAssignment`,
`Invoke-MgRemediation`, `New-PermissionDrift.ps1` and every `-SiteUrl` path of `Invoke-Governance.ps1`. Locally they
are covered by Pester tests that mock the real PnP cmdlets (parameter names and types are checked);
`Get-MgRoleAssignment` (CSOM role assignments) has no local test at all.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Lab tenant, Microsoft 365 E5 trial | SharePoint + Purview sensitivity labels. **SharePoint Advanced Management is not used** (not in E5: needs a Copilot licence or the SAM Plan 1 add-on) | €0 (trial until 20 Dec 2026) |
| The episode 3 **Contoso Purchasing** site with the episode 4 **Supplier Documents** library filed | the drift script needs a Fabrikam contract and a Northwind Traders invoice; *Purchase Requests* is optional (step skipped if missing) | €0 |
| Lab users | `labadmin` runs everything (site owner and site collection admin); `alex.demo` (Alex Demo, direct Full Control), `sam.demo` (Sam Demo, member + the shared contract), `jordan.demo` (Jordan Demo, Contract Managers) | €0 (E5 trial licences) |
| **SharePoint Administrator** role for `labadmin`, and site collection admin on the site | site sharing settings and the label need the SharePoint admin role | €0 |
| Entra app for PnP with **delegated** permissions | the existing "MG Lab PnP" app. `Get-PnPFileSharingLink`/`Remove-PnPFileSharingLink` go through Microsoft Graph: check the app has delegated Graph permissions for files/sites before the day | €0 |
| A sensitivity label **Confidential** scoped to *Groups & sites* | see "Label set-up" below; do it at least a day before (a new label needs at least an hour) | €0 (E5) |
| PowerShell 7.4+ with PnP.PowerShell 3.x, Pester; Security & Compliance PowerShell (ExchangeOnlineManagement) for `Get-Label` | `Install-Module PnP.PowerShell, Pester, ExchangeOnlineManagement -Scope CurrentUser` | €0 |

### Label set-up (once, a day before)
1. Enable labels for groups and sites in Entra (`EnableMIPLabels = True` in the group settings — follow
   *Assign sensitivity labels to Microsoft 365 groups in Microsoft Entra ID*), then in Security & Compliance
   PowerShell run `Execute-AzureAdLabelSync`.
2. Purview portal → Information protection → Labels → create **Confidential**, scope *Groups & sites*, protection
   settings: *External sharing and Conditional Access* → *Only people in your organization*. Publish it in a label
   policy that includes `labadmin`.
3. `Connect-IPPSSession`, then `Get-Label | ft Name, Guid` → note the GUID (never on screen) as `$label`.

## Set-up (before recording)
```powershell
cd series/sharepoint/episodes/05-permissions-governance
Invoke-Pester ./tests -Output Detailed                        # expect 23 passed
$site  = 'https://<lab-tenant>.sharepoint.com/sites/Purchasing'   # never on screen unmasked
$app   = '<MG Lab PnP client id>'
$label = '<Confidential label GUID>'
Connect-PnPOnline -Url $site -ClientId $app -DeviceLogin      # as labadmin
Add-PnPGroupMember -Group 'Contoso Purchasing Members' -LoginName <sam.demo UPN>   # if episode 3 didn't add Sam
./src/New-PermissionDrift.ps1 -SiteUrl $site -ClientId $app -DirectUser <alex.demo UPN> -ShareWithUser <sam.demo UPN> `
    -ContractManager <jordan.demo UPN> -WhatIf                # read the plan, then run without -WhatIf
./src/New-PermissionDrift.ps1 -SiteUrl $site -ClientId $app -DirectUser <alex.demo UPN> -ShareWithUser <sam.demo UPN> -ContractManager <jordan.demo UPN>
```
Then the manual step: on the site, **Settings → Site permissions → Share site**, add *Everyone except external users*
with **Read** (it lands in the Visitors group). If the tenant hides that claim in the people picker, note it and skip
(GV007 then won't appear; adjust the narration of `eeeu` and `audit`).

Dark terminal theme, font 18+, clear the screen before each capture.

## Screens to capture (match the `screen` scenes in script.yaml)

1. **`screens/eeeu.jpg` — scene `eeeu`**
   Browser on the site: **Settings → Site permissions**, *Site visitors* expanded showing *Everyone except external
   users* (Read). If possible a second capture of **Advanced permissions settings** showing Alex Demo with Full Control.

2. **`screens/audit-live.jpg` — scene `audit`**
   ```powershell
   ./src/Invoke-Governance.ps1 -PolicyPath ./src/governance/purchasing.policy.json -SiteUrl $site -ClientId $app `
       -SensitivityLabelId $label -ExportSnapshot ./src/snapshots/before.json
   ```
   Expected (same as the fixture): policy "No findings"; GV001, GV004, GV007, GV009 errors; GV002, GV003, GV005,
   GV008, GV010, GV011, GV012, GV014 warnings; "4 error(s), 8 warning(s); 11 can be fixed automatically".
   **Record what it really says.** Check, and note in README if different:
   - GV011 appears for *Contoso Purchasing Members* on Supplier Documents (proves `-CopyRoleAssignments` copied it).
   - GV012 lists the Fabrikam contract (proves `Get-PnPListItem -Includes HasUniqueRoleAssignments` loads the flag).
   - GV014 lists the Northwind invoice with scope Organization (Graph link scope as PnP reports it).
   - In `snapshots/before.json`, the `principalType` of *Everyone except external users* (expected `SecurityGroup`).
   If a cmdlet fails, record the error and fix the module before re-recording — don't stage it.

3. **`screens/remediate.jpg` — scene `remediate`**
   ```powershell
   ./src/Invoke-Governance.ps1 -PolicyPath ./src/governance/purchasing.policy.json -SiteUrl $site -ClientId $app -SensitivityLabelId $label -Fix -WhatIf
   ./src/Invoke-Governance.ps1 -PolicyPath ./src/governance/purchasing.policy.json -SiteUrl $site -ClientId $app -SensitivityLabelId $label -Fix
   ```
   Capture the second run: seven "done" rows, then "Audit after remediation:" with only GV005. Check:
   `Set-PnPTenantSite -SensitivityLabel <GUID>` applied the label to a communication site; `Remove-PnPFileSharingLink`
   removed the organization link (open the invoice's *Manage access* to confirm).

4. **`screens/admin-center.jpg` — scene `admin`**
   SharePoint admin center → **Sites → Active sites**, columns *Sensitivity* and *External sharing* visible, the
   Contoso Purchasing row: *Confidential*, *Only people in your organization*. Optional: the details pane, *Policies*
   tab.

After capturing, add `crop`/`highlight` to each screen scene if needed (see episode 07's script for the format).

## Masking
- Tenant host in the address bar, in `$site` and in the snapshot path output; PnP client id; label GUID; device code.
- Account names, avatars and UPNs: the lab users' display names (Alex Demo, Sam Demo, Jordan Demo) are fictional
  and can stay; blur the tenant domain in their login names (plan rows) and labadmin's name/avatar in the browser.
- The admin center lists other lab sites: crop to the Contoso Purchasing row.
- `src/snapshots/` contains real login names: it's git-ignored; don't commit it.

## Tear-down
```powershell
Connect-PnPOnline -Url $site -ClientId $app -DeviceLogin
Remove-PnPGroup -Identity 'Contract Managers' -Force
Remove-PnPGroupMember -Group 'Contoso Purchasing Members' -LoginName <sam.demo UPN>   # if added in set-up
Set-PnPList -Identity 'Supplier Documents' -ResetRoleInheritance   # if episode 6 doesn't need it restricted
```
To remove the label (optional, episode 6 can keep it): admin center → Active sites → the site → *Policies* →
*Sensitivity* → none. The remediation already restores sharing, links, grants and inheritance. Delete `src/snapshots/` locally. The
**Confidential** label and its policy can stay in the tenant (other episodes may use it). Remove any Entra/Purview
role assigned to labadmin only for the label set-up.
