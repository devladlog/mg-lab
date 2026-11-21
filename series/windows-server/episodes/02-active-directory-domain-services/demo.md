# Demo shot list — DEVLADLOG Windows Server #2: Active Directory Domain Services

Everything in `src/`, `setup/` and `tests/` already ran in the build container: 42 Pester tests (AD cmdlets mocked),
the offline report from the fictional snapshot (`sample/report.md`) and a parse/5.1-syntax check of
`New-LabForest.ps1`. **Nothing has run against a real domain controller yet** — every screen below needs the lab.
Rewrite the narration of each screen scene to what is actually on screen.

## Prerequisites

| Item | Notes | Cost |
|---|---|---|
| Hyper-V lab on an **isolated VLAN** (same as episode 1) | Lab AD/DNS/DHCP must never touch the home network | none |
| CON-DC01: Windows Server 2025 **evaluation** VM, Server Core, **static IP**, DNS pointing to itself after promotion | 2 vCPU / 4 GB, 60 GB disk | none |
| CON-FS01: Windows Server 2025 VM (Desktop Experience) to join the domain | used for the sign-in gotcha | none |
| PowerShell 7.2+ on CON-DC01 for the AdLab module (`winget` isn't on Server Core: use the MSI from the PowerShell GitHub releases) | `New-LabForest.ps1` itself runs in Windows PowerShell 5.1 | none |
| This episode folder copied to `C:\lab\ep02` on CON-DC01 | | none |

## Setup and screens (in recording order)

### 1. `screens/promote.jpg` — "Check first, then promote" (**needs lab**)
On CON-DC01, elevated `powershell.exe`:
```powershell
cd C:\lab\ep02
.\setup\New-LabForest.ps1 -DomainName lab.contoso.com -NetbiosName CONTOSOLAB -WhatIf
```
Capture: `ForestMode values accepted here: ...` and the `Test-ADDSForestInstallation` output (`Status : Success`).
- **Verify and note in README:** is `Win2025` in the accepted list? If not, re-run with `-FunctionalLevel` set to the
  highest listed value and change the narration (the scene is about *checking*, so either result works).
- Note: the `-WhatIf` run installs nothing, so if the AD DS role isn't installed yet the script stops after printing
  that. For the shot, install the role first: `Install-WindowsFeature AD-Domain-Services -IncludeManagementTools`.

Then the real run (B-roll of the restart is enough):
```powershell
.\setup\New-LabForest.ps1 -DomainName lab.contoso.com -NetbiosName CONTOSOLAB
```
Join CON-FS01 to `lab.contoso.com` afterwards (`Add-Computer -DomainName lab.contoso.com -Restart`).

### 2. `screens/provision.jpg` — "Run it twice" (**needs lab**)
After the restart, in `pwsh` on CON-DC01:
```powershell
cd C:\lab\ep02
Import-Module .\src\AdLab\AdLab.psd1
$pw = Read-Host -AsSecureString 'Initial password'          # lab-only password, never shown on screen
$p = @{ CsvPath = '.\src\users.csv'; DomainDn = 'DC=lab,DC=contoso,DC=com'; UpnSuffix = 'lab.contoso.com'; InitialPassword = $pw }
Invoke-AdLabProvisioning @p | Group-Object Action, Type | Format-Table Count, Name     # Created OU 9, Group 5, User 8
Invoke-AdLabProvisioning @p | Group-Object Action, Type | Format-Table Count, Name     # Exists 22
```
Capture both tables in one frame. Optional: `dsa.msc` from an RSAT machine showing the OU tree (B-roll).
- Verify: the Import-Module of `ActiveDirectory` works in PowerShell 7 on the DC (it's loaded by `Assert-AdLabModule`).

### 3. Prepare the report data (before shot 3, not recorded)
```powershell
# a privileged account for the Tier 0 finding, and an orphaned adminCount
New-ADUser -Name 'adm-alex' -SamAccountName adm-alex -Path 'OU=IT,OU=Users,OU=Contoso,DC=lab,DC=contoso,DC=com' -AccountPassword $pw -Enabled $true
Add-ADGroupMember -Identity 'Domain Admins' -Members adm-alex
Add-ADGroupMember -Identity 'Domain Admins' -Members iferreira
# wait for SDProp (runs every 60 minutes by default on the PDC emulator), check adminCount=1 on iferreira, then:
Remove-ADGroupMember -Identity 'Domain Admins' -Members iferreira -Confirm:$false
```
(`Domain Admins` by name is fine in an English lab; the module itself uses SIDs.)

### 4. `screens/report.jpg` — "The lab domain, judged" (**needs lab**)
```powershell
.\src\Invoke-AdHygieneReport.ps1 -SnapshotFile .\lab-snapshot.json -OutFile .\ad-report.md
```
Expect (verify): `RecycleBin` Medium, `PasswordPolicy` Medium if the default minimum length is below 14,
`LockoutPolicy` if the threshold is 0, `PrivilegedGroup` for Domain Admins/Administrators (adm-alex + Administrator
is fine with `MaxTierZeroMembers = 1`; add a second admin if you want the row), `OrphanedAdminCount` for iferreira,
`NeverUsed` won't appear (accounts are new), `KrbtgtPassword` won't appear (new forest).
- Note in README the exact `DomainMode`/`ForestMode` strings the snapshot shows (e.g. whether `FunctionalLevel` Info
  rows appear at the 2025 level — they shouldn't if the string contains `2025`).

### 5. `screens/lastlogon.jpg` — "Gotcha: lastLogonTimestamp isn't a stopwatch" (**needs lab**)
1. Sign in to CON-FS01 as `CONTOSO\jgoncalves` (first sign-in forces the password change), sign out.
2. A few minutes later, sign in again.
3. On CON-DC01:
```powershell
Get-ADUser jgoncalves -Properties lastLogon, lastLogonTimestamp | Select-Object Name,
    @{ n = 'lastLogon (this DC)';       e = { [datetime]::FromFileTimeUtc($_.lastLogon) } },
    @{ n = 'lastLogonTimestamp (repl)'; e = { [datetime]::FromFileTimeUtc($_.lastLogonTimestamp) } } | Format-List
```
Expected: `lastLogon` = second sign-in, `lastLogonTimestamp` = first sign-in. If both match (e.g. S4U or other
activity updated it), record what you see and change the narration; the Learn reference stays valid.

### Optional B-roll: enable the Recycle Bin
```powershell
Enable-ADOptionalFeature -Identity 'Recycle Bin Feature' -Scope ForestOrConfigurationSet -Target lab.contoso.com
```
Show the irreversible-change confirmation, then re-run the report: the `RecycleBin` row is gone.

## Masking
- Everything is fictional (`lab.contoso.com`, `CONTOSOLAB`, CSV names). Keep it that way.
- Never type passwords on screen: always `Read-Host -AsSecureString`.
- Hide the Hyper-V host name, real IP ranges if they identify the home network, and the Windows user profile path.

## Tear-down
The lab domain is reused in episode 3 (Group Policy): keep CON-DC01 and the users.
If you're done with the series: delete the VMs and their VHDX files; if you used Azure, delete the resource group
and check the budget alert. Remove `lab-snapshot.json` and `ad-report.md` from the DC.
