# Demo shot list — DEVLADLOG Windows Server #12: Failover Clustering

## Lab environment

Recorded on the **shared local Hyper-V lab** (`series/LAB.md`): domain `lab.contoso.com` / `CONTOSO`, network
`10.50.0.0/24`. No cloud, no extra licence, cost 0. A cluster needs at least two nodes, and the shared VMs must stay
clean for the other episodes, so **two extra throwaway Server Core VMs** are needed. Rows added to
`series/LAB-REQUESTS.md`.

| Role in the episode | VM | OS / edition | vCPU / RAM / disk | IP | Changes made |
|---|---|---|---|---|---|
| **Cluster node 1, and the console where the build runs** | **CON-NODE01 (new, throwaway)** | Windows Server 2025 Datacenter Evaluation, **Server Core** | 2 / 2 GB / 40 GB | 10.50.0.51 (`MGLab-NAT`, gateway 10.50.0.1, DNS 10.50.0.10), joined to `lab.contoso.com` | Failover Clustering, IIS, the cluster `CON-CL01`, the folder `C:\lab\ep12`. Deleted after the recording |
| **Cluster node 2** | **CON-NODE02 (new, throwaway)** | same | 2 / 2 GB / 40 GB | 10.50.0.52 | Failover Clustering, IIS. Deleted after the recording |
| Witness share host | CON-SRV01 | shared (Server Core) | existing | 10.50.0.21 | the folder `C:\ClusterWitness` and the share `ClusterWitness`, created by the build and removed by `-Step Remove` |
| Prober and second console | CON-SRV02 | shared (Desktop Experience) | existing | 10.50.0.22 | none (only runs `Watch-ClusterRole.ps1`) |
| Domain controller | CON-DC01 | shared | existing | 10.50.0.10 | two computer objects `CON-CL01` and `CON-WEB` (cluster name objects), removed by `-Step Remove` |

- Clustered addresses (free in the lab range, not in `lab.config.psd1`): cluster `CON-CL01` **10.50.0.60**, role
  `CON-WEB` **10.50.0.61**. Check that nothing answers a ping on them before the recording.
- Screens are recorded in VMConnect as the **lab Administrator** (`CONTOSO\Administrator`), in elevated **Windows
  PowerShell 5.1** on Server Core (a console window, no desktop). Passwords are never typed on camera or written in a
  file.
- **Run the build on CON-NODE01**: Learn says `New-Cluster`, `Add-ClusterGenericServiceRole` and `Remove-Cluster` cannot
  run remotely without CredSSP, and the script refuses to start on a machine that is not a node.
- Shared storage is not used: the cluster is created with `-NoStorage` and the validation ignores the storage tests.
  The clustered role is the IIS service `W3SVC`, which needs no disk.

Everything in `src/` and `tests/` already ran in the build container: 52 Pester tests, the readiness check on three
invented fact files (`sample/`) and the prober summary on a saved run. **Needs the lab (not run yet):** the collector,
the feature install, `Test-Cluster`, `New-Cluster`, the witness share and `Set-ClusterQuorum`, the clustered role, the
drain and the hard stop, see README "Not run yet". Rewrite the narration of the screen scenes to the real output
(findings, restarts, outage seconds) on the recording day.

## Prepare (before recording)

1. Create the two VMs (Hyper-V host, elevated PowerShell), install Server Core, name them `CON-NODE01` and `CON-NODE02`,
   set 10.50.0.51 and .52 /24, DNS 10.50.0.10, join the domain, restart. Take a checkpoint `pre-ep12`.
