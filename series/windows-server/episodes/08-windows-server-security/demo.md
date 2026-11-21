# Demo shot list — DEVLADLOG Windows Server #8: Windows Server security

## Lab environment

Recorded on the **shared local Hyper-V lab** (`series/LAB.md`): domain `lab.contoso.com` / `CONTOSO`, network
`10.50.0.0/24`. No extra VM, no cloud, no licence, cost 0. The lab is disposable (rebuilt by `Start-MGLab.ps1`), which
is what makes the one irreversible step (the LAPS schema update) acceptable here; it would not be in a production forest.

| Role in the episode | Shared VM | OS / edition | IP | Changes made (undone in tear-down unless noted) |
|---|---|---|---|---|
| **Admin console, runs everything** | CON-SRV02 | WS 2025 Datacenter Eval, Desktop Experience | 10.50.0.22 | episode folder in `C:\lab\ep08`, RSAT: `RSAT-AD-PowerShell`, `GPMC` |
| Domain controller | CON-DC01 | WS 2025 Datacenter Eval, Server Core | 10.50.0.10 | hardened (Harden step), LAPS schema extended (**not undone**), OU `LabServers`, GPO `MGLab - Windows LAPS` |
| Members | CON-SRV01, CON-SQL01, CON-CLI01 | WS 2025 Datacenter Eval, Server Core | .21 / .30 / .41 | hardened; moved into OU `LabServers` for LAPS |

- Screens are recorded on **CON-SRV02** (VMConnect, elevated Windows PowerShell 5.1) signed in as the **lab
  Administrator** (`CONTOSO\Administrator`). Passwords are never typed on camera or written in a file.
- WinRM must work from CON-SRV02 to the other four (`Invoke-Command -ComputerName CON-SRV01 { hostname }`). Earlier
  episodes already used WinRM against these VMs; if one refuses, run `Enable-PSRemoting -Force` on it first.
- Credential Guard: the VMs are generation 2 (Secure Boot on); whether it is running depends on the host (IOMMU) and
  the VM. **Record what the check really says**; the script reports it, it does not change it.

Everything in `src/` and `tests/` already ran in the build container: 39 Pester tests and the check on three invented
fact files (`sample/`). **Needs the lab (not run yet):** the collector on the five servers, the remediation against real
servers, the rollback, and all of LAPS. Rewrite the narration of the screen scenes to the real output (counts,
findings) on the recording day.

## Prepare (before recording)

On the laptop, elevated PowerShell, repo root:

```powershell
$cred = Get-Credential 'CONTOSO\Administrator'                      # typed off camera
$s = New-PSSession -VMName CON-SRV02 -Credential $cred
Copy-Item -ToSession $s -Path .\series\windows-server\episodes\08-windows-server-security -Destination C:\lab\ep08 -Recurse -Force
Invoke-Command -Session $s { Install-WindowsFeature RSAT-AD-PowerShell, GPMC | Out-Null }
Remove-PSSession $s
# the OU for LAPS (CON-DC01), and a look at whether the LAPS schema is already there
Invoke-Command -VMName CON-DC01 -Credential $cred {
    $dn = (Get-ADDomain).DistinguishedName
    if (-not (Get-ADOrganizationalUnit -Filter "Name -eq 'LabServers'")) { New-ADOrganizationalUnit -Name LabServers -Path $dn }
    foreach ($n in 'CON-SRV01', 'CON-SQL01', 'CON-CLI01') { Get-ADComputer $n | Move-ADObject -TargetPath "OU=LabServers,$dn" }
    [bool](Get-ADObject -SearchBase (Get-ADRootDSE).schemaNamingContext -Filter "name -eq 'ms-LAPS-Password'")   # True = schema step will be skipped
}
```

