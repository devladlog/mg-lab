# Demo shot list — DEVLADLOG Windows Server #6: Windows Admin Center

## Lab environment

All screens are recorded on the **shared local Hyper-V lab** (`series/LAB.md`): domain `lab.contoso.com`, NetBIOS
`CONTOSO`, network `10.20.0.0/24`. No extra VM, no tenant, no Azure. Windows Admin Center has no additional cost beyond
Windows (Learn FAQ); the VMs are evaluation editions. Cost 0.

### Where Windows Admin Center goes: CON-SRV02, as a gateway

| Option | Verdict | Why |
|---|---|---|
| **CON-SRV02** (WS 2025 Desktop Experience, domain member) | **Chosen** | Windows Server 2025 is a supported *gateway server* topology; domain-joined, so AD groups control gateway access and Kerberos (RBCD) gives single sign-on to the nodes; Desktop Experience has a browser, so the whole demo is recorded inside the lab and nothing changes on the laptop; it's the production pattern (one shared gateway) |
| CON-DC01 | No | Learn: installing Windows Admin Center on a domain controller isn't supported |
| The Windows recording laptop | No | Not domain-joined: Windows 11 is only a *local client* topology, no group-based access in workgroups (Learn), and we'd have to change the owner's laptop (TrustedHosts, credentials) to reach the VMs |
| CON-SRV01 / CON-SQL01 / CON-CLI01 | No | Server Core (no local browser); CON-SRV01 is the RBAC target, CON-SQL01 is often off to save RAM |

### VMs used

| Role in the episode | Shared VM | OS / edition | IP | vCPU / RAM | Changes for the recording (undone in tear-down) |
|---|---|---|---|---|---|
| **Gateway** | **CON-SRV02** | WS 2025 Datacenter Eval, Desktop Experience | 10.20.0.22 | 2 / **raise max to 4 GB** (from 3) | Windows Admin Center (Administration Mode, port 443, self-signed certificate), `RSAT-AD-PowerShell`, episode folder in `C:\lab\ep06` |
| Node, RBAC target | CON-SRV01 | WS 2025 Datacenter Eval, Server Core | 10.20.0.21 | 2 / 1–2 GB | RBAC applied from the UI (JEA endpoint `Microsoft.Sme.PowerShell`, `Microsoft.Sme*` modules, 3 local groups), `alex.demo` in *Windows Admin Center Readers*, RBCD from the gateway |
| Node | CON-DC01 | WS 2025 Datacenter Eval, Server Core | 10.20.0.10 | 2 / 2–3 GB | user `alex.demo` (enabled; password typed by the recorder); no delegation on the DC |
| Node | CON-CLI01 | WS 2025 Datacenter Eval, Server Core | 10.20.0.41 | 1 / 1–1.5 GB | RBCD from the gateway |
| Node (optional) | CON-SQL01 | WS 2025 Datacenter Eval, Server Core | 10.20.0.30 | 2 / 2–6 GB | none; may stay off (the preflight reports it as Info, `Optional: true`) |

