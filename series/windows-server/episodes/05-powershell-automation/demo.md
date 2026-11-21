# Demo shot list — DEVLADLOG Windows Server #5: PowerShell Automation

## Lab environment

All screens are recorded on the **shared local Hyper-V lab** (`series/LAB.md`): domain `lab.contoso.com`, NetBIOS
`CONTOSO`, network `10.20.0.0/24`. No extra VM, no tenant, no Azure, no licence (evaluation editions), cost 0.

| Role in the episode | Shared VM | OS / edition | IP | Changes made for the recording (all undone in tear-down, except the KDS root key) |
|---|---|---|---|---|
| Domain controller: groups, gMSA | **CON-DC01** | WS 2025 Datacenter Eval, Server Core | 10.20.0.10 | KDS root key (lab form, see below), groups `GG-AppOps-Readers` / `GG-AppOps-Operators`, gMSA `gmsa-opsjob`, enabled user `alex.demo` |
| App server with the JEA endpoint | **CON-SRV01** | WS 2025 Datacenter Eval, Server Core | 10.20.0.21 | IIS (`Web-Server`), module `ContosoOps` in `C:\Program Files\WindowsPowerShell\Modules`, endpoint `Contoso.AppOps`, transcripts in `C:\ProgramData\JEAConfiguration\Transcripts`, ~60 MB of old demo log files |
| Job host (runs the scheduled task) | **CON-SRV02** | WS 2025 Datacenter Eval, **Desktop Experience** (Task Scheduler GUI) | 10.20.0.22 | `RSAT-AD-PowerShell`, gMSA installed, `C:\OpsJob`, task `\Contoso\OpsJob` |
| Helpdesk client | **CON-CLI01** | WS 2025 Datacenter Eval, Server Core | 10.20.0.41 | none (PowerShell 7 from episode 1; Windows PowerShell 5.1 works too) |
| Recording machine | Hyper-V host (Windows laptop) | — | 10.20.0.1 | elevated PowerShell for PowerShell Direct; VMConnect windows |

- Sign-in: the **lab Administrator** (`CONTOSO\Administrator`) for setup; **`CONTOSO\alex.demo`** for the helpdesk
  screens. The recorder types every password; none is written in a file or shown on screen.
- The **KDS root key** is forest-wide. `New-OpsJobIdentity.ps1 -CreateLabKdsRootKey` creates it with
  `-EffectiveTime` ten hours in the past, which Learn documents only for test environments with a single DC (our lab).
  It stays after tear-down: Learn warns that deleting and re-creating root keys causes caching problems, and later
  episodes can reuse it. If one already exists, the script skips this step.
- Nothing destructive happens to the shared VMs; registering the endpoint restarts WinRM on CON-SRV01 only.

Everything in `src/` and `tests/` already ran in the build container: 47 Pester tests, the lint on both definitions
(`sample/lint-lab.md`, `sample/lint-risky.md`) and an offline run of the runbook (`sample/ops-offline.jsonl`).
**Needs the lab (not run yet):** `Install-OpsEndpoint` against the real JEA cmdlets, the implicit-remoting connection
(`Connect-OpsTarget`), `Get-OpsHealth` on Server Core, both setup scripts, the scheduled task as the gMSA. Rewrite the
narration of the screen scenes to the real output.

## Prepare the lab (before recording)

From an elevated PowerShell on the laptop, in the repo root. PowerShell Direct needs no network credentials and keeps
working while WinRM restarts:

