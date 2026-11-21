# Demo shot list — DEVLADLOG Windows Server #10: Server Core & Nano Server

## Lab environment

Recorded on the **shared local Hyper-V lab** (`series/LAB.md`): domain `lab.contoso.com` / `CONTOSO`, network
`10.50.0.0/24`. **No extra VM** (nothing to add to `series/LAB-REQUESTS.md`), no cloud, no licence, cost 0.

| Role in the episode | VM | OS / edition | IP | Notes |
|---|---|---|---|---|
| **Admin console, runs everything** | CON-SRV02 (shared) | WS 2025 Datacenter Eval, Desktop Experience | 10.50.0.22 | episode folder in `C:\lab\ep10`; Windows PowerShell 5.1 |
| Server Core, gets the App Compatibility FOD and the restart | CON-SRV01 (shared) | WS 2025 Datacenter Eval, Server Core | 10.50.0.21 | its console is the SConfig screen |
| Server Core, only read | CON-DC01, CON-SQL01 (shared) | Server Core | .10 / .30 | |
| Server Core, switched off for one screen | CON-CLI01 (shared) | Server Core | 10.50.0.41 | powered off to produce "no answer", started again afterwards |

- Screens are recorded on **CON-SRV02** (VMConnect, elevated Windows PowerShell) signed in as the **lab Administrator**
  (`CONTOSO\Administrator`). The SConfig screen is the **console of CON-SRV01** in VMConnect, signed in the same way.
  Passwords are never typed on camera or written in a file.
- **Before recording: Hyper-V checkpoints** of the three VMs that change, on the laptop (elevated PowerShell):
  `foreach ($v in 'CON-SRV01','CON-SQL01','CON-CLI01') { Checkpoint-VM -Name $v -SnapshotName pre-ep10 }`.
  That is the tear-down (below). The check itself changes nothing.
- The App Compatibility FOD comes from **Windows Update** (needs outbound access from CON-SRV01 through the lab NAT). If
  that does not work, mount the Windows Server 2025 *Languages and Optional Features* ISO that the Learn article links to
  in the VM, set `Setup.FodSourcePath` in `core-lab.json` to `<drive>:\LanguagesAndOptionalFeatures` and say so on camera.

Everything in `src/` and `tests/` already ran in the build container: 56 Pester tests, and the check on three **invented**
fact files (`sample/`). **Needs the lab (not run yet):** the collector on real servers, the real footprint numbers, the
FOD install and the restart. The narration of the screen scenes is written from the invented samples: **rewrite it to what
the real lab shows** (the sample numbers are not measurements).

## Prepare (before recording)

On the laptop (Hyper-V host), elevated PowerShell, repo root:

```powershell
$cred = Get-Credential 'CONTOSO\Administrator'                      # typed off camera
foreach ($v in 'CON-SRV01','CON-SQL01','CON-CLI01') { Checkpoint-VM -Name $v -SnapshotName pre-ep10 }
$s = New-PSSession -VMName CON-SRV02 -Credential $cred
Copy-Item -ToSession $s -Path .\series\windows-server\episodes\10-server-core-nano-server -Destination C:\lab\ep10 -Recurse -Force
Remove-PSSession $s
```

