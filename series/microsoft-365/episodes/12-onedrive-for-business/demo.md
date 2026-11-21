# Demo shot list — DEVLADLOG Microsoft 365 #12: OneDrive for Business

Everything in `src/` and `tests/` already ran in the build container (47 Pester tests, an offline report from fictional data). The registry half was only tested against a **fake registry**: its first real run is
the one recorded here. This file lists what the human-supervised session must set up and record. Every step below is **needs tenant** or **needs VM**. Every screen shows the real product (the admin center,
the script on the real Windows PC, the real OneDrive sync app). `tests/fixtures/*` and `sample/` never appear on screen.

No purchase, no cost, no new VM: it reuses the existing lab VM.

## Lab environment

| Item | Notes | Cost / requirement |
|---|---|---|
| Microsoft 365 E5 trial (already in the lab, until 20 Dec 2026) | Includes OneDrive for Business; see `series/LAB.md` | in the lab |
| Lab VM `CON-W11-01` (Windows 11, from episode 7) | Entra-joined, signed in as `alex.demo`; the OneDrive sync app must be present. **Not verified:** that the image ships it: if it does not, install it from Microsoft before recording (off camera) | existing VM, running only while recording |
| Lab users | `labadmin` (recording account, Global Administrator), `alex.demo` (signs in on the VM), `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo` | none |
| Roles | `labadmin` as Global Administrator: reads tenant settings, the usage reports and changes the Reports org setting (Learn: only a Global Administrator can) | none |
| Graph scopes (delegated, consent for `labadmin`) | `SharePointTenantSettings.Read.All`, `Reports.Read.All`, `ReportSettings.Read.All` | none |
| Host PowerShell (lab desktop) | PowerShell 7.2+, `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser` | none |
| VM PowerShell | PowerShell 7.2+ elevated (Run as administrator). Windows PowerShell 5.1 is not enough (`#Requires -Version 7.2`) | none |

## Setup (before recording, at least a few days before: the usage report needs data)

1. **Module on the host.** `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser`.
2. **Remember the real values.** Off camera, with `labadmin`: `Connect-MgGraph -Scopes SharePointTenantSettings.Read.All -NoWelcome`, then
   `Invoke-MgGraphRequest -Uri /v1.0/admin/sharepoint/settings -OutputType PSObject | Select-Object personalSiteDefaultStorageLimitInMB, deletedUserPersonalSiteRetentionPeriodInDays, isUnmanagedSyncAppForTenantRestricted, isSyncButtonHiddenOnPersonalSite, isMacSyncAppEnabled`.
   Note them. This episode changes nothing in the tenant, but the audit's baseline must be edited against them.