On CON-SRV02 sign in as the lab Administrator, open **Windows PowerShell (Admin)**, `cd C:\lab\ep08\src`,
`function prompt { 'PS> ' }`, large font. Make sure CON-SQL01 is running (or accept that the check skips it).

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/check-before.jpg` — "Five servers, one question"
```powershell
.\Invoke-SecCheck.ps1 -FactsFile .\facts-before.json -OutFile .\check-before.md -PlanOnly
```
Capture the findings table and the last line (`N server(s), N finding(s), N high.`), then the plan table below it.
The sample on invented data says 26 findings, 0 high; the real numbers decide the narration. If the check reports
`CollectorError` rows (auditpol text, Defender, DeviceGuard), keep them: they are part of the truth.

### 2. `screens/harden.jpg` — "Read the plan, then change it"
```powershell
.\Deploy-SecLab.ps1 -Step Harden -RollbackFile .\rollback.json -WhatIf     # plan + What if lines
.\Deploy-SecLab.ps1 -Step Harden -RollbackFile .\rollback.json             # applies
.\Invoke-SecCheck.ps1 -OutFile .\check-after.md                            # re-check
```
Capture the plan (Before and Value columns), a few What if lines, and the re-check with the Medium findings gone.
Do **not** add `-IncludeRisky` on camera unless an NTLM audit was done first (see Learn: level 5 refuses NTLM). After
hardening, test that something still works across the lab (for example `Get-ChildItem \\CON-SRV01\C$` from CON-SRV02):
inbound SMB signing is now required and Kerberos clients are fine.

### 3. `screens/laps-plan.jpg` — "Windows LAPS: the one-way step"
```powershell
.\Deploy-SecLab.ps1 -Step Laps -WhatIf
```
Run on CON-SRV02 with RSAT (it needs the LAPS, ActiveDirectory and GroupPolicy modules). Capture the plan: if the schema
step is listed it is marked Irreversible; if the schema already has LAPS the plan starts at the OU permission and
the narration says so. Then the real run:
```powershell
.\Deploy-SecLab.ps1 -Step Laps -AllowSchemaUpdate
```
Learn's example shows a Yes/Yes to All prompt per attribute; the script passes `-Confirm:$false`, so none appears.

### 4. `screens/laps-result.jpg` — "A different password on every server"
```powershell
Invoke-Command -ComputerName CON-SRV01 { gpupdate.exe /target:computer /force; Invoke-LapsPolicyProcessing }
Invoke-Command -ComputerName CON-SRV01 { Get-WinEvent -LogName 'Microsoft-Windows-LAPS/Operational' -MaxEvents 5 | Format-Table TimeCreated, Id, Message -Wrap }
Get-LapsADPassword -Identity CON-SRV01                                     # Password column is a SecureString: stays masked
```
Expect event 10018 (password updated in Active Directory) and an `ExpirationTimestamp` about 30 days out. Repeat for
CON-SQL01 and show that the two expiration times exist for two different computer objects. Never use `-AsPlainText`
on camera. If the event is missing, capture the 10017 chain instead and say so; the troubleshooting page lists which
events to read.

Code scenes (rules, plan, LAPS plan, rollback, tests) come from `script.yaml`; the bad-server excerpt comes from
`sample/check-bad.md` (invented data, labelled "sample data" on screen).

## Masking

- Lab names are fictional (`CON-*`, `lab.contoso.com`, `alex.demo`); keep them.
- **Never show a LAPS password** (no `-AsPlainText`, no decrypted output) or any credential dialog.
- The command-line audit setting means event 4688 now contains command lines: do not open the Security log on camera.
- Crop the VMConnect title bars ("<VM> on <host name>") and the laptop taskbar.

## Tear-down

On CON-SRV02, with the rollback file written by the Harden step:
```powershell
.\Deploy-SecLab.ps1 -Step Rollback -RollbackFile .\rollback.json -WhatIf ; .\Deploy-SecLab.ps1 -Step Rollback -RollbackFile .\rollback.json
```
Then LAPS (the schema extension stays; a rebuilt lab starts clean):
```powershell
Get-GPInheritance -Target "OU=LabServers,$((Get-ADDomain).DistinguishedName)"     # check the link
Remove-GPLink -Name 'MGLab - Windows LAPS' -Target "OU=LabServers,$((Get-ADDomain).DistinguishedName)"
Remove-GPO -Name 'MGLab - Windows LAPS'
foreach ($n in 'CON-SRV01', 'CON-SQL01', 'CON-CLI01') { Get-ADComputer $n | Move-ADObject -TargetPath "CN=Computers,$((Get-ADDomain).DistinguishedName)" }
Remove-ADOrganizationalUnit -Identity "OU=LabServers,$((Get-ADDomain).DistinguishedName)" -Confirm:$false   # may need -Recursive after protection is removed
Remove-Item C:\lab\ep08 -Recurse -Force
```
Passwords already written by LAPS stay on the computer objects until the computers are rebuilt; that is lab-only data.
Remove the RSAT features (`Uninstall-WindowsFeature RSAT-AD-PowerShell, GPMC`) unless an earlier episode still needs them.
