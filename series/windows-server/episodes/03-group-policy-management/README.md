# DEVLADLOG Windows Server #3 — Group Policy Management: GPOs from a file, proof, and an audit

**GpoLab** is a PowerShell module that treats Group Policy as code for the `lab.contoso.com` domain from episode 2:

1. **`gpo-definitions.json`** describes the GPOs: registry-based settings (`HKLM` = Computer, `HKCU` = User), which
   half is disabled, links (target OU, order, enforced) and security filtering. `Read-GpoLabDefinition` refuses
   mistakes before anything touches the domain: a setting in a disabled half, a link outside the domain, security
   filtering with no computer Read group.
2. **`Invoke-GpoLabDeployment`** makes the domain match the file: `New-GPO`, `GpoStatus`, `Set-GPRegistryValue`,
   `New-GPLink`/`Set-GPLink`, `Set-GPPermission`. It reads before it writes, so a second run reports `NoChange` for
   every row, and every change goes through `-WhatIf`/`-Confirm`.
3. **`Export-GpoLabSnapshot` + `Test-GpoLabHygiene`** export every GPO (status, AD and SYSVOL versions, whether each
   half has settings according to `Get-GPOReport -ReportType Xml`, permissions) and every link in the domain to JSON,
   then check it: settings in a disabled half, AD/SYSVOL version mismatch, user settings computers can't read
   (MS16-072), unlinked / empty / all-links-disabled GPOs, linked GPOs nobody can apply, enforced links, blocked
   inheritance.
4. **`Backup-GpoLab`** runs `Backup-GPO -All` into a timestamped folder and writes `links.json` next to it, because
   importing a backup restores settings, not links.

The two lab GPOs: **CON-Servers-Baseline** (Servers OU, computer half only: PowerShell script block logging and
Network Level Authentication for RDP) and **CON-Finance-ScreenLock** (Users OU, user half only, filtered to
`GG-Dept-Finance`: password-protected screen saver, 900-second timeout).

| Path | What it is |
|---|---|
| [`src/GpoLab/GpoLab.psm1`](src/GpoLab/GpoLab.psm1) | The module (Windows PowerShell 5.1 and PowerShell 7) |
| [`src/gpo-definitions.json`](src/gpo-definitions.json) | The two lab GPOs, with the ADMX policy name of every value |
| [`src/Invoke-GpoHygieneReport.ps1`](src/Invoke-GpoHygieneReport.ps1) | Entry script: live (exports a snapshot) or `-FromSnapshot`; `-OutFile`, `-FailOnHigh` (exit 1) |
| [`tests/GpoLab.Tests.ps1`](tests/GpoLab.Tests.ps1) | 27 Pester tests; GroupPolicy and ActiveDirectory cmdlets are stubbed and mocked |
| [`tests/fixtures/gpo-snapshot.json`](tests/fixtures/gpo-snapshot.json) | Fictional snapshot of `lab.contoso.com`: 9 GPOs, one example of each problem (zero GUIDs) |
| [`tests/fixtures/gporeport-baseline.xml`](tests/fixtures/gporeport-baseline.xml) | A `Get-GPOReport -ReportType Xml` document in the documented shape, for the "has settings" test |
| [`sample/report.md`](sample/report.md) | The report generated from the fixture |

## Run the tests (any OS, no domain)

```bash
cd series/windows-server/episodes/03-group-policy-management
pwsh -NoProfile -Command 'Invoke-Pester ./tests'          # Tests Passed: 27, Failed: 0   (PowerShell 7.6.0, Pester 6.2.0)

cd src
pwsh -NoProfile -Command './Invoke-GpoHygieneReport.ps1 -FromSnapshot ../tests/fixtures/gpo-snapshot.json -OutFile ../sample/report.md'
# lab.contoso.com: 9 GPO(s), 9 finding(s), 2 high.
```

## Run it in the lab

