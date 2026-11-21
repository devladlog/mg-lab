# DEVLADLOG Microsoft 365 #12 — OneDrive for Business

**Read what the tenant says about OneDrive, find the OneDrives that need attention, and set up the sync app on a PC (silent sign-in, Files On-Demand, silent Known Folder Move) with a way back.**
Two halves that do not touch each other:

1. **Tenant side, read-only** — [`src/Invoke-OneDriveAudit.ps1`](src/Invoke-OneDriveAudit.ps1) + the `OneDriveAdmin` module.
   - `Get-ODATenantSetting` (`GET /admin/sharepoint/settings`) and `Get-ODASettingFinding` compare the OneDrive-related properties of a baseline file ([`src/onedrive-baseline.json`](src/onedrive-baseline.json)) with the tenant.
     A name that is not an updatable property is an error. A property the tenant does not return is `Info`, never drift.
   - `Get-ODAUsageReport` (`getOneDriveUsageAccountDetail`), `Get-ODAAccountFinding` and `Get-ODAStorageSummary`: `NearFull`, `InactiveOneDrive`, `NeverUsed`, `NoActivityRecorded`,
     `CustomQuota` (only when you pass the tenant default), `DeletedRetained`. A concealed report (UPNs are hashes) stops the audit with the setting to change.
2. **PC side, writes the registry** — [`src/Set-OneDriveSyncPolicy.ps1`](src/Set-OneDriveSyncPolicy.ps1). Windows only; it needs an elevated PowerShell to write, and the tenant id is a parameter (it never talks to Microsoft 365).
   - `Get-ODASyncPolicyPlan`: the values under `HKLM\SOFTWARE\Policies\Microsoft\OneDrive`: `SilentAccountConfig`=1, `FilesOnDemandEnabled`=1, `KFMSilentOptIn`=tenant id, `KFMSilentOptInWithNotification`=0 (1 with `-Notify`),
     `KFMSilentOptInDesktop/Documents/Pictures`=1 (pick folders with `-KnownFolders`), and `KFMBlockOptOut`=1 only with `-BlockOptOut`.
   - `Get-ODASyncPolicyState` (`-Check`: `Compliant` / `Different` / `Missing`), `Set-ODASyncPolicy` (`-WhatIf`; **the previous state goes to a rollback file first** and a file that exists is never overwritten),
     `Restore-ODASyncPolicy` (`-Restore`: puts back old values and removes values that did not exist; skips a value someone changed after us).

Same fictional tenant as episodes 1–11 (`contoso`); lab users `labadmin`, `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo`. The PC is the lab VM `CON-W11-01` from episode 7. The data in the tests
never appears in the demo.

| Path | What it is |
|---|---|
| [`src/onedrive-baseline.json`](src/onedrive-baseline.json) | Baseline (example values: yours to decide) and account thresholds (180 days, 90 percent) |
| [`src/OneDriveAdmin/OneDriveAdmin.psm1`](src/OneDriveAdmin/OneDriveAdmin.psm1) · [`.psd1`](src/OneDriveAdmin/OneDriveAdmin.psd1) | The module: Graph collection, pure analysis, sync-policy plan/state/write/restore, markdown report |
| [`src/Invoke-OneDriveAudit.ps1`](src/Invoke-OneDriveAudit.ps1) | Tenant audit runner (live, or `-SettingsFile` + `-UsageFile` offline, `-AsOf`, `-Period`, `-OutFile`) |
| [`src/Set-OneDriveSyncPolicy.ps1`](src/Set-OneDriveSyncPolicy.ps1) | PC runner: apply (default, `-RollbackFile` required), `-Check`, `-Restore`, `-WhatIf` |
| [`tests/OneDriveAdmin.Tests.ps1`](tests/OneDriveAdmin.Tests.ps1) | 47 Pester tests (fake Graph tenant; fake registry through mocked provider cmdlets; one test checks our Graph calls against the real Microsoft.Graph.Authentication module) |
| [`tests/fixtures/`](tests/fixtures) | Fictional settings, usage report (and a concealed one), test baseline |
| [`sample/onedrive-report.md`](sample/onedrive-report.md) | Report for the fictional data, generated offline |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and shot list (uses the existing lab VM; no cost) |