2. On the laptop copy the episode folder to CON-NODE01 and to CON-SRV02 (PowerShell Direct, credential typed off camera):
```powershell
$cred = Get-Credential 'CONTOSO\Administrator'
foreach ($vm in 'CON-NODE01') {
  $s = New-PSSession -VMName $vm -Credential $cred
  Copy-Item -ToSession $s -Path .\series\windows-server\episodes\12-failover-clustering -Destination C:\lab\ep12 -Recurse -Force
  Remove-PSSession $s
}
```
   Do the same for CON-SRV02 (only `src\` is needed there).
3. On CON-NODE01: `Test-WSMan CON-NODE02`, `Test-WSMan CON-SRV01`. Open **Windows PowerShell (Admin)**: on Server Core
   run `powershell` in the console, `cd C:\lab\ep12\src`, `function prompt { 'PS> ' }`. **Nothing clustered yet.**
4. Optional, off camera: let the clocks drift on purpose with `w32tm` on one node to show `ClockSkew`; put it back
   afterwards (`w32tm /resync`).

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/ready-before.jpg` — "Check the nodes first"
```powershell
.\Invoke-ClusterReadiness.ps1 -FactsFile .\facts-before.json -OutFile .\ready-before.md -PlanOnly
```
Expect the node table, `FeatureMissing` (Medium) on both nodes, `WitnessShareMissing` (Medium), the quorum arithmetic and
the 11-step plan. The sample on invented data says 6 findings, 0 high. If a collector line fails, keep the
`NodeUnreachable` or error row: it is the truth.

### 2. `screens/build.jpg` — "Build it, with What if first"
```powershell
.\Deploy-ClusterLab.ps1 -Step Build -WhatIf
.\Deploy-ClusterLab.ps1 -Step Build
```
Installing the feature may ask for a **restart** on a node; restart it, sign in again and re-run the same command: the
plan is rebuilt from the facts, so finished steps drop out. Capture the final `Get-ClusterNode`, `Get-ClusterGroup`
and `Get-ClusterQuorum` output. If `Test-Cluster` reports warnings (no shared storage is expected), say so: it still
completes. If `Set-ClusterQuorum` is refused for access reasons, the cluster account needs access to the share (README
"Not run yet"); fix it live and show it.

### 3. `screens/drain.jpg` — "A planned failover, measured"
On CON-SRV02 start the prober first:
```powershell
.\Watch-ClusterRole.ps1 -Url http://10.50.0.61/ -DurationSec 90 -OutFile .\drain.jsonl
```
and 15 seconds later on CON-NODE01:
```powershell
.\Deploy-ClusterLab.ps1 -Step Drain -WhatIf
.\Deploy-ClusterLab.ps1 -Step Drain
```
Capture both windows: the `From` / `To` row and the prober summary. The probe has a 2 s request timeout, so an outage is
measured to about two seconds, not milliseconds (README, gotchas).

### 4. `screens/crash.jpg` — "Now stop a node the hard way" (optional)
Prober again for 120 s. On the Hyper-V host: `Stop-VM -Name <the owning node> -TurnOff` (find it with
`Get-ClusterGroup CON-WEB` on the surviving node). Capture the role online on the other node and the outage table. Start
the VM again and wait for the node to rejoin before tear-down.

Code scenes (quorum, rules, plan, probe, gotcha, tests) come from `script.yaml`; the quorum table, plan and probe summary
come from `sample/` and `tests/fixtures/probe-drain.jsonl` (invented data, labelled "sample data" on screen).

## Masking

- Lab names are fictional (`CON-*`, `lab.contoso.com`, `alex.demo`); keep them.
- No password, no licence key, no tenant URL. This episode never signs in to the cloud.
- Crop the VMConnect title bars ("<VM> on <host name>") and the laptop taskbar.

## Tear-down

On CON-NODE01:
```powershell
.\Deploy-ClusterLab.ps1 -Step Remove -WhatIf
.\Deploy-ClusterLab.ps1 -Step Remove      # Remove-Cluster -CleanupAD -Force, then the witness share on CON-SRV01
```
Then **delete the VMs CON-NODE01 and CON-NODE02 with their VHDX files** and their computer accounts
(`Remove-ADComputer CON-NODE01`, `CON-NODE02` on CON-DC01), and check that `CON-CL01` and `CON-WEB` are gone from AD
(`Get-ADComputer -Filter "Name -like 'CON-CL01' -or Name -like 'CON-WEB'"`). Check that `\\CON-SRV01\ClusterWitness` and
`C:\ClusterWitness` no longer exist. `lab.config.psd1` is not edited by this episode.
