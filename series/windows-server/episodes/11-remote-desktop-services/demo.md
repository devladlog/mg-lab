# Demo shot list — DEVLADLOG Windows Server #11: Remote Desktop Services

## Lab environment

Recorded on the **shared local Hyper-V lab** (`series/LAB.md`): domain `lab.contoso.com` / `CONTOSO`, network
`10.50.0.0/24`. No cloud, no extra licence, cost 0. One **extra throwaway VM** is needed, because Learn says the RD
Session Host, RD Web Access and RD Gateway role services are **not in Server Core** and CON-SRV02 (the only shared
Desktop Experience VM) is kept clean for the other episodes. Row added to `series/LAB-REQUESTS.md`.

| Role in the episode | VM | OS / edition | vCPU / RAM / disk | IP | Changes made |
|---|---|---|---|---|---|
| **RDS server: Connection Broker + Session Host + Web Access + Licensing, and the console where everything runs** | **CON-RDS01 (new, throwaway)** | Windows Server 2025 Datacenter Evaluation, **Desktop Experience** | 2 / 4 GB (dynamic 4-6 GB) / 60 GB | 10.50.0.44 (`MGLab-NAT`, gateway 10.50.0.1, DNS 10.50.0.10), joined to `lab.contoso.com` | the RDS role services, the collection, the episode folder `C:\lab\ep11`. Deleted after the recording |
| Client that connects | CON-SRV02 | WS 2025 Datacenter Eval, Desktop Experience (shared) | existing | 10.50.0.22 | none (only runs `mstsc` and a browser; the connection leaves `alex.demo`'s profile on CON-RDS01 only) |
| Domain controller | CON-DC01 | shared | existing | 10.50.0.10 | one AD group `RDS Demo Users` (removed in tear-down) |

- Screens are recorded on **CON-RDS01** in VMConnect (elevated **Windows PowerShell 5.1**) as the **lab Administrator**
  (`CONTOSO\Administrator`), and for the session screen on **CON-SRV02**. Passwords are never typed on camera or
  written in a file.
- Lab users: `alex.demo` connects (fictional, password set by the lab owner). Nobody else is used.
- Windows Server evaluation edition is fine: the **120 day licensing grace period** is exactly what the episode is
  about; no RDS CAL is bought or installed.

Everything in `src/` and `tests/` already ran in the build container: 46 Pester tests and the check on four invented
fact files (`sample/`). **Needs the lab (not run yet):** the collectors (property names of the `Get-RD*` output
objects are not documented on Learn, see README "Not run yet"), `New-RDSessionDeployment` and everything after it, the
session screens, the logoff. Rewrite the narration of the screen scenes to the real output (counts, findings, state
names) on the recording day.

## Prepare (before recording)

1. Create the VM (Hyper-V host, elevated PowerShell), install Windows Server 2025 Datacenter Evaluation with
   Desktop Experience, name it `CON-RDS01`, set 10.50.0.44/24, DNS 10.50.0.10, join the domain, restart.
2. On the laptop copy the episode folder in (PowerShell Direct, credential typed off camera):
```powershell
$cred = Get-Credential 'CONTOSO\Administrator'
$s = New-PSSession -VMName CON-RDS01 -Credential $cred
Copy-Item -ToSession $s -Path .\series\windows-server\episodes\11-remote-desktop-services -Destination C:\lab\ep11 -Recurse -Force
Remove-PSSession $s
```
3. Create the AD group the collection will allow (on CON-SRV02 or CON-DC01 with RSAT, as Domain Admin):
```powershell
.\setup\New-RdsDemoGroup.ps1 -WhatIf ; .\setup\New-RdsDemoGroup.ps1        # RDS Demo Users = alex.demo, sam.demo
```
4. On CON-RDS01 make sure WinRM answers its own FQDN (the collector uses `Invoke-Command`):
   `Test-WSMan con-rds01.lab.contoso.com`. Open **Windows PowerShell (Admin)**, `cd C:\lab\ep11\src`,
   `function prompt { 'PS> ' }`, large font. **No RDS roles installed yet.**

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/check-before.jpg` — "A broker with nothing behind it"
```powershell
.\Invoke-RdsCheck.ps1 -FactsFile .\facts-before.json -OutFile .\check-before.md -PlanOnly
```
Expect `NoDeployment` (High) because `Get-RDServer` finds no deployment; the module may also report a `CollectorError`
from the RemoteDesktop cmdlets when no deployment exists: keep it, it is the truth. Grace days should read 120 (a
fresh server) or the count of days since the VM got the role. Capture the findings, the five-step plan and the last
line. The sample on invented data says 2 findings, 1 high.

### 2. `screens/apply.jpg` — "What if first, then for real"
```powershell
.\Deploy-RdsLab.ps1 -Step Apply -WhatIf
.\Deploy-RdsLab.ps1 -Step Apply -AllowDeployment
```
`New-RDSessionDeployment` installs role services and the server **may restart**; if it does, sign in again and re-run
`.\Deploy-RdsLab.ps1 -Step Apply -AllowDeployment`: the plan is rebuilt from the facts, so finished steps disappear
(this also proves idempotence on camera). Repeat until the output is the Certificate manual warning only. Do not edit
`rds-lab.json`. If a step fails, capture the error and the re-run; fixing it live is better than hiding it.

### 3. `screens/check-after.jpg` — "Check again"
```powershell
.\Invoke-RdsCheck.ps1 -OutFile .\check-after.md
Get-RDCertificate | Format-Table Role, Level, ExpiresOn
```
Expect the collection findings gone and three or four `CertSelfSigned` Medium findings plus the single-server Info rows
(the sample on invented data says 5 findings, 0 high). Optional second shot from CON-SRV02: Edge at
`https://con-rds01.lab.contoso.com/RDWeb` showing the real certificate warning.

### 4. `screens/sessions.jpg` — "Who is on the server?"
On CON-SRV02: `mstsc /v:con-rds01.lab.contoso.com`, sign in as `CONTOSO\alex.demo` (password off camera), open Notepad,
then close the RDP window with the X (disconnect, not log off). Back on CON-RDS01:
```powershell
.\Invoke-RdsCheck.ps1 -OutFile .\check-sessions.md
Get-RDUserSession | Format-Table UserName, HostServer, SessionState, UnifiedSessionId
```
Capture the Sessions table and the raw `SessionState` text (the module matches `ACTIVE` / `DISCONNECT` loosely; if the
real text differs, fix `Get-RdsSessionSummary` and `Invoke-RdsDisconnectedLogoff` and say so in README). The first
sign-in shows the "licensing mode is not configured" or a grace period balloon only if licensing is not set; with the
plan applied it should not appear for the per user mode (Learn: it can still appear with a local account or an
administrative session).

### 5. `screens/logoff.jpg` — "Log off the stale one"
```powershell
.\Deploy-RdsLab.ps1 -Step Logoff -UserName alex.demo -WhatIf
.\Deploy-RdsLab.ps1 -Step Logoff -UserName alex.demo
Get-RDUserSession
```
Capture the What if line (user, host, session id), the `LoggedOff` row and the empty session list. `Invoke-RDUserLogoff`
closes the open Notepad: that is the point of the guard rails.

Code scenes (rules, plan, collection, logoff, Core gotcha, tests) come from `script.yaml`; the plan table and the
"found before" values come from `sample/check-defaults.md` (invented data, labelled "sample data" on screen).

## Masking

- Lab names are fictional (`CON-*`, `lab.contoso.com`, `alex.demo`); keep them.
- No password, no RDS CAL or licence key (none is used), no tenant URL. This episode never signs in to the cloud.
- Crop the VMConnect title bars ("<VM> on <host name>") and the laptop taskbar.

## Tear-down

On CON-RDS01 (optional, the VM is deleted anyway):
```powershell
Remove-RDSessionCollection -CollectionName 'MG Lab Desktops' -Force
Remove-Item C:\lab\ep11 -Recurse -Force
```
Then on the laptop: **delete the VM CON-RDS01, its VHDX, and its computer account** (`Remove-ADComputer CON-RDS01` on
CON-DC01) and, on CON-DC01, `Remove-ADGroup 'RDS Demo Users' -Confirm:$false`. The stale `alex.demo` profile only exists
on CON-RDS01. Delete the row's VM from the lab inventory; `lab.config.psd1` is not edited by this episode.
