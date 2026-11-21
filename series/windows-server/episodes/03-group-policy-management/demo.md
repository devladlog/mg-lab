# Demo shot list — DEVLADLOG Windows Server #3: Group Policy Management

## Lab environment

No new VM. Everything runs on the shared Hyper-V lab from `series/LAB.md` (network `10.50.0.0/24`, domain
`lab.contoso.com`, NetBIOS `CONTOSO`):

| VM | Role in this episode | What to install / prepare |
|---|---|---|
| CON-DC01 (10.50.0.10, Server Core) | Domain controller, PDC emulator: the GroupPolicy cmdlets talk to it | nothing |
| CON-SRV01 (10.50.0.21, Server Core) | Target of `CON-Servers-Baseline` (script block logging, NLA) | move to `OU=Servers,OU=Contoso` |
| CON-SRV02 (10.50.0.22, Desktop Experience) | Admin box: GPMC, Windows PowerShell 5.1, and the computer João signs in to for the gotcha | `Install-WindowsFeature GPMC, RSAT-AD-PowerShell`; move to `OU=Servers,OU=Contoso` |

- Screens are recorded on the **CON-SRV02 VM console** (VMConnect, enhanced session, 1600×900, PowerShell font 18+).
  The report preview can be on the host in VS Code (copy `gpo-report.md` out) or in Notepad on CON-SRV02.
- Cost: none (evaluation VMs, no cloud resources). RAM: the three VMs above, ~7 GB maximum together.
- Account: "lab Administrator" (domain admin of the lab) for the deployment; `CONTOSO\jgoncalves` for the gotcha.
  Passwords are typed by the recorder, never on screen and never in files.

Everything in `src/` and `tests/` already ran in the build container: 27 Pester tests (GroupPolicy and
ActiveDirectory cmdlets stubbed and mocked) and the offline report from the fictional snapshot (`sample/report.md`).
**Nothing has run against a real domain yet**: every screen below needs the lab. Rewrite the narration of each screen
scene to what is actually on screen.

## Prerequisites (before recording, not filmed)

