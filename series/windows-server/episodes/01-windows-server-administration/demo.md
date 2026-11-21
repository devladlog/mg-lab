# Demo shot list — DEVLADLOG Windows Server #1: Windows Server Administration

## Lab environment

All screens are recorded on the **shared local Hyper-V lab** (`series/LAB.md`): domain `lab.contoso.com`, NetBIOS
`CONTOSO`, network `10.50.0.0/24`. No extra VM, no tenant, no Azure, no licence (evaluation editions), cost 0.

| Role in the episode | Shared VM | OS / edition | IP | Changes made for the recording (all undone in tear-down) |
|---|---|---|---|---|
| Domain controller (healthy Core server) | **CON-DC01** | WS 2025 Datacenter Eval, Server Core | 10.50.0.10 | none (read-only target); AD user `alex.demo` created for the local-admin finding |
| App server (healthy Core server) | **CON-SRV01** | WS 2025 Datacenter Eval, Server Core | 10.50.0.21 | IIS (`Web-Server`) installed |
| File server, the "problem child" | **CON-SRV02** | WS 2025 Datacenter Eval, **Desktop Experience** | 10.50.0.22 | `FS-FileServer`, then SMB1, Public firewall profile off, RDP on, `CONTOSO\alex.demo` in local Administrators |
| Admin machine (runs the baseline) | **CON-CLI01** | WS 2025 Datacenter Eval, Server Core | 10.50.0.41 | PowerShell 7 (MSI) and the episode folder in `C:\lab\ep01` |

- Earlier drafts named the servers CON-FS01 and CON-APP01; they map to **CON-SRV02** and **CON-SRV01**. The test
  fixtures and `sample/report.md` keep the fictional CON-FS01/CON-APP01 snapshots (tests only).
- Sign-in everywhere: the **lab Administrator** (`CONTOSO\Administrator`); the recorder types the password, it is
  never written in a file or shown.
- Recording machine: the Windows lab laptop (Hyper-V host). Screens are VMConnect windows of CON-CLI01 (terminal)
  and CON-SRV02 (Settings app), plus VS Code on the laptop for the report preview.

Everything in `src/` and `tests/` already ran in the build container (32 Pester tests, offline run from the fictional
snapshots → `sample/report.md`). The live part has not been run against a real server yet. Rewrite the narration of
the screen scenes to the real numbers on screen.

## Prepare the lab (before recording)

From an elevated PowerShell 7 on the laptop (PowerShell Direct, no network credentials needed):

```powershell
$cred = Get-Credential 'CONTOSO\Administrator'            # lab Administrator, typed off camera
# admin machine: PowerShell 7 + the episode folder
$cli = New-PSSession -VMName CON-CLI01 -Credential $cred
Copy-Item -ToSession $cli -Path .\series\windows-server\episodes\01-windows-server-administration -Destination C:\lab\ep01 -Recurse
Copy-Item -ToSession $cli -Path <PowerShell-7.x-win-x64.msi> -Destination C:\lab\
Invoke-Command -Session $cli { Start-Process msiexec.exe '/i C:\lab\PowerShell-7.x-win-x64.msi /quiet' -Wait }  # use the real file name
# app server
Invoke-Command -VMName CON-SRV01 -Credential $cred { Install-WindowsFeature Web-Server }
# lab AD user for the local-admin finding
Invoke-Command -VMName CON-DC01 -Credential $cred {
    New-ADUser -Name 'Alex Demo' -SamAccountName alex.demo -UserPrincipalName alex.demo@lab.contoso.com -Enabled $false
}
```

On **CON-SRV02** (the "problem child", lab-only changes so the report has something to show):

```powershell
Invoke-Command -VMName CON-SRV02 -Credential $cred {
    Install-WindowsFeature FS-FileServer, FS-SMB1             # forbidden feature (reboot if asked, before recording)
    Set-NetFirewallProfile -Profile Public -Enabled False
    Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server' -Name fDenyTSConnections -Value 0   # RDP on
    Add-LocalGroupMember -SID 'S-1-5-32-544' -Member 'CONTOSO\alex.demo'
}
```

Leave Windows Update alone on CON-SRV02 for a few days if you want a real "patch age" finding; otherwise expect none.