On a domain member with GPMC and the AD module (`Install-WindowsFeature GPMC, RSAT-AD-PowerShell`), as a lab domain
admin, in **Windows PowerShell 5.1** (`powershell.exe`), where the GroupPolicy module loads natively:

```powershell
cd C:\lab\ep03\src
Import-Module .\GpoLab\GpoLab.psd1
Invoke-GpoLabDeployment -DefinitionPath .\gpo-definitions.json -WhatIf | Format-Table Gpo, Action, Target, Result
Invoke-GpoLabDeployment -DefinitionPath .\gpo-definitions.json        | Format-Table Gpo, Action, Target, Result

.\Invoke-GpoHygieneReport.ps1 -SnapshotFile .\gpo-snapshot.json -OutFile .\gpo-report.md
Backup-GpoLab -Path C:\lab\gpo-backups
```

See [demo.md](demo.md) for the full recording plan (prerequisites, the four screens, tear-down).

## Design choices

- **The file is the source of truth.** The GPO comment says "edit gpo-definitions.json, not GPMC", and a re-run puts
  back anything changed by hand (a disabled link, an edited value, a removed permission): the drift test proves it.
- **Disable the half you don't use, and validate it.** A computer-only GPO gets `UserSettingsDisabled`. The validator
  refuses a setting in a disabled half at deploy time; the hygiene check finds the ones created by hand.
- **Match links by GPO ID, not name.** `Get-GPInheritance -Target <OU>` lists the links on an OU; we compare `GpoId`.
- **Security filtering never removes Read for computers.** Groups in `SecurityFiltering` get `GpoApply`; the
  `ComputerRead` trustee (Authenticated Users) is replaced with `GpoRead` (`-Replace`), which removes Apply and keeps
  Read, the first option Learn lists for MS16-072.
- **Snapshot is the contract.** Export once in the domain, judge anywhere, re-check old snapshots later.
- **Windows PowerShell 5.1 first.** The module runs where the GroupPolicy module lives without extra installs; a
  Pester test parses the module and fails on PowerShell 7-only syntax (`?:`, `??`, `?.`, `&&`).

## What we learned / gotchas

- **MS16-072: user policy is read with the computer's account.** Since the June 2016 update, Windows retrieves user
  Group Policy in the computer's security context, so computers need Read on every GPO that applies to users.
  Removing Authenticated Users from Security Filtering removes Read *and* Apply; give Read back to Authenticated Users
  or Domain Computers. The report flags it as `UserGpoNoComputerRead` (High). Domain controllers aren't affected
  (Enterprise Domain Controllers has Read on all GPOs by default).
- **A GPO lives in two places.** The Group Policy container is in AD, the template in SYSVOL, replicated by AD
  replication and DFSR/FRS respectively. `Get-GPO` shows both version numbers per half; the report flags a mismatch.
- **`Invoke-GPUpdate` needs firewall rules on the target**: Remote Scheduled Tasks Management (RPC and RPC-EPMAP) and
  WMI-In, because it schedules gpupdate as a task. For the demo we use `Invoke-Command` (WinRM is on by default).
- **Script block logging starts with new sessions.** Learn: once enabled, *new* PowerShell sessions log event 4104
  to Microsoft-Windows-PowerShell/Operational. Check with a fresh session after `gpupdate`.
- **Link order: lower number wins.** GPOs with a higher link order are processed first, so the link with order 1 on
  an OU is processed last and wins a conflict. Enforced links override lower ones and ignore blocked inheritance:
  Learn says to use them sparingly, so the report lists every one.
- **Removing a GPO removes its links in its own domain** (unless `-KeepLinks`); `Import-GPO` into a new GPO does not
  recreate links: hence `links.json` next to every backup.
- **PowerShell 7.6.0 bit us in the tests:** `@($list)` on a `System.Collections.Generic.List[object]` that holds
  `PSCustomObject`s threw "Argument types do not match" (a list of integers was fine). The module uses
  `System.Collections.ArrayList` instead; reproduce with
  `$l=[Collections.Generic.List[object]]::new(); $l.Add([pscustomobject]@{a=1}); @($l)`.