## Run the tests

```bash
cd series/microsoft-365/episodes/12-onedrive-for-business
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Without the real Graph module:  Tests Passed: 46, Failed: 0, Skipped: 1
# With Microsoft.Graph.Authentication on PSModulePath (adds the "real module parameters" test):
#                                 Tests Passed: 47, Failed: 0, Skipped: 0
```

Produced in this repo's container (PowerShell 7.6 on Linux, Pester 6.2.0). PSScriptAnalyzer (Warning and Error) reports 0 issues on `src/`.
**The registry code was never run against a real registry:** the tests replace `Test-Path`, `New-Item`, `Get-ItemProperty`, `New-ItemProperty` and `Remove-ItemProperty` with a fake registry, so they prove the logic
(plan, rollback, restore, skip-if-changed, `-WhatIf` writes nothing), not the Windows provider. The first real run is in [demo.md](demo.md).

## Run it

```powershell
cd src
# Offline (no tenant): analyse the fictional data
./Invoke-OneDriveAudit.ps1 -BaselineFile ../tests/fixtures/baseline.test.json -SettingsFile ../tests/fixtures/settings.json `
    -UsageFile ../tests/fixtures/onedriveusage.csv -AsOf 2026-11-21T12:00:00Z -OutFile ../sample/onedrive-report.md

# Needs tenant (see demo.md): copy onedrive-baseline.json to onedrive-baseline.lab.json first
./Invoke-OneDriveAudit.ps1 -BaselineFile ./onedrive-baseline.lab.json -OutFile ./report.lab.md    # SharePointTenantSettings.Read.All, Reports.Read.All, ReportSettings.Read.All

