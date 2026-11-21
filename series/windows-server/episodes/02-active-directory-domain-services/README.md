# DEVLADLOG Windows Server #2 — Active Directory Domain Services: new forest, CSV users, hygiene report

Three pieces, all PowerShell:

1. **`setup/New-LabForest.ps1`** promotes a Windows Server 2025 VM to the first DC of `lab.contoso.com`: installs the
   AD DS role, reads which functional levels *this* server accepts, runs `Test-ADDSForestInstallation`, then
   `Install-ADDSForest` (DNS is installed with it by default). Supports `-WhatIf`.
2. **`Invoke-AdLabProvisioning`** creates OUs (protected from accidental deletion), one global security group per
   department and the users from [`src/users.csv`](src/users.csv). People are matched on **EmployeeID**, so a second
   run creates nothing and a surname change never creates a duplicate. Logon names are ASCII, ≤ 20 characters,
   unique. Supports `-WhatIf`.
3. **`Export-AdLabSnapshot` + `Test-AdLabHygiene`** export the domain to JSON and check it: stale users and computers
   (privileged ones are High), never-used accounts, `PasswordNeverExpires`, `PASSWD_NOTREQD`, SPN user accounts,
   orphaned `adminCount`, Tier 0 group size, Guest, krbtgt password age, Recycle Bin, password/lockout policy,
   functional level.

| Path | What it is |
|---|---|
| [`setup/New-LabForest.ps1`](setup/New-LabForest.ps1) | Forest promotion with prerequisite checks (run on the future DC in Windows PowerShell 5.1, needs lab) |
| [`src/AdLab/AdLab.psm1`](src/AdLab/AdLab.psm1) | The module: naming, OU/user plans, provisioning, snapshot export, hygiene checks, markdown report |
| [`src/Invoke-AdHygieneReport.ps1`](src/Invoke-AdHygieneReport.ps1) | Entry script: live (exports a snapshot) or `-FromSnapshot`; `-OutFile`, `-FailOnHigh` |
| [`src/users.csv`](src/users.csv) | 8 fictional users (accents, a collision, a 24-character name on purpose) |
| [`src/policy.json`](src/policy.json) | Thresholds: stale after 90 days, krbtgt 180 days, min password length 14, Tier 0 ≤ 1 extra member |
| [`tests/AdLab.Tests.ps1`](tests/AdLab.Tests.ps1) | 42 Pester tests; AD cmdlets are stubbed and mocked |
| [`tests/fixtures/lab-snapshot.json`](tests/fixtures/lab-snapshot.json) | Fictional snapshot of `lab.contoso.com` with one example of each problem |
| [`sample/report.md`](sample/report.md) | The report generated from the fixture |

## Run the tests (any OS, no domain controller)

```bash
cd series/windows-server/episodes/02-active-directory-domain-services
pwsh -NoProfile -Command 'Invoke-Pester ./tests'          # Tests Passed: 42, Failed: 0   (PowerShell 7.6, Pester 6.2)

cd src
pwsh -NoProfile -Command './Invoke-AdHygieneReport.ps1 -FromSnapshot ../tests/fixtures/lab-snapshot.json -Now 2026-11-20T09:00:00Z -OutFile ../sample/report.md'
# lab.contoso.com: 16 finding(s), 3 high.
```

## Run it in the lab

```powershell
# On the future DC (Windows Server 2025, static IP, isolated network), elevated Windows PowerShell 5.1 (powershell.exe):
./setup/New-LabForest.ps1 -DomainName lab.contoso.com -NetbiosName CONTOSOLAB -WhatIf
./setup/New-LabForest.ps1 -DomainName lab.contoso.com -NetbiosName CONTOSOLAB       # restarts the server

# After the restart, on the DC (PowerShell 7.2+; the ActiveDirectory module comes with the role):
Import-Module ./src/AdLab/AdLab.psd1
$pw = Read-Host -AsSecureString 'Initial password for the lab users'
Invoke-AdLabProvisioning -CsvPath ./src/users.csv -DomainDn 'DC=lab,DC=contoso,DC=com' -UpnSuffix lab.contoso.com -InitialPassword $pw -WhatIf
Invoke-AdLabProvisioning -CsvPath ./src/users.csv -DomainDn 'DC=lab,DC=contoso,DC=com' -UpnSuffix lab.contoso.com -InitialPassword $pw

./src/Invoke-AdHygieneReport.ps1 -SnapshotFile ./lab-snapshot.json -OutFile ./ad-report.md
```

## Design choices

- **Ask the server, not the docs.** The script lists the `ForestMode` values the local `Install-ADDSForest` accepts
  (`GetEnumNames()`) and stops with that list if the requested level isn't there.
- **`Test-ADDSForestInstallation` before `Install-ADDSForest`.** Learn: it *tests* whether the changes are possible,
  while `-WhatIf` only summarizes them.
- **Stable key = EmployeeID.** Names change; employee IDs don't. Every existing `sAMAccountName` in the domain counts
  as taken, not only the CSV's.
- **Groups by SID, members recursively.** Protected groups are found by well-known SID / RID (works on non-English
  DCs), and `Get-ADGroupMember -Recursive` counts nested members.
