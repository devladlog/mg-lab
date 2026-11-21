# Shared demo lab (read before writing demo.md)

All demos are recorded for real. Use these shared resources before asking for new ones.

## Cloud tenant (Momento Galático lab tenant)
- Microsoft 365 E5 trial (25 licences, until 20 Dec 2026): includes Entra ID P2, Purview, Defender, Teams, SharePoint.
  Not included: SharePoint Advanced Management (needs a Microsoft 365 Copilot licence in the org or the SAM add-on).
- Entra ID Governance add-on trial (until 20 Dec 2026): lifecycle workflows, entitlement management, access reviews.
- Power Automate process mining 90-day trial in `DEV` (started 21 Nov 2026, until ~19 Feb 2027).
- Power Apps Premium, Microsoft 365 Business Standard, Fabric + Power BI 60-day trial (West Europe capacity).
- Lab users (fictional, all with E5 + Entra ID Governance + Dynamics 365 Sales trial licences, location Portugal):
  `labadmin` (Lab Admin, the recording account), `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo`
  (display names "<First> Demo"). `labadmin` and `sam.demo` also have the Copilot Studio trial licence. Departments, managers, groups and roles are not set yet: each demo.md says what it
  needs and sets it up in its own steps (and undoes it in tear-down). The owner's own account is never used in demos.
  Premium Power Platform: there are no spare Power Apps Premium licences. A demo user who needs premium connectors
  starts the self-service Power Apps / Power Automate Premium trial the first time (say so in demo.md), or the app
  runs in `DEV` under the environment's pay-as-you-go plan if one is set (not set today).
- Power Platform environment `DEV` (Dataverse). Developer environments can no longer be created; plan for `DEV`
  or a sandbox environment.
- Dynamics 365 Sales trial environment "Sales trial" (EMEA, created 21 Nov 2026, 30-day trial): Sales Hub app with
  sample data. Use it for Dynamics 365 app demos (Sales, leads/opportunities, BPFs on sales entities); Dataverse-only
  demos can use `DEV`. Mask the org URL in every capture.
- Azure subscription: one pay-as-you-go subscription in the lab tenant (Owner). Every demo deploys into its own
  resource group `rg-mglab-<series>-<ep>` (West Europe, or Sweden Central for Azure OpenAI), lists each resource with SKU
  and estimated cost for the recording window, and deletes the resource group in tear-down. Prefer free tiers. A €30/month budget
  ("mglab-monthly") emails alerts at 50%, 80%, 100% and forecast 100%.

- AI credits: AI Builder trials are discontinued and seeded credits ended 1 Nov 2026. Running AI prompts in an app
  or flow needs Copilot Credits via a pay-as-you-go plan (not set; needs the owner, and a production/sandbox
  environment, not a Developer one). Testing inside the prompt builder is free.