```powershell
$cred = Get-Credential 'CONTOSO\Administrator'                      # typed off camera
$ep   = '.\series\windows-server\episodes\05-powershell-automation'

# 1. Copy the episode to the three servers
foreach ($vm in 'CON-DC01', 'CON-SRV01', 'CON-SRV02') {
    $s = New-PSSession -VMName $vm -Credential $cred
    Copy-Item -ToSession $s -Path $ep -Destination 'C:\lab\ep05' -Recurse -Force
    Remove-PSSession $s
}

# 2. Identities on the DC: alex.demo (enabled, password typed now), groups, KDS key (lab form), gMSA
$alexPw = Read-Host -AsSecureString 'Password for alex.demo'
Invoke-Command -VMName CON-DC01 -Credential $cred -ArgumentList $alexPw {
    param($pw)
    if (-not (Get-ADUser -Filter "SamAccountName -eq 'alex.demo'")) {
        New-ADUser -Name 'Alex Demo' -SamAccountName alex.demo -UserPrincipalName alex.demo@lab.contoso.com -AccountPassword $pw -Enabled $true
    }
    & C:\lab\ep05\setup\New-OpsJobIdentity.ps1 -HelpdeskUser alex.demo -CreateLabKdsRootKey
}

# 3. App server: IIS + ~60 MB of IIS-style logs older than 14 days (the job's log budget is 50 MB)
Invoke-Command -VMName CON-SRV01 -Credential $cred {
    Install-WindowsFeature Web-Server | Out-Null
    $dir = 'C:\inetpub\logs\LogFiles\W3SVC1'
    New-Item -ItemType Directory $dir -Force | Out-Null
    1..30 | ForEach-Object {
        $f = Join-Path $dir ('u_ex2610{0:00}.log' -f $_)
        [IO.File]::WriteAllBytes($f, (New-Object byte[] (2MB)))
        (Get-Item $f).LastWriteTime = (Get-Date).AddDays(-20 - $_)
    }
}
```

The JEA install itself is screen 1. The job host setup is done before screen 3:

```powershell
Invoke-Command -VMName CON-SRV02 -Credential $cred { Set-Location C:\lab\ep05\setup; .\Register-OpsJobTask.ps1 }
```

`Register-OpsJobTask.ps1` installs RSAT-AD-PowerShell if needed, runs `Install-ADServiceAccount` and stops if
`Test-ADServiceAccount` isn't `True`. If it fails right after creating the gMSA, restart CON-SRV02 once (the computer
picks up its new rights at logon) and run it again; note in README if that was needed.