- **Pester can only mock commands that exist**, so the tests create stubs for the GPMC/RSAT cmdlets that declare every
  parameter the module passes (otherwise `-ParameterFilter` sees nothing), same lesson as episode 2.

> **Not run yet (needs the lab, see [demo.md](demo.md)):** the real deployment, export and backup against
> `lab.contoso.com`. Only unit-tested with mocks. To confirm in the lab: that setting `GpoStatus` on the object
> returned by `Get-GPO` persists; the exact property names `Computer.DSVersion` / `Computer.SysvolVersion` on the
> object; that the screen saver values (written as `String`) show up in GPMC under Administrative Templates and not
> under Extra Registry Settings; what `gpresult` prints in the MS16-072 case.

## References

- [Group Policy overview](https://learn.microsoft.com/windows-server/identity/ad-ds/manage/group-policy/group-policy-overview) (GPC in AD, GPT in SYSVOL, replication) and [Group Policy scope](https://learn.microsoft.com/windows-server/identity/ad-ds/manage/group-policy/group-policy-scope) (security filtering needs Read and Apply)
- [Can't apply user Group Policy settings if computer objects don't have GPO Read permissions](https://learn.microsoft.com/troubleshoot/windows-server/group-policy/cannot-apply-user-gpo-when-computer-objects-dont-have-read-permissions) and [MS16-072](https://learn.microsoft.com/security-updates/securitybulletins/2016/ms16-072)
- [Set-GPRegistryValue](https://learn.microsoft.com/powershell/module/grouppolicy/set-gpregistryvalue), [Get-GPRegistryValue](https://learn.microsoft.com/powershell/module/grouppolicy/get-gpregistryvalue), [Get-GPO](https://learn.microsoft.com/powershell/module/grouppolicy/get-gpo)
- [New-GPLink](https://learn.microsoft.com/powershell/module/grouppolicy/new-gplink) (link order, enforced "use sparingly"), [Get-GPInheritance](https://learn.microsoft.com/powershell/module/grouppolicy/get-gpinheritance)
- [Set-GPPermission](https://learn.microsoft.com/powershell/module/grouppolicy/set-gppermission) (`-Replace`), [Get-GPPermission](https://learn.microsoft.com/powershell/module/grouppolicy/get-gppermission)
- [Invoke-GPUpdate](https://learn.microsoft.com/powershell/module/grouppolicy/invoke-gpupdate) (firewall rules), [Remove-GPO](https://learn.microsoft.com/powershell/module/grouppolicy/remove-gpo) (links removed by default), [Backup-GPO](https://learn.microsoft.com/powershell/module/grouppolicy/backup-gpo), [Import-GPO](https://learn.microsoft.com/powershell/module/grouppolicy/import-gpo)
- [Restoring GPO backups: links missing after import](https://learn.microsoft.com/entra/identity/domain-services/group-policy) (common restoration pitfalls table)
- Settings: [Policy CSP - WindowsPowerShell (EnableScriptBlockLogging)](https://learn.microsoft.com/windows/client-management/mdm/policy-csp-windowspowershell#turnonpowershellscriptblocklogging), [about_Logging (event 4104)](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_logging?view=powershell-5.1), [ADMX_TerminalServer (UserAuthentication)](https://learn.microsoft.com/windows/client-management/mdm/policy-csp-admx-terminalserver#ts_user_authentication_policy), [ADMX_ControlPanelDisplay (ScreenSaverIsSecure, screen saver timeout)](https://learn.microsoft.com/windows/client-management/mdm/policy-csp-admx-controlpaneldisplay)
- Blog: [Group Policy Management — Complete Guide](https://www.devladlog.com/articles/windows-server/2025-08-29-group-policy-management-complete-guide-2025/)
