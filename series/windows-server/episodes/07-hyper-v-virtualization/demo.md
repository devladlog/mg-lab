# Demo shot list — DEVLADLOG Windows Server #7: Hyper-V virtualization

## Lab environment

Everything is recorded on the **Hyper-V host itself**: the shared recording laptop (`series/LAB.md`) that runs the
lab VMs (CON-DC01, CON-SRV01 Core, CON-SRV02 Desktop Experience, CON-SQL01, CON-CLI01; internal NAT network
`10.50.0.0/24`; domain `lab.contoso.com` / `CONTOSO`). No cloud, no licence, cost 0. The screens are an elevated
**Windows PowerShell** window on the laptop (plus Hyper-V Manager for one capture).

| Item | Detail |
|---|---|
| Existing VMs | Only **read**: the audit lists CON-DC01, CON-SRV01, CON-SRV02, CON-SQL01, CON-CLI01. Nothing on them changes |
| **Extra VM (new, throwaway)** | **CON-HVT01**: empty Generation 2 VM, no operating system, no ISO. 2 vCPU, 512 MB startup / dynamic 512-1024 MB, 20 GB dynamic VHDX, vTPM + Secure Boot, **no virtual switch, no IP**. Created and deleted by `Deploy-HvLab.ps1` during the recording (row in `series/LAB-REQUESTS.md`) |
| Where its files go | The host's default VM and VHD paths (`Get-VMHost`); `Remove` refuses anything outside them and anything not named `CON-HVT01` |
| Disk | About 1 MB for the new VHDX header until checkpoints grow it; free space of a few GB is plenty |
| Rights | Elevated PowerShell, member of Hyper-V Administrators. Hyper-V PowerShell module installed on the laptop |

Destructive steps (checkpoint removal, VM and disk deletion) touch **only CON-HVT01**. Never point `Deploy-HvLab.ps1`
at a shared lab VM: change `TestVm.Name` in `hv-lab.json` only to another throwaway name.

Everything in `src/` and `tests/` already ran in the build container: 40 Pester tests, the audit on two invented
fact files (`sample/`). **Needs the lab (not run yet):** the collector on the host (property names), creating the
VM, taking and removing checkpoints, the real merge time, the VM removal. Rewrite the narration of the screen scenes to
what actually appears.

## Prepare (before recording)

On the laptop, elevated PowerShell, repo root:

```powershell
cd series\windows-server\episodes\07-hyper-v-virtualization\src
Get-VM | Format-Table Name, State, Generation, Version        # the five CON-* VMs; no CON-HVT01 yet
(Get-VMHost).VirtualMachinePath, (Get-VMHost).VirtualHardDiskPath     # note them: the new VM's files go here
function prompt { 'PS> ' }                                           # large font
```

Check `hv-lab.json`: `TestVm.Name` is `CON-HVT01`, `Switch` is empty. Check `Get-VM CON-HVT01` finds nothing.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/audit.jpg` — "The host, audited"
```powershell
.\Invoke-HvAudit.ps1 -FactsFile .\host-facts.json -OutFile .\audit.md
```
Capture the findings table and the last line (`<host>: 5 VM(s), N finding(s), N high.`). Whatever the real host says
is the truth for the narration (the sample says 0 high on invented data). If the audit reports something real that
is embarrassing or private (paths with a user name, other personal VMs), crop or filter: the five CON-* VMs are the
story, other VMs must not appear (see Masking). Open `audit.md` in the editor for a second shot if it is clean.
If the collector fails on a property name, capture the error, fix `Get-HvCollectorScript`, and say so in README.

### 2. `screens/create.jpg` — "A VM from a file"
```powershell
.\Deploy-HvLab.ps1 -Step Create -WhatIf       # six What if lines
.\Deploy-HvLab.ps1 -Step Create
Get-VM CON-HVT01 | Format-List Name, Generation, Version, ProcessorCount, DynamicMemoryEnabled, CheckpointType, State
Get-VMFirmware CON-HVT01 | Format-List SecureBoot
Get-VMSecurity CON-HVT01 | Format-List TpmEnabled
```
Capture the `-WhatIf` output next to the real result. Expect Generation 2, State Off, Production, Secure Boot On,
TPM enabled.

### 3. `screens/chain.jpg` — "Checkpoints are disks"
```powershell
.\Deploy-HvLab.ps1 -Step Checkpoints
```
Takes `demo-1`, `demo-2`, `demo-3` and `KEEP-baseline`, lists the checkpoints (name, **SnapshotType**, creation time)
and the disk chain. **Record what really happens:** an empty VM has no guest, so `Production` may produce Standard
checkpoints (Learn: fallback to Standard) or fail; whichever it is, that is the shot, and narration says it. Try
once with `-Start` (VM running, no OS) and once Off, keep the more instructive one, and write the result in README
under "What we learned". Then show the chain: `Get-VMHardDiskDrive CON-HVT01 | % { Get-VHD $_.Path } | fl Path,
VhdType, ParentPath`. Optional second window: Hyper-V Manager > CON-HVT01 > Checkpoints tree.

### 4. `screens/cleanup.jpg` — "Plan, remove, wait for the merge"
```powershell
.\Deploy-HvLab.ps1 -Step Cleanup -WhatIf      # shows the plan only
.\Deploy-HvLab.ps1 -Step Cleanup
```
Capture the plan table (Keep / Remove with reasons: `KEEP-baseline` is kept because of its name, the newest demo
checkpoint is kept, the others are removed), then the merge result (`Merged True`, `WaitedSeconds`). If the merge
takes longer than the 600 s timeout the warning is a fine shot; do not delete `.avhdx` files by hand.

The code scenes (audit rules, plan, merge wait, bad-host findings, tests) are rendered from `script.yaml`; the bad-host
excerpt comes from `sample/audit-bad.md` (invented data, say so on screen: "sample data").

## Masking

- Lab names are fictional (`CON-*`, `lab.contoso.com`). Keep them.
- The laptop's real name, user profile folder, other VMs, drive labels with personal names, and the Windows account
  name must not appear: crop the title bar/taskbar, set `$env:COMPUTERNAME` aside, and if the audit's first line shows
  the real computer name, record the table crop only. Paths under `E:\MGLab` are fine.
- No credentials are used in this episode.

## Tear-down

```powershell
.\Deploy-HvLab.ps1 -Step Remove -WhatIf
.\Deploy-HvLab.ps1 -Step Remove               # turns CON-HVT01 off, removes it, deletes the whole disk chain and its folder
Get-VM CON-HVT01 -ErrorAction SilentlyContinue                       # nothing
Get-ChildItem (Get-VMHost).VirtualHardDiskPath -Filter 'CON-HVT01*'   # nothing
Remove-Item .\host-facts.json, .\audit.md -ErrorAction SilentlyContinue
```
The five lab VMs were never changed. If the `Remove` step refuses (name or root), read the message: it names the
file that is outside the allowed roots.