- **The snapshot is the contract.** Export once on the DC, judge anywhere; old snapshots can be re-checked with `-Now`.

## What we learned / gotchas

- **`lastLogonTimestamp` is not a stopwatch.** It replicates, but it's only updated when the stored value is older
  than `msDS-LogonTimeSyncInterval` — in practice 9 to 14 days. `StaleDays = 90` is a threshold with a two-week
  margin, and every stale finding says so. The non-replicated `lastLogon` is exact but per DC.
- **Functional level values disagree on Learn.** The AD DS install guide uses `-ForestMode Win2025`; the
  `Install-ADDSForest` reference lists accepted values only up to `WinThreshold`. Hence the `GetEnumNames()` check.
  New forests need Windows Server 2016 level or later; the 2025 level is required for the 32k database page feature.
- **`adminCount` outlives group membership.** Removing a user from a protected group leaves `adminCount = 1` and
  inheritance disabled; SDProp doesn't undo it. The report flags these as `OrphanedAdminCount`.
- **Recycle Bin: enable it early.** Enabling is irreversible and only objects deleted *afterwards* can be restored
  from it.
- **Pester can't mock a command that doesn't exist, and copies the stub's parameters.** Our first stubs used
  `ValueFromRemainingArguments`, so every `-ParameterFilter` saw nothing and the call-count assertions failed. The stubs
  now declare each parameter the module passes.
- **sAMAccountName is 20 characters or fewer.** `Bartholomew Featherstonehaugh-Smythe` → `bfeatherstonehaughsm`;
  with a collision the number replaces the last character(s) instead of making it longer.

> Not run yet (needs the lab, see [demo.md](demo.md)): `New-LabForest.ps1`, the real `Invoke-AdLabProvisioning` and
> `Export-AdLabSnapshot` against a DC. Only parsed and unit-tested with mocks here. In particular, confirm that
> `Win2025` is in the accepted list and the exact `DomainMode` string `Get-ADDomain` returns at that level.

## References

- [Install Active Directory Domain Services (PowerShell)](https://learn.microsoft.com/windows-server/identity/ad-ds/deploy/install-active-directory-domain-services--level-100-)
- [Install-ADDSForest](https://learn.microsoft.com/powershell/module/addsdeployment/install-addsforest) and [Test-ADDSForestInstallation](https://learn.microsoft.com/powershell/module/addsdeployment/test-addsforestinstallation)
- [AD DS functional levels](https://learn.microsoft.com/windows-server/identity/ad-ds/active-directory-functional-levels) and [What's new in Windows Server 2025](https://learn.microsoft.com/windows-server/get-started/whats-new-windows-server-2025) (2016 minimum for new forests, 32k pages)
- [SAM-Account-Name attribute](https://learn.microsoft.com/windows/win32/adschema/a-samaccountname) (20 characters or fewer)
- [Last-Logon-Timestamp attribute](https://learn.microsoft.com/windows/win32/adschema/a-lastlogontimestamp) and [9 to 14 days](https://learn.microsoft.com/troubleshoot/mem/configmgr/discovery/lastlogontimestamp-not-accurate)
- [Appendix C: Protected accounts and groups](https://learn.microsoft.com/windows-server/identity/ad-ds/plan/security-best-practices/appendix-c--protected-accounts-and-groups-in-active-directory) and [Reducing the AD attack surface](https://learn.microsoft.com/windows-server/identity/ad-ds/plan/security-best-practices/reducing-the-active-directory-attack-surface) (adminCount stays 1)
- [Appendix E: Enterprise Admins](https://learn.microsoft.com/windows-server/identity/ad-ds/plan/security-best-practices/appendix-e--securing-enterprise-admins-groups-in-active-directory), [F: Domain Admins](https://learn.microsoft.com/windows-server/identity/ad-ds/plan/security-best-practices/appendix-f--securing-domain-admins-groups-in-active-directory), [G: Administrators](https://learn.microsoft.com/windows-server/identity/ad-ds/plan/security-best-practices/appendix-g--securing-administrators-groups-in-active-directory)
- [Security identifiers (well-known RIDs)](https://learn.microsoft.com/windows-server/identity/ad-ds/manage/understand-security-identifiers) and [Well-known SIDs](https://learn.microsoft.com/windows/win32/secauthz/well-known-sids)
- [Enable and use Active Directory Recycle Bin](https://learn.microsoft.com/windows-server/identity/ad-ds/get-started/adac/active-directory-recycle-bin) (irreversible) and [Enable-ADOptionalFeature](https://learn.microsoft.com/powershell/module/activedirectory/enable-adoptionalfeature)
- [Reset the krbtgt password](https://learn.microsoft.com/windows-server/identity/ad-ds/manage/forest-recovery-guide/ad-forest-recovery-reset-the-krbtgt-password) (twice, 10 hours apart) and [Defender for Identity: krbtgt older than 180 days](https://learn.microsoft.com/defender-for-identity/security-posture-assessments/accounts)
- Blog: [Active Directory Domain Services — Complete Guide](https://www.devladlog.com/articles/windows-server/2025-08-26-active-directory-domain-services-complete-guide-2025/)