- Copilot in Fabric/Power BI: per Learn, the Fabric trial capacity does not support Copilot; a paid F2+ (or P1) capacity
  is needed for those screens (owner's decision, cost stated in the episode).
- Teams: the Workflows app is already allowed for everyone (Teams admin center, checked 21 Nov 2026).

## Dev services
- Azure DevOps: existing organization `devladlog` (connected to the lab directory). Demos create their own private
  project and delete it afterwards. Billing is linked to the lab Azure subscription, so the free Microsoft-hosted grant
  is active (1 parallel job, up to 60 min per run, 1,800 min/month). No paid parallel jobs.
- GitHub: the same account/organization used for github.com/devladlog/mg-lab. Throwaway demo repos are created and
  deleted inside the episode.

## Local Hyper-V lab (on the recording laptop, built by `lab/hyperv/Start-MGLab.ps1`)
**Built and running since 21 Nov 2026** on `E:\MGLab` (laptop: Core Ultra 9, 24 threads, 191 GB RAM, so RAM is not a
constraint). Lab users' passwords are set and `labadmin` is Global Administrator.
Internal NAT network `10.50.0.0/24`, host = `10.50.0.1`, domain `lab.contoso.com` (NetBIOS `CONTOSO`).

| VM | OS | Role | IP | vCPU / RAM |
|----|----|------|----|-----------|
| CON-DC01 | Windows Server 2025 Datacenter Eval, Server Core | AD DS + DNS | 10.50.0.10 | 2 / 2–3 GB |
| CON-SRV01 | Windows Server 2025 Datacenter Eval, Server Core | member server | 10.50.0.21 | 2 / 1–2 GB |
| CON-SRV02 | Windows Server 2025 Datacenter Eval, Desktop Experience | member server (GUI tools) | 10.50.0.22 | 2 / 2–3 GB |
| CON-SQL01 | Windows Server 2025 Datacenter Eval, Server Core | SQL Server 2022 Developer, default instance, TCP 1433, mixed auth | 10.50.0.30 | 2 / 2–6 GB |
| CON-CLI01 | Windows Server 2025 Datacenter Eval, Server Core | test client (DHCP/DNS/GPO demos) | 10.50.0.41 | 1 / 1–1.5 GB |
| CON-SQL02 | Windows Server 2025 Datacenter Eval, Server Core | SQL Server 2022 Developer, Always On AG secondary (SQL ep 10) | 10.50.0.42 | 2 / 2–6 GB |
| CON-W11-01 | Windows 11 Enterprise Eval (90 days), vTPM | Intune/Entra-joined client; stops at Windows setup for an on-camera Entra join. Needs the ISO saved as `E:\MGLab\iso\Win11Ent-Eval.iso` | DHCP on Hyper-V `Default Switch` (not on the lab network) | 2 / 4 GB |

- The recording laptop itself is Windows: Power BI Desktop, VS Code, SSMS, browsers and terminals run on the host and
  reach the VMs at the IPs above.
- More VMs can be added in `lab/hyperv/lab.config.psd1` (keep the laptop's RAM in mind: the four VMs above use up to
  ~14 GB). If an episode needs an extra VM, add a `## Lab environment` entry in demo.md with name, OS/edition,
  vCPU/RAM/disk, IP in 10.50.0.40–99, role, and software.
- An episode that records a destructive or "from zero" step (e.g. promoting a new forest) uses a throwaway VM, never
  the shared ones, and says so in demo.md.
- Credentials are never written in any file in the repo; demo.md says "lab Administrator" and the recorder signs in.

## Recording laptop toolchain (checked on the laptop, 21 Nov 2026)

`series/tools/Get-WindowsToolchain.ps1` writes the full list to `verify-results/toolchain.txt`. What episodes can rely on:

| Tool | On the laptop | Notes for episodes |
|---|---|---|
| .NET SDK | 10.0.301 / 10.0.303, runtime 10 only | **No .NET 8 runtime** (.NET 8 support ended 10 Nov 2026). All projects target net10.0 except `net/10-net-8-9-features`, which needs the .NET 8 runtime installed for that recording only. No MAUI workload (`net/12` needs `dotnet workload install maui`). The newer SDK enforces IDE0005 (unused `using`) at build. |
| PowerShell | Windows PowerShell 5.1 (Pester 3.4 only) and PowerShell 7.6 | Tests need Pester 5+: the verification run loads a repo-local copy from `.tools\Modules` (not installed system-wide). Same for PSScriptAnalyzer. |
| Bicep | not on PATH; Azure CLI 2.87 has its managed copy in `%USERPROFILE%\.azure\bin` | Add that folder to PATH (or `winget install Microsoft.Bicep`) before running template tests by hand. |
| Python / Node | Python 3.10.11 (`python`, not `python3`: that name is the Microsoft Store stub), Node 24.16, npm 11 | Scripts must not assume `python3` on Windows. |
| Git | 2.54, with Git Bash (`C:\Program Files\Git\bin\bash.exe`) | `bash` on PATH is the WSL launcher; use Git Bash for shell checks. No `openssl` on PATH. |
| Power Platform CLI | pac 2.15.1 | |
| Docker | **not installed** | Business Central container (`dynamics-365/12`) and any `docker compose` demo need Docker Desktop (Windows containers for BC). |
| Visual Studio | Visual Studio Professional **2022** | `developer-tools/12` is written for VS 2026; `copilot-ai/16` needs VS 2026 or 2022 17.14.17+. |
| VS Code | with C# Dev Kit, PowerShell, Python, Bicep, Docker, Power Platform, Claude Code and Continue extensions | |
| AI locally | Ollama 0.40, LM Studio CLI, NVIDIA RTX 5090 Laptop GPU (24 GB) | `copilot-ai/23` |

Windows verification of every episode's .NET and Pester suites: `series/tools/Invoke-WindowsVerification.ps1` (VS Code task "MG 2"). Results in `verify-results/summary.md`; a `verify-results/rerun-failed.flag` file makes the next run repeat only the failed (or listed) episodes.
