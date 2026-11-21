# Demo shot list — SharePoint #5 Permissions and governance

The code scenes are real output from this folder (policy lint, offline audit of the fixture, Pester). The four
`screen` scenes need the lab tenant. **Needs tenant:** `Get-MgPermissionSnapshot`, `Get-MgRoleAssignment`,
`Invoke-MgRemediation`, `New-PermissionDrift.ps1` and every `-SiteUrl` path of `Invoke-Governance.ps1`. Locally they
are covered by Pester tests that mock the real PnP cmdlets (parameter names and types are checked);
`Get-MgRoleAssignment` (CSOM role assignments) has no local test at all.

No VMs and no Azure resources: everything runs on the recording laptop (PowerShell 7 + browser) against the lab tenant.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Lab tenant, Microsoft 365 E5 trial | SharePoint + Purview sensitivity labels. **SharePoint Advanced Management is not used** (not in E5: needs a Copilot licence or the SAM Plan 1 add-on) | €0 (trial until 20 Dec 2026) |
| The episode 3 **Contoso Purchasing** site with the episode 4 **Supplier Documents** library filed | the drift script needs a Fabrikam contract and a Northwind Traders invoice; *Purchase Requests* is optional (step skipped if missing) | €0 |
| Four demo users | shown as Alex Demo (owner, runs the scripts), Lee Gu, Megan Bowen, Isaiah Langer: any lab accounts, display names masked if they differ | €0 (E5 trial licences) |
| **SharePoint Administrator** role for the account running the scripts, and site collection admin on the site | site sharing settings and the label need the SharePoint admin role | €0 |
| Entra app for PnP with **delegated** permissions | the existing "MG Lab PnP" app. `Get-PnPFileSharingLink`/`Remove-PnPFileSharingLink` go through Microsoft Graph: check the app has delegated Graph permissions for files/sites before the day | €0 |
| A sensitivity label **Confidential** scoped to *Groups & sites* | see "Label set-up" below; do it at least a day before (a new label needs at least an hour) | €0 (E5) |
| PowerShell 7.4+ with PnP.PowerShell 3.x, Pester; Security & Compliance PowerShell (ExchangeOnlineManagement) for `Get-Label` | `Install-Module PnP.PowerShell, Pester, ExchangeOnlineManagement -Scope CurrentUser` | €0 |

### Label set-up (once, a day before)
1. Enable labels for groups and sites in Entra (`EnableMIPLabels = True` in the group settings — follow
   *Assign sensitivity labels to Microsoft 365 groups in Microsoft Entra ID*), then in Security & Compliance
   PowerShell run `Execute-AzureAdLabelSync`.
2. Purview portal → Information protection → Labels → create **Confidential**, scope *Groups & sites*, protection
   settings: *External sharing and Conditional Access* → *Only people in your organization*. Publish it in a label
   policy to the demo users.
3. `Connect-IPPSSession`, then `Get-Label | ft Name, Guid` → note the GUID (never on screen) as `$label`.

## Set-up (before recording)
```powershell
cd series/sharepoint/episodes/05-permissions-governance
Invoke-Pester ./tests -Output Detailed                        # expect 23 passed
$site  = 'https://<lab-tenant>.sharepoint.com/sites/Purchasing'   # never on screen unmasked
$app   = '<MG Lab PnP client id>'
$label = '<Confidential label GUID>'
./src/New-PermissionDrift.ps1 -SiteUrl $site -ClientId $app -DirectUser <lee upn> -ShareWithUser <megan upn> `
    -ContractManager <isaiah upn> -WhatIf                     # read the plan, then run without -WhatIf
./src/New-PermissionDrift.ps1 -SiteUrl $site -ClientId $app -DirectUser <lee upn> -ShareWithUser <megan upn> -ContractManager <isaiah upn>
```
Then the manual step: on the site, **Settings → Site permissions → Share site**, add *Everyone except external users*
with **Read** (it lands in the Visitors group). If the tenant hides that claim in the people picker, note it and skip
(GV007 then won't appear; adjust the narration of `eeeu` and `audit`).

Dark terminal theme, font 18+, clear the screen before each capture.

## Screens to capture (match the `screen` scenes in script.yaml)

1. **`screens/eeeu.jpg` — scene `eeeu`**
   Browser on the site: **Settings → Site permissions**, *Site visitors* expanded showing *Everyone except external
   users* (Read). If possible a second capture of **Advanced permissions settings** showing Lee Gu with Full Control.

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
- Account names, avatars and UPNs: real lab users appear in the terminal (login names in the plan rows) — blur them
  or rename the lab users to the fictional display names before recording.
- The admin center lists other lab sites: crop to the Contoso Purchasing row.
- `src/snapshots/` contains real login names: it's git-ignored; don't commit it.

## Tear-down
```powershell
Connect-PnPOnline -Url $site -ClientId $app -DeviceLogin
Remove-PnPGroup -Identity 'Contract Managers' -Force
Set-PnPList -Identity 'Supplier Documents' -ResetRoleInheritance   # if episode 6 doesn't need it restricted
```
To remove the label (optional, episode 6 can keep it): admin center → Active sites → the site → *Policies* →
*Sensitivity* → none. The remediation already restores sharing, links, grants and inheritance. Delete `src/snapshots/` locally. The
**Confidential** label and its policy can stay in the tenant (other episodes may use it).