On CON-SRV02: **Windows PowerShell (Admin)**, `cd C:\lab\ep10\src`, `function prompt { 'PS> ' }`, large font. Read the real
numbers first, with `.\Invoke-CoreCheck.ps1` and no switches. The default limit for a Core system drive in
`core-lab.json` (16 GB) is our guess, not a Microsoft figure: if the real Core servers are all above or far below it,
change it to something that makes sense and **say so on camera**.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/sconfig.jpg` — "The real console of a Core server"
VMConnect to **CON-SRV01**, signed in as the lab Administrator. SConfig starts by itself (Learn: from Windows Server 2022
on). Show the main menu, type `4` to show *Configure remote management* (do **not** change anything), back out, then `15` for
the PowerShell prompt and `exit` to get SConfig back. Capture the menu with the server name and domain in view. Crop the
VMConnect title bar.

### Seed the state the check will find (off camera)
1. **A server that does not answer:** on the laptop, `Stop-VM -Name CON-CLI01 -TurnOff` (the check cannot tell "off" from
   "WinRM broken": both are *no answer*, and the script says so in the message).
2. **The FOD is missing on CON-SRV01:** nothing to seed; it is not there by default. Check on the console with
   `Get-WindowsCapability -Online | Where-Object Name -like 'ServerCore.AppCompatibility*'`.
3. Leave CON-SRV02 as it is: it has the desktop on purpose, and the check should list the features that would block Core.

### 2. `screens/check-before.jpg` — "The lab, as it is today"
```powershell
.\Invoke-CoreCheck.ps1 -FactsFile .\facts-before.json -OutFile .\check-before.md -PlanOnly
```
Capture the findings table, the setup plan table and the last line. Expect: `Unreachable` (CON-CLI01), `AppCompatMissing`
(CON-SRV01), `DesktopJustified` and `CoreBlockers` (CON-SRV02, with the real list), and whatever the numbers say for
`FootprintHigh`. `WinRmFirewall` is unlikely on a live lab (see README). Keep any `CollectorError` rows: they are part
of the truth (`Get-WindowsCapability` and `Get-WindowsFeature` run on the server through `Invoke-Command`).

### 3. `screens/setup.jpg` — "WhatIf first, then the real run"
```powershell
.\Deploy-CoreLab.ps1 -WhatIf                     # plan + What if lines; the restart is a Skipped row
.\Deploy-CoreLab.ps1                             # Add-WindowsCapability on CON-SRV01 (takes several minutes: Learn)
.\Deploy-CoreLab.ps1 -AllowRestart               # restarts CON-SRV01
```
Capture the plan, the Result table with `restart needed` in the detail, and the second Result table with the restart
requested. Wait for CON-SRV01 to come back (`Test-WSMan CON-SRV01`) before the next screen. Start CON-CLI01 again:
`Start-VM -Name CON-CLI01`.

If the FOD install fails (no source), record the failed row, set `Setup.FodSourcePath`, rerun, and use that on screen.

### 4. `screens/check-after.jpg` — "After the fixes, and the footprint"
```powershell
.\Invoke-CoreCheck.ps1 -OutFile .\check-after.md
Get-Content .\check-after.md | Select-String -Pattern 'Footprint' -Context 0,8
```
Capture the findings table (the High and Medium rows gone) and the *Footprint by install type* table. Say that it compares
servers that run different roles.

Code scenes (collector, plan, Nano rule, gotcha, tests) come from `script.yaml`; the Pester output comes from the command
in README. The Nano Server part has **no recording**: it is the check on text, shown as code in the video. If you want it
on screen, run on CON-SRV02: `& .\Invoke-CoreCheck.ps1 -FromFacts ..\tests\fixtures\facts-after.json -Dockerfile ..\tests\fixtures\Dockerfile.nano-bad`
(no image is built; there is no Windows container host in the lab plan).

## Masking

- Lab names are fictional (`CON-*`, `lab.contoso.com`); keep them.
- Crop the VMConnect title bars ("<VM> on <host name>") and the laptop taskbar.
- Nothing secret appears: the scripts never print credentials.

## Tear-down

The check changes nothing. The setup changed CON-SRV01 (FOD, restart). Restore the checkpoints taken in *Prepare*:
```powershell
foreach ($v in 'CON-SRV01','CON-SQL01','CON-CLI01') { Restore-VMSnapshot -VMName $v -Name pre-ep10 -Confirm:$false }
foreach ($v in 'CON-SRV01','CON-SQL01','CON-CLI01') { Remove-VMSnapshot -VMName $v -Name pre-ep10 }      # after checking they are fine
```
If the checkpoints cannot be used, remove the FOD on CON-SRV01 (`Remove-WindowsCapability -Online -Name ServerCore.AppCompatibility~~~~0.0.1.0`, then
restart) and make sure CON-CLI01 is running. Delete `C:\lab\ep10` on CON-SRV02.