3. **Give the lab OneDrives a story** (only the tenant's own lab users, a few days before):
   - `alex.demo`, `jordan.demo`, `taylor.demo`: each uploads some files to OneDrive (browser). `sam.demo`: uploads one file and is then left alone.
   - `riley.demo`: opens OneDrive once, no files (it should say `NeverUsed`; a OneDrive is only created when the user first opens it or an admin pre-provisions it: **Not verified** that the lab user already has one).
   - **Near full:** Microsoft 365 admin center > Users > Active users > `taylor.demo` > OneDrive > *Storage used* > set the maximum storage to 1 GB, then upload files totalling over 900 MB (a copied folder is fine). Write down the old value; tear-down 3.
   - **Deleted user (optional):** create `casey.former@...`, let it open OneDrive, delete the user at least 7 days before recording (Learn: the OneDrive stays for the retention period). **Not verified:** how soon the account shows `Is Deleted` in the report. If it does not show up, skip `DeletedRetained` and edit the narration.
4. **Config.** Copy `src/onedrive-baseline.json` to `onedrive-baseline.lab.json` (outside the repo) and edit: `accounts.inactiveDays` smaller than the age of `sam.demo`'s single upload (for example `3`; say on camera that production is 180);
   `accounts.nearFullPercent: 90`; `settings` to **one real difference** on purpose, for instance `deletedUserPersonalSiteRetentionPeriodInDays` set to a value different from the tenant's (the audit shows drift; the tenant is not changed).
5. **Dry run, off camera.** `./Invoke-OneDriveAudit.ps1 -BaselineFile ./onedrive-baseline.lab.json`. Check:
   - **Concealed.** A new tenant conceals names (Learn: the default since 1 Sept 2021): the run prints the warning and stops. Keep that for screen 2's first beat, then clear **Conceal user, group, and site names in all reports**
     (Microsoft 365 admin center > Settings > Org settings > Services > Reports; it takes a few minutes), and run again. *If the tenant is not concealed, skip the beat.*
   - The report's `Report Refresh Date` says how fresh the data is: if the lab users are missing, record another day. **Not verified:** the lag.
   - **Not verified:** the real `Is Deleted` text and whether `Storage Allocated (Byte)` equals the quota set in step 3. If `NearFull` does not fire for `taylor.demo`, do not claim it in the narration.
6. **The VM.** Start `CON-W11-01`, sign in as `alex.demo`. Copy the whole `src` folder to `C:\mg\src` (the module is next to the scripts). Note the Entra tenant id off camera (Entra admin center > Overview): it is pasted into the command on screen 3, so **mask it**.
   Check that OneDrive is **not** yet signed in and the known folders are **not** redirected (File Explorer > Properties of Documents: Location is `C:\Users\alex.demo\Documents`), and that `HKLM:\SOFTWARE\Policies\Microsoft\OneDrive` does not exist yet
   (`Test-Path` gives `False`): the first run must be a clean one. If it exists, export it first (`reg export`) and say so on camera.

## Screens to capture (match `script.yaml` screen scenes)

### 1. `screens/settings.jpg` — "What the tenant says about OneDrive" (needs tenant)
Microsoft 365 admin center / SharePoint admin center > **Settings > OneDrive** (storage limit, retention for deleted users, sync). Show the retention days and the default storage. Mask the tenant name.
Rewrite the narration to the real values.

### 2. `screens/audit.jpg` — "The audit, on the real tenant" (needs tenant, read-only)
```powershell
./Invoke-OneDriveAudit.ps1 -BaselineFile ./onedrive-baseline.lab.json                        # while concealed: the warning
# clear the Reports setting, wait a few minutes
./Invoke-OneDriveAudit.ps1 -BaselineFile ./onedrive-baseline.lab.json -OutFile ./report.lab.md
```
Capture the warning, then the findings (settings drift first, then the account rows), the finding count and the storage table. Rewrite the narration to the real rows. Mask UPNs beyond the lab aliases and the domain.
`report.lab.md` contains tenant data: show it only cropped.

### 3. `screens/apply.jpg` — "Plan, then write" (needs VM, **writes the registry**)
On the VM, elevated PowerShell 7, in `C:\mg\src`:
1. `./Set-OneDriveSyncPolicy.ps1 -TenantId <tenant guid> -RollbackFile .\onedrive-policy.rollback.json -WhatIf` : a table of values with status `WhatIf`; show that `Test-Path HKLM:\SOFTWARE\Policies\Microsoft\OneDrive` is still `False` and that no rollback file exists.
2. Same command without `-WhatIf`: status `Written`; show `onedrive-policy.rollback.json` (it records that the values did not exist before).
3. `./Set-OneDriveSyncPolicy.ps1 -TenantId <tenant guid> -Check` : every row `Compliant`. Open `regedit` once on the policies key to show the real values (mask the tenant id).
Rewrite the narration to what really happened. **Not verified:** that the real provider accepts `New-ItemProperty -PropertyType -Force` the way the mocks assume: if anything fails, record the error: it is a finding for the code.

### 4. `screens/result.jpg` — "What the user sees" (needs VM and tenant)
Start (or restart) OneDrive on the VM; with `SilentAccountConfig` it signs in `alex.demo` without a prompt, Files On-Demand shows the cloud and check icons, and silent Known Folder Move redirects Desktop, Documents and Pictures.
Show File Explorer (Documents > Properties > Location now under `OneDrive - ...`) and the user's OneDrive in the browser with the three folders. **Not verified:** how long this takes (the policy is read at sync-app start; Learn's *Redirect known folders* page describes the behaviour).
If it takes minutes, say so on camera and cut to the result; do not stage it. Then run `-Check` again.
If KFM does not start, read the sync app's own messages and report what is shown; do not edit the narration to hide it.

## Masking checklist
- Tenant id (screen 3 command, regedit), tenant name and domain, UPNs beyond the lab aliases, the OneDrive URL (it contains the tenant name), VM user profile path if it shows the tenant name.
- `onedrive-baseline.lab.json`, `report.lab.md` and `onedrive-policy.rollback.json` (it holds the tenant id) contain tenant data: show only cropped, never commit them.

## Tear-down (before the trial ends on 20 Dec 2026)
1. On the VM, elevated: `./Set-OneDriveSyncPolicy.ps1 -Restore .\onedrive-policy.rollback.json` : the values that did not exist are removed; `-Check` shows `Missing`. If the policy key is left empty, delete it by hand.
2. **Known folders:** the policy does not move them back. In OneDrive settings > Sync and backup > Manage backup, stop backing up Desktop, Documents and Pictures (choose to keep the files on this PC if asked), or revert the VM to its pre-demo checkpoint.
   Sign out of OneDrive on the VM, or revert the checkpoint. Delete `C:\mg`.
3. Admin center: put `taylor.demo`'s storage maximum back to the value written in setup 3. Delete the files uploaded for the demo.
4. Microsoft 365 admin center > Settings > Org settings > Services > Reports: tick **Conceal user, group, and site names in all reports** again.
5. Delete `casey.former` permanently (Deleted users) if it was created; delete `onedrive-baseline.lab.json`, `report.lab.md` and `onedrive-policy.rollback.json` from the recording machines. Optionally remove the consent for
   `Microsoft Graph Command Line Tools` (Entra admin center > Enterprise applications), `Disconnect-MgGraph`, and shut the VM down.