# Needs the lab VM, elevated PowerShell on Windows (tenant id = Entra admin center > Overview)
./Set-OneDriveSyncPolicy.ps1 -TenantId <tenant guid> -RollbackFile .\onedrive-policy.rollback.json -WhatIf
./Set-OneDriveSyncPolicy.ps1 -TenantId <tenant guid> -RollbackFile .\onedrive-policy.rollback.json
./Set-OneDriveSyncPolicy.ps1 -TenantId <tenant guid> -Check
./Set-OneDriveSyncPolicy.ps1 -Restore .\onedrive-policy.rollback.json
```

## What we learned / gotchas

- **Retention starts only when the user is deleted** (Learn: *Set the OneDrive retention for deleted users*). `deletedUserPersonalSiteRetentionPeriodInDays` is how long a deleted user's OneDrive is kept and reachable
  by others; afterwards it goes to the site collection recycle bin for 93 days (Learn: *Retention and deletion*). `DeletedRetained` reports an account in that period; it is information, not an error.
- **Known Folder Move is configured per PC (or by Intune/GPO), not in the tenant.** That is why the PC half writes the registry. Learn's *Redirect and move Windows known folders to OneDrive* lists prerequisites and limits worth reading before
  a real rollout; this tool does not duplicate those checks and the exact list was not re-verified for this README.
- **`Set-ItemProperty -Type` is a dynamic parameter of the registry provider**: it does not exist on Linux, so a Pester mock of it fails there. The module uses `New-ItemProperty -PropertyType -Force`, which also works in Windows PowerShell.
  Writing under `HKLM` needs elevation: the runner checks it before touching anything (and `-WhatIf` does not need it).
- **The tenant id lives in the registry as a string** (`KFMSilentOptIn`), the toggles as DWORD. The plan lowercases the tenant id and rejects anything that is not a GUID.
- **Usage reports hide names by default since 1 September 2021** (Learn: *Microsoft 365 admin center usage reports overview*): UPNs come back as hashes. A Global Administrator clears *Conceal user, group, and site names
  in all reports*; the audit detects the hashes and stops with that instruction. It is a logged event in the Purview audit log; restore the setting afterwards.
- **The usage report has no creation date**: a OneDrive created yesterday looks like one nobody used. The rules are named `NeverUsed` / `NoActivityRecorded`, not "abandoned".
- **Unlicensed accounts** keep a OneDrive for a limited time and Learn describes how long (*Unlicensed OneDrive accounts*); the tool does not model licences.
- **What this episode does not change in the tenant:** nothing. The audit only `GET`s; settings such as the default storage or the retention period stay in the admin center (links below).
- **Not verified** (needs tenant or VM, see [demo.md](demo.md)):
  - the real `Is Deleted` text in the report (the code expects `True`/`False`) and how the report behaves with an unreadable or absent Site URL;
  - whether `Storage Allocated (Byte)` equals the default quota in MB × 1 MiB (the `CustomQuota` rule assumes it; the default comes from the tenant's `personalSiteDefaultStorageLimitInMB`, and the rule is skipped when the tenant does not return it), and the values under automatic site storage;
  - how soon silent Known Folder Move starts after the policy is written, and whether the Windows 11 image of the lab VM already ships the OneDrive sync app;
  - the real `Compliant` / `Different` output on Windows, since the registry was only mocked.
  The baseline values are examples, not Microsoft recommendations.

Not covered (to keep the episode to 6 minutes): Intune and Group Policy deployment of the same values, the Mac sync app, Files Restore and Known Folder Move troubleshooting, sharing and external access for OneDrive,
per-user storage changes, preserving or restoring a deleted user's OneDrive, sync-client versions and update rings, OneDrive for Business on mobile.

## References

- [sharepointSettings resource](https://learn.microsoft.com/graph/api/resources/sharepointsettings?view=graph-rest-1.0) · [Get settings](https://learn.microsoft.com/graph/api/sharepointsettings-get?view=graph-rest-1.0)
- [reportRoot: getOneDriveUsageAccountDetail](https://learn.microsoft.com/graph/api/reportroot-getonedriveusageaccountdetail?view=graph-rest-1.0) · [adminReportSettings](https://learn.microsoft.com/graph/api/resources/adminreportsettings?view=graph-rest-1.0)
- [Microsoft 365 admin center usage reports overview (show or conceal names)](https://learn.microsoft.com/microsoft-365/admin/activity-reports/activity-reports?view=o365-worldwide#show-user-group-or-site-details-in-usage-reports) · [OneDrive usage report](https://learn.microsoft.com/microsoft-365/admin/activity-reports/onedrive-for-business-usage-ww?view=o365-worldwide)
- [Use OneDrive policies to control sync settings (Group Policy / registry)](https://learn.microsoft.com/sharepoint/use-group-policy) · [Redirect and move Windows known folders to OneDrive](https://learn.microsoft.com/sharepoint/redirect-known-folders)
- [Set the default storage space for OneDrive](https://learn.microsoft.com/sharepoint/set-default-storage-space) · [Set the OneDrive retention for deleted users](https://learn.microsoft.com/sharepoint/set-retention) · [Retention and deletion in OneDrive](https://learn.microsoft.com/sharepoint/retention-and-deletion)
- [Restore a deleted OneDrive](https://learn.microsoft.com/sharepoint/restore-deleted-onedrive) · [Unlicensed OneDrive accounts](https://learn.microsoft.com/sharepoint/unlicensed-onedrive-accounts)
- Blog: [OneDrive for Business — Complete Guide](https://www.devladlog.com/articles/office-365/2025-02-03-onedrive-business-complete-guide-2025/)
  (note, read 21 Nov 2026: the article's code uses placeholder cmdlets and has no OneDrive-specific command. This folder's code is meant to replace it.)
