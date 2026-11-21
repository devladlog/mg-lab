# Demo shot list — DEVLADLOG Windows Server #1: Windows Server Administration

Everything in `src/` and `tests/` already ran in the build container (32 Pester tests, offline run from the fictional
snapshots → `sample/report.md`). The live part **needs the lab** (Windows Server VMs); nothing below was run against
a real server yet. Rewrite the narration of the screen scenes to the real numbers on screen.

## Prerequisites

| Item | Notes | Cost |
|---|---|---|
| Hyper-V host (homelab EliteDesk or a desktop) on an **isolated lab VLAN** | Lab AD/DNS must never reach the home network | none |
| 3 × Windows Server 2025 **evaluation** VMs (180 days) | ISO from the Microsoft Evaluation Center. 2 vCPU / 4 GB each is enough | none |
| CON-DC01 | Server Core, first DC of `lab.contoso.com` (built in episode 2 with `setup/New-LabForest.ps1` from ep 02 — or promote it by hand first) | none |
| CON-FS01 | **Desktop Experience**, domain member, `FS-FileServer` role | none |
| CON-APP01 | Server Core, domain member, IIS (`Install-WindowsFeature Web-Server`) | none |
| Admin machine | Domain-joined Windows 11 or one of the servers, with **PowerShell 7.2+** (`winget install Microsoft.PowerShell`) and this repo folder | none |
| Account | A lab domain admin for the recording (lab only). Never a real tenant/domain account | none |

Alternative: Azure VMs with auto-shutdown and a budget alert (cost: a few euros per recording day). Not needed.

## Set up the "problem child" (before recording)

On **CON-FS01** (so the report has something to show — all lab-only changes):

```powershell
Install-WindowsFeature FS-SMB1                    # forbidden feature (reboot if asked, before recording)
Set-NetFirewallProfile -Profile Public -Enabled False
Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server' -Name fDenyTSConnections -Value 0   # RDP on
Add-LocalGroupMember -SID 'S-1-5-32-544' -Member 'CONTOSO\alex.demo'   # create the lab user first (episode 2 CSV)
```

Leave Windows Update alone on CON-FS01 for a few days if you want a real "patch age" finding; otherwise expect none.

Edit `src/baseline.json` before the first run:
- `MinimumUbr`: the latest UBR on the [release information page](https://learn.microsoft.com/windows/release-health/windows-server-release-info)
  that the lab VMs have installed (e.g. `33828` for 26100.33828) — or leave `0`.
- Keep `IgnoreStoppedServices` empty for the first run (that's part of the story), then fill it.

Terminal: dark theme, font 18+, ~1600×900, `function prompt { 'PS> ' }`.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/live-run.jpg` — "Three servers, one command" (**needs lab**)
```powershell
cd src
./Invoke-ServerBaseline.ps1 -ComputerName CON-DC01, CON-FS01, CON-APP01 -SnapshotDir ./snapshots -OutFile ./report.md
```
Capture the findings table and the last line `3 server(s), N finding(s), N high.`
Check and note in README if different:
- the collector runs on Server Core and Desktop Experience without errors (it was only parsed and unit-tested here);
- which **Automatic services are stopped** on fresh 2025 VMs. Copy their names into `IgnoreStoppedServices` *after*
  this shot and re-run (B-roll of that edit is a nice extra);
- `TimeSource` on CON-DC01: a fresh first DC often reports `Local CMOS Clock` → High finding. Keep it if it happens;
  fix with `w32tm /config /manualpeerlist:"pool.ntp.org" /syncfromflags:manual /reliable:yes /update` only in the lab.

### 2. `screens/report.jpg` — "Worst first" (**needs lab**)
Open `report.md` in VS Code preview. Summary table on top, High rows first. Zoom on CON-FS01's High rows
(FS-SMB1, Public firewall off), plus the Low `Rdp` and `InstallationType` rows.

### 3. `screens/fixed.jpg` — "Fix it, run it again" (**needs lab**)
```powershell
Invoke-Command -ComputerName CON-FS01 { Uninstall-WindowsFeature FS-SMB1; Set-NetFirewallProfile -Profile Public -Enabled True }
./Invoke-ServerBaseline.ps1 -ComputerName CON-DC01, CON-FS01, CON-APP01 -OutFile ./report.md
```
Show that `ForbiddenFeature` and `Firewall` rows are gone. If a `PendingReboot` row appears after the uninstall,
keep it on screen (the narration covers it).

### 4. `screens/hotfix.jpg` — "Gotcha: Get-HotFix doesn't list every update" (**needs lab**)
On CON-FS01 (Desktop Experience): left, `Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 5`;
right, **Settings → Windows Update → Update history**. Point at an entry Get-HotFix doesn't list (typically a
definition update). If nothing differs on the day, capture the *Notes* section of the
[Get-HotFix page](https://learn.microsoft.com/powershell/module/microsoft.powershell.management/get-hotfix) instead
and adjust the narration.

Code scenes (remoting, collector, ps51, baseline, checks, tests) are rendered from `script.yaml`; the `tests` scene
shows the real Pester output from the build container.

## Masking

- Lab names are fictional (`CON-*`, `lab.contoso.com`, `alex.demo`) — keep them. Never show the real tenant name,
  public IPs, the Hyper-V host's name or Wi-Fi/VLAN names.
- Terminal title bars and the Windows taskbar can show the host/user name: crop or run `pipeline/mask.js` for
  browser shots.
- Evaluation watermark on the desktop is fine (and honest).

## Tear-down

```powershell
Invoke-Command -ComputerName CON-FS01 {
    Remove-LocalGroupMember -SID 'S-1-5-32-544' -Member 'CONTOSO\alex.demo'
    Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server' -Name fDenyTSConnections -Value 1
}
Remove-Item ./snapshots, ./report.md -Recurse -Force
```
Keep the VMs for episode 2 (same lab). If you used Azure: delete the resource group, check the budget alert.