1. **OUs, groups and users from episode 2.** If `OU=Contoso` doesn't exist yet, run episode 2's provisioning on
   CON-DC01 or CON-SRV02 (`Invoke-AdLabProvisioning -CsvPath .\src\users.csv ...`, see that episode's README).
   This episode needs `OU=Servers,OU=Contoso`, `OU=Users,OU=Contoso` (with `OU=Finance`), the group
   `GG-Dept-Finance` and the user `jgoncalves` (João Gonçalves, Finance).
2. **Put the member servers in the Servers OU** (on CON-SRV02, Windows PowerShell as lab Administrator):
   ```powershell
   Install-WindowsFeature GPMC, RSAT-AD-PowerShell
   Get-ADComputer -Identity CON-SRV01 | Move-ADObject -TargetPath 'OU=Servers,OU=Contoso,DC=lab,DC=contoso,DC=com'
   Get-ADComputer -Identity CON-SRV02 | Move-ADObject -TargetPath 'OU=Servers,OU=Contoso,DC=lab,DC=contoso,DC=com'
   ```
3. **Sign in once as `CONTOSO\jgoncalves` on CON-SRV02** (first sign-in forces the password change), check that
   console sign-in is allowed for domain users on this member server, sign out.
4. Copy this episode folder to `C:\lab\ep03` on CON-SRV02. If the files came from the internet zone,
   `Get-ChildItem C:\lab\ep03 -Recurse | Unblock-File`.
5. Use **Windows PowerShell 5.1** (`powershell.exe`) for everything: the GroupPolicy module loads natively there.
   `function prompt { 'PS> ' }` for clean frames.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/deploy.jpg` — "Plan, apply, apply again" (**needs lab**)
```powershell
cd C:\lab\ep03\src
Import-Module .\GpoLab\GpoLab.psd1
Invoke-GpoLabDeployment -DefinitionPath .\gpo-definitions.json -WhatIf | Format-Table Gpo, Action, Target, Result -AutoSize
Invoke-GpoLabDeployment -DefinitionPath .\gpo-definitions.json        | Format-Table Gpo, Action, Target, Result -AutoSize
Invoke-GpoLabDeployment -DefinitionPath .\gpo-definitions.json        | Format-Table Gpo, Action, Target, Result -AutoSize
```
Expected: run 1 all `WhatIf` (plus the "What if:" lines); run 2 `Done` for 2 CreateGpo, 2 SetStatus, 4 SetRegistry,
2 Link, 2 Permission; run 3 all `NoChange` (12 rows). Capture runs 2 and 3 in one frame if possible.
- **Verify and note in README:** that `$gpo.GpoStatus = 'UserSettingsDisabled'` persists (GPMC → Details tab →
  GPO Status). If it doesn't, run 3 will show `SetStatus Done` again; report that instead of hiding it.
- **Verify in GPMC → Settings tab** that the four values appear under *Administrative Templates* (Windows PowerShell,
  Remote Desktop Session Host\Security, Control Panel\Personalization) and not under *Extra Registry Settings*. If the
  screen saver values land in Extra Registry Settings, the ADMX expects another value type: fix `Type` in the JSON,
  re-run, and note it in README.
- Optional cut-in: GPMC with `CON-Servers-Baseline` linked to Servers and `CON-Finance-ScreenLock` linked to Users,
  Scope tab of the Finance GPO (Security Filtering: GG-Dept-Finance) and Delegation tab (Authenticated Users: Read).

### 2. `screens/applied.jpg` — "Did it apply? Ask the server" (**needs lab**)
```powershell
Invoke-Command -ComputerName CON-SRV01 { gpupdate /force | Out-Null; gpresult /r /scope computer }
Invoke-Command -ComputerName CON-SRV01 { Get-ItemProperty 'HKLM:\Software\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging' }
Invoke-Command -ComputerName CON-SRV01 {
    Get-WinEvent -LogName 'Microsoft-Windows-PowerShell/Operational' -FilterXPath '*[System[EventID=4104]]' -MaxEvents 3 |
        Format-Table TimeCreated, Id, @{ n = 'ScriptBlock'; e = { $_.Message.Substring(0, [Math]::Min(80, $_.Message.Length)) } } -AutoSize
}
```
Capture: `CON-Servers-Baseline` under *Applied Group Policy Objects*, `EnableScriptBlockLogging : 1`, and 4104 events
(script block logging only logs sessions started after the policy arrived; the `Invoke-Command` sessions are new).
- Why not `Invoke-GPUpdate`? It schedules gpupdate through Task Scheduler and needs the *Remote Scheduled Tasks
  Management* and *WMI-In* firewall rules on the target (Learn). `Invoke-Command` uses WinRM, which is on by default.

### 3. `screens/ms16072.jpg` — "Gotcha: user policy is read by the computer" (**needs lab**)
On CON-SRV02 as lab Administrator, make the classic mistake:
```powershell
Set-GPPermission -Name CON-Finance-ScreenLock -TargetName 'Authenticated Users' -TargetType Group -PermissionLevel None -Replace
Get-GPPermission -Name CON-Finance-ScreenLock -All | Format-Table Trustee, Permission
```
Sign in to CON-SRV02 as `CONTOSO\jgoncalves`, open a command prompt:
```
gpresult /r /scope user
```
Capture what gpresult says about `CON-Finance-ScreenLock` (Learn shows an access-denied error in the HTML report for
this case; `gpresult /h %TEMP%\gp.html` and open it if `/r` only omits the GPO). Then, back as lab Administrator:
```powershell
Invoke-GpoLabDeployment -DefinitionPath .\gpo-definitions.json | Where-Object Result -ne 'NoChange' | Format-Table
# Permission  Authenticated Users=GpoRead  Done
```
João signs out and in again: `gpresult /r /scope user` lists the GPO under applied GPOs, and
`reg query "HKCU\Software\Policies\Microsoft\Windows\Control Panel\Desktop"` shows `ScreenSaverIsSecure 1` and
`ScreenSaveTimeOut 900`. Split screen: broken gpresult left, fixed right.
- The screen saver itself may not start on a server without a configured screen saver (Learn: the timeout has no
  effect without a valid screen saver). The scene is about the policy arriving; don't claim the screen locks.

### 4. Plant two problems for the report (before shot 5, not recorded)
```powershell
New-GPO -Name 'CON-Test-Empty' -Comment 'Planted for the episode 3 report' | Out-Null
New-GPO -Name 'CON-Sales-Legacy' |
    Set-GPRegistryValue -Key 'HKCU\Software\Policies\Microsoft\Windows\Control Panel\Desktop' -ValueName ScreenSaveTimeOut -Type String -Value '600' | Out-Null
(Get-GPO -Name 'CON-Sales-Legacy').GpoStatus = 'UserSettingsDisabled'
New-GPLink -Name 'CON-Sales-Legacy' -Target 'OU=Sales,OU=Users,OU=Contoso,DC=lab,DC=contoso,DC=com' | Out-Null
```

### 5. `screens/report.jpg` — "The lab domain, audited" (**needs lab**)
```powershell
.\Invoke-GpoHygieneReport.ps1 -SnapshotFile .\gpo-snapshot.json -OutFile .\gpo-report.md
```
Expected: `CON-Sales-Legacy` DisabledHalfHasSettings (High), `CON-Test-Empty` UnlinkedGpo + EmptyGpo (Low), nothing
for `CON-Servers-Baseline`, `CON-Finance-ScreenLock` or the two default policies. Record and note in README anything
else that appears (for example a VersionMismatch on a default GPO). Open `gpo-report.md` in a markdown preview.
- Optional B-roll: `Backup-GpoLab -Path C:\lab\gpo-backups` and the folder with the GUID folders + `links.json`.

## Masking
- Everything is fictional (`lab.contoso.com`, `CONTOSO`, CSV names). GPO GUIDs in the lab are random but not
  identifying; no need to blur. Never type passwords on screen.
- Hide the Hyper-V host name, the Windows user profile path on the host and any home-network IPs.

## Tear-down
```powershell
Remove-GPO -Name 'CON-Test-Empty'; Remove-GPO -Name 'CON-Sales-Legacy'
Backup-GpoLab -Path C:\lab\gpo-backups          # keep a copy of the managed GPOs
```
Keep `CON-Servers-Baseline` and `CON-Finance-ScreenLock` (and the servers in `OU=Servers`) unless a later episode says
otherwise; they're harmless in the lab. To remove them: `Remove-GPO -Name CON-Servers-Baseline`,
`Remove-GPO -Name CON-Finance-ScreenLock` (links go with the GPO). Delete `gpo-snapshot.json` / `gpo-report.md`.