- Memory while recording: CON-DC01 + CON-SRV01 + CON-SRV02 (4 GB) + CON-CLI01 ≈ 10.5 GB; leave CON-SQL01 off.
- Software: the Windows Admin Center installer (`WindowsAdminCenter.exe`) from the
  [Windows Admin Center Evaluation Center](https://www.microsoft.com/evalcenter/download-windows-admin-center) (or
  `https://aka.ms/WACdownload`, as in Learn's command-line install). Microsoft Edge in-box on Desktop Experience.
- Sign-in: **lab Administrator** (`CONTOSO\Administrator`, local admin on the gateway = gateway administrator) for the
  setup and the admin screens; **`CONTOSO\alex.demo`** via *Manage as* for the reader screen. Passwords and the
  Windows Admin Center **access key** are typed off camera and never written in a file.
- Recording machine: the Hyper-V laptop, VMConnect windows of CON-SRV02 (PowerShell + Edge) and CON-SRV01 (console).

Everything in `src/` and `tests/` already ran in the build container: 41 Pester tests, the preflight on two fact
fixtures (`sample/preflight-con-srv02.md`, `sample/preflight-bad.md`) and the generated `sample/connections.csv`.
**Needs the lab (not run yet):** the collector on CON-SRV02, the silent install, `Import-WACConnection` (module path
and parameters), `Set-ADComputer` delegation, the RBAC collector and *Manage as* with a reader. Rewrite the narration of
the screen scenes to the real output.

## Prepare the lab (before recording)

On the laptop, elevated PowerShell, repo root:

```powershell
$cred = Get-Credential 'CONTOSO\Administrator'                     # typed off camera
# CON-SRV02: more memory for the gateway + Edge (shut down first if Hyper-V refuses to change it while running)
Set-VMMemory -VMName CON-SRV02 -MaximumBytes 4GB
Stop-VM CON-SQL01 -ErrorAction SilentlyContinue                    # optional node, saves RAM

# Episode folder + installer on the gateway (download the installer on the laptop first)
$s = New-PSSession -VMName CON-SRV02 -Credential $cred
Copy-Item -ToSession $s -Path .\series\windows-server\episodes\06-windows-admin-center -Destination C:\lab\ep06 -Recurse -Force
Copy-Item -ToSession $s -Path $HOME\Downloads\WindowsAdminCenter.exe -Destination C:\lab\WindowsAdminCenter.exe
Invoke-Command -Session $s { Install-WindowsFeature RSAT-AD-PowerShell | Out-Null }
Remove-PSSession $s

# alex.demo (helpdesk), enabled, password typed now
$pw = Read-Host -AsSecureString 'Password for alex.demo'
Invoke-Command -VMName CON-DC01 -Credential $cred -ArgumentList $pw {
    param($p)
    if (-not (Get-ADUser -Filter "SamAccountName -eq 'alex.demo'")) {
        New-ADUser -Name 'Alex Demo' -SamAccountName alex.demo -UserPrincipalName alex.demo@lab.contoso.com -AccountPassword $p -Enabled $true
    }
}
```

On CON-SRV02 sign in at the console as the lab Administrator; open **Windows PowerShell (Admin)**, `cd C:\lab\ep06\src`,
`function prompt { 'PS> ' }`, large font. Keep Edge ready.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/installed.jpg` — "Preflight, install, sign in"
In the PowerShell window on CON-SRV02:

```powershell
.\Invoke-WacPreflight.ps1 -FactsFile .\gateway-facts.json -OutFile .\preflight.md
.\Deploy-WacLab.ps1 -Step Install -InstallerPath C:\lab\WindowsAdminCenter.exe
```

Expect 0 High (CON-SQL01 Info if off, SelfSignedCertificate Info) and `Url : https://con-srv02.lab.contoso.com`.
Then Edge → `https://con-srv02.lab.contoso.com`, sign in as the lab Administrator → **All connections**.
Capture PowerShell (left) and Edge (right). If Edge warns about the certificate (self-signed, 60 days), continue for the
lab and don't show the warning page. Note the installed version (Settings → About) in README.

### 2. `screens/imported.jpg` — "Shared connections, tagged"
In Edge: Settings → Advanced → copy the **access key** (off camera). In PowerShell:

```powershell
.\Deploy-WacLab.ps1 -Step Connections -AccessKey (Read-Host -AsSecureString 'Access key') -Credential (Get-Credential CONTOSO\Administrator)
```

Refresh **All connections**: five `con-*.lab.contoso.com` entries with tags. Filter by tag `core` → four entries.
If `Import-WACConnection` rejects a parameter or the module isn't found, capture the error, note it in README and add
the connections once with *Add → Import a list* (the PowerShell CSV isn't compatible with that UI import, per Learn:
use a plain list of names there).

**Optional B-roll (not in the script): single sign-on.** Before running the next command, connect to con-srv01 and
note whether Windows Admin Center asks for credentials. Then run `.\Deploy-WacLab.ps1 -Step Sso` (output: CON-SRV01,
CON-CLI01 `Add / Done`, CON-SQL01 too if in AD; CON-DC01 is not touched) and connect again. Record both only if the
difference is visible; if Kerberos tickets are cached, restart the `WindowsAdminCenter` service on CON-SRV02 and retry.

### 3. `screens/rbac-endpoint.jpg` — "The endpoint behind the button"
1. Edge: connect to con-srv01 → **Settings → Role-based access control → Apply**. It can take up to 10 minutes and
   restarts WinRM on CON-SRV01 (Learn). Refresh until the status is **Applied**; capture that page.
2. PowerShell on CON-SRV02: `.\Deploy-WacLab.ps1 -Step Rbac` → adds `CONTOSO\alex.demo` to *Windows Admin Center
   Readers* on CON-SRV01 and prints "RBAC matches wac-lab.json." (or the remaining findings).
3. CON-SRV01 console (VMConnect, sconfig option 15):

```powershell
Get-PSSessionConfiguration -Name Microsoft.Sme.PowerShell | Format-List Name, PSVersion, Permission
Get-LocalGroup 'Windows Admin Center*'
Get-PSSessionCapability -ConfigurationName Microsoft.Sme.PowerShell -Username CONTOSO\alex.demo | Measure-Object
```

Capture the endpoint, the three groups and the command count.

### 4. `screens/readers.jpg` — "Alex can look, not touch"
Edge, All connections → select con-srv01 → **Manage as** → `CONTOSO\alex.demo` (password off camera) → connect.
Capture: the limited-access indication (whatever the UI shows), Overview, **Services** listing services, and the tool
list without PowerShell and Remote Desktop. If Services offers Restart, try it on Spooler and capture the result.
If *Manage as* doesn't give the reader experience (for example it is refused), capture the message, note it in README
and record the screen by signing in to the gateway as alex.demo instead.

### 5. `screens/showscript.jpg` — "Every click is PowerShell"
As the lab Administrator, connected to con-srv01 → **Services** → PowerShell icon on the application bar → choose a
command in the dropdown → the script is shown. Zoom on it.

Code scenes (preflight, install, connections, delegation, tests) are rendered from `script.yaml`; `connections` and
`tests` show real output from the build container.

## Masking

- Lab names are fictional (`CON-*`, `lab.contoso.com`, `alex.demo`); keep them.
- **Never show the access key** (Settings → Advanced) or any credential dialog being filled in.
- Windows Admin Center may show the signed-in account in the header: it's the lab Administrator (fine). Crop
  VMConnect title bars ("<VM> on <host name>") and the laptop taskbar.
- If Settings → Azure or any update banner shows account or tenant details, keep it off screen (nothing is registered
  with Azure in this episode).

## Tear-down

On CON-SRV02 (PowerShell, `C:\lab\ep06\src`):

```powershell
.\Deploy-WacLab.ps1 -Step Sso -Remove            # removes only the gateway from each node's delegation list
```

On CON-SRV01 (console or PowerShell Direct from the laptop), undo what *Apply* created (the list on Learn):

```powershell
Unregister-PSSessionConfiguration -Name Microsoft.Sme.PowerShell -Force          # restarts WinRM
'Windows Admin Center Administrators', 'Windows Admin Center Hyper-V Administrators', 'Windows Admin Center Readers' |
    ForEach-Object { Remove-LocalGroup -Name $_ -ErrorAction SilentlyContinue }
Get-ChildItem 'C:\Program Files\WindowsPowerShell\Modules' -Directory -Filter 'Microsoft.Sme*' | Remove-Item -Recurse -Force
```

On CON-SRV02: uninstall **Windows Admin Center** from Settings → Apps → Installed apps, then
`Uninstall-WindowsFeature RSAT-AD-PowerShell` (keep it if episode 5's job host is still in use) and
`Remove-Item C:\lab -Recurse -Force`. On the laptop: `Set-VMMemory -VMName CON-SRV02 -MaximumBytes 3GB` (VM off if
needed) and on CON-DC01 `Remove-ADUser alex.demo -Confirm:$false`.