Edit `src/baseline.json` (the copy in `C:\lab\ep01`) before the first run:
- `MinimumUbr`: the latest UBR on the [release information page](https://learn.microsoft.com/windows/release-health/windows-server-release-info)
  that the lab VMs have installed (e.g. `33828` for 26100.33828) — or leave `0`.
- Keep `IgnoreStoppedServices` empty for the first run (that's part of the story), then fill it.

Terminal on CON-CLI01: `pwsh`, `function prompt { 'PS> ' }`, VMConnect window maximised, console font large enough
to read at 1080p.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/live-run.jpg` — "Three servers, one command"
On CON-CLI01, in `pwsh`:
```powershell
cd C:\lab\ep01\src
./Invoke-ServerBaseline.ps1 -ComputerName CON-DC01, CON-SRV01, CON-SRV02 -SnapshotDir ./snapshots -OutFile ./report.md
```
Capture the findings table and the last line `3 server(s), N finding(s), N high.`
Check and note in README if different:
- the collector runs on Server Core and Desktop Experience without errors (it was only parsed and unit-tested here);
- which **Automatic services are stopped** on fresh 2025 VMs. Copy their names into `IgnoreStoppedServices` *after*
  this shot and re-run (B-roll of that edit is a nice extra);
- `TimeSource` on CON-DC01: a first DC often reports `Local CMOS Clock` → High finding. Keep it if it happens. Don't
  reconfigure time on the shared DC for the video.

### 2. `screens/report.jpg` — "Worst first"
Copy the report to the laptop (`Copy-Item -FromSession $cli C:\lab\ep01\src\report.md -Destination .\report.md`) and
open it in VS Code preview, or show it in the CON-CLI01 console. Summary table on top, High rows first. Zoom on
CON-SRV02's High rows (FS-SMB1, Public firewall off), plus the Low `Rdp` and `InstallationType` rows.

### 3. `screens/fixed.jpg` — "Fix it, run it again"
On CON-CLI01:
```powershell
Invoke-Command -ComputerName CON-SRV02 { Uninstall-WindowsFeature FS-SMB1; Set-NetFirewallProfile -Profile Public -Enabled True }
./Invoke-ServerBaseline.ps1 -ComputerName CON-DC01, CON-SRV01, CON-SRV02 -OutFile ./report.md
```
Show that `ForbiddenFeature` and `Firewall` rows are gone. If a `PendingReboot` row appears after the uninstall,
keep it on screen (the narration covers it), then reboot CON-SRV02 after the shot.

### 4. `screens/hotfix.jpg` — "Gotcha: Get-HotFix doesn't list every update"
On CON-SRV02 (VMConnect, Desktop Experience): left, `Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 5`;
right, **Settings → Windows Update → Update history**. Point at an entry Get-HotFix doesn't list (typically a
definition update). If nothing differs on the day, capture the *Notes* section of the
[Get-HotFix page](https://learn.microsoft.com/powershell/module/microsoft.powershell.management/get-hotfix) instead
and adjust the narration.

Code scenes (remoting, collector, ps51, baseline, checks, tests) are rendered from `script.yaml`; the `tests` scene
shows the real Pester output from the build container.

## Masking

- Lab names are fictional (`CON-*`, `lab.contoso.com`, `alex.demo`) — keep them. Never show the real tenant name,
  public IPs, the Hyper-V host's (laptop's) name or Wi-Fi names.
- VMConnect title bars show "<VM> on <host name>": crop them. The laptop's taskbar and VS Code title bar can show the
  Windows user name: crop or record from a neutral folder.
- Evaluation watermark on the desktop is fine (and honest).

## Tear-down

On the laptop (`$cred` as above):
```powershell
Invoke-Command -VMName CON-SRV02 -Credential $cred {
    Remove-LocalGroupMember -SID 'S-1-5-32-544' -Member 'CONTOSO\alex.demo'
    Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server' -Name fDenyTSConnections -Value 1
    Uninstall-WindowsFeature FS-SMB1, FS-FileServer        # if not already removed in shot 3
    Set-NetFirewallProfile -Profile Public -Enabled True
}
Invoke-Command -VMName CON-SRV01 -Credential $cred { Uninstall-WindowsFeature Web-Server }
Invoke-Command -VMName CON-DC01  -Credential $cred { Remove-ADUser alex.demo -Confirm:$false }
Invoke-Command -Session $cli { Remove-Item C:\lab\ep01 -Recurse -Force }   # PowerShell 7 can stay for episode 2
Remove-PSSession $cli
```
Restart CON-SRV01/CON-SRV02 if a reboot is pending. The shared VMs stay for the rest of the series.