Terminals: `function prompt { 'PS> ' }`, large font, VMConnect windows maximised.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/register.jpg` — "The endpoint, registered"
On the laptop (elevated), PowerShell Direct into CON-SRV01 (Windows PowerShell 5.1 inside the VM):

```powershell
Invoke-Command -VMName CON-SRV01 -Credential $cred {
    Import-Module C:\lab\ep05\src\OpsLab\OpsLab.psd1
    $r = Install-OpsEndpoint -DefinitionPath C:\lab\ep05\src\jea-definition.json `
            -FunctionsModulePath C:\lab\ep05\src\ContosoOps\ContosoOps.psm1 -Confirm:$false
    $r.Steps; $r.Findings | Format-Table Severity, Check -AutoSize
    Get-PSSessionConfiguration -Name Contoso.AppOps | Format-List Name, PSVersion, Permission
}
```

Expect Steps `module transcripts registered`, one `Accepted VirtualAccountIsAdmin`, `PSVersion 5.1` and Permission
listing `CONTOSO\GG-AppOps-Readers` and `CONTOSO\GG-AppOps-Operators` with `AccessAllowed`. If `New-PSRoleCapabilityFile`
rejects a parameter shape, stop and note the exact error (only mocked in the container).

### 2. `screens/helpdesk.jpg` — "What helpdesk can do"
On CON-CLI01 (VMConnect, `pwsh`):

```powershell
Enter-PSSession -ComputerName CON-SRV01 -ConfigurationName Contoso.AppOps -Credential CONTOSO\alex.demo
Get-Command
Get-OpsHealth
Restart-Service W3SVC          # expected: not recognized (alex is a reader)
Exit-PSSession
```

Then on CON-SRV01 as Administrator (VMConnect, sconfig option 15):
`Get-PSSessionCapability -ConfigurationName Contoso.AppOps -Username CONTOSO\alex.demo`.
Capture Get-Command's short list (the eight RestrictedRemoteServer defaults plus `Get-Service`, `Get-OpsHealth`) and the
Restart-Service error. Two takes or a split screen are fine.

### 3. `screens/task.jpg` — "The job, running as the gMSA"
1. On CON-SRV01 (admin): `Stop-Service W3SVC` (WAS keeps running).
2. On CON-SRV02 (VMConnect, Desktop Experience): Task Scheduler → Task Scheduler Library → Contoso → OpsJob.
   General tab: "When running the task, use the following user account: CONTOSO\gmsa-opsjob$". Right-click → **Run**.
3. After ~1 minute, refresh: Last Run Result `The operation completed successfully. (0x0)`.
4. PowerShell on CON-SRV02: `Get-Content C:\OpsJob\logs\ops-*.jsonl -Tail 6` → `Health` (W3SVC=Stopped, LogFolderMB ~60),
   `Action RestartService W3SVC Succeeded`, `Action ClearLogs ... Succeeded` with "30 file(s), 60 MB freed", `RunEnd ExitCode 0`.

If the result is `0x1`, keep it: open the log, the reason is in the `Alert` / `Error` lines. Fix and re-run, and note
the cause in README "What we learned".

### 4. `screens/transcript.jpg` — "Who did it? The transcript knows"
On CON-SRV01 (VMConnect, sconfig option 15):

```powershell
$t = Get-ChildItem C:\ProgramData\JEAConfiguration\Transcripts -Recurse -File | Sort-Object LastWriteTime | Select-Object -Last 1
Get-Content $t.FullName | Select-String 'Username:|RunAs User:|Restart-Service|Clear-OpsLogFolder'
```

Show `Username: CONTOSO\gmsa-opsjob$`, `RunAs User: WinRM Virtual Users\WinRM VA_...`, and
`CommandInvocation(Restart-Service)` / `ParameterBinding(Restart-Service): name="Name"; value="W3SVC"`.

### 5. `screens/nolanguage.jpg` — "Gotcha: no variables in JEA"
On CON-CLI01 (`pwsh`):

```powershell
$cred = Get-Credential CONTOSO\alex.demo
Invoke-Command -ComputerName CON-SRV01 -ConfigurationName Contoso.AppOps -Credential $cred -ScriptBlock { $svc = 'W3SVC'; Get-Service -Name $svc }
Invoke-Command -ComputerName CON-SRV01 -ConfigurationName Contoso.AppOps -Credential $cred -ScriptBlock { Get-Service -Name W3SVC }
```

The first command fails because the session is in NoLanguage mode: capture the error text exactly as printed (it
hasn't been seen in this lab yet), and the second one working underneath.

Code scenes (definition, merge, install, decision, remoting, gmsa, tests) are rendered from `script.yaml`; the `merge`
and `tests` scenes show real output from the build container.

## Masking

- Lab names are fictional (`CON-*`, `lab.contoso.com`, `alex.demo`, `gmsa-opsjob`); keep them.
- VMConnect title bars show "<VM> on <host name>": crop them. Crop the laptop's taskbar and any window title that
  shows the Windows user name or the repo path on the laptop.
- Never show a password prompt being filled in; cut before `Get-Credential` dialogs appear or blur them.
- Run IDs (GUIDs) in the log are random and harmless.

## Tear-down

```powershell
Invoke-Command -VMName CON-SRV02 -Credential $cred { C:\lab\ep05\setup\Register-OpsJobTask.ps1 -Remove; Remove-Item C:\lab\ep05 -Recurse -Force }
Invoke-Command -VMName CON-SRV01 -Credential $cred {
    Unregister-PSSessionConfiguration -Name Contoso.AppOps -Force                 # restarts WinRM
    Remove-Item 'C:\Program Files\WindowsPowerShell\Modules\ContosoOps' -Recurse -Force
    Remove-Item C:\ProgramData\JEAConfiguration -Recurse -Force
    Remove-Item C:\inetpub\logs\LogFiles\W3SVC1\u_ex2610*.log -Force -ErrorAction SilentlyContinue
    Uninstall-WindowsFeature Web-Server | Out-Null
    Remove-Item C:\lab\ep05 -Recurse -Force
}
Invoke-Command -VMName CON-DC01 -Credential $cred {
    & C:\lab\ep05\setup\New-OpsJobIdentity.ps1 -Remove                           # gMSA + both groups (KDS root key stays)
    Remove-ADUser alex.demo -Confirm:$false
    Remove-Item C:\lab\ep05 -Recurse -Force
}
```

Restart CON-SRV01 if `Uninstall-WindowsFeature` asks for it. The shared VMs stay for the rest of the series.
