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

## Dev services
- Azure DevOps: existing organization `devladlog` (connected to the lab directory). Demos create their own private
  project and delete it afterwards. Microsoft-hosted pipelines need the org's billing linked to the lab Azure
  subscription (free grant: 1 job, 1,800 min/month); until then use a self-hosted agent on a lab VM.
- GitHub: the same account/organization used for github.com/devladlog/mg-lab. Throwaway demo repos are created and
  deleted inside the episode.

## Local Hyper-V lab (on the recording laptop, built by `lab/hyperv/Start-MGLab.ps1`)
Internal NAT network `10.20.0.0/24`, host = `10.20.0.1`, domain `lab.contoso.com` (NetBIOS `CONTOSO`).

| VM | OS | Role | IP | vCPU / RAM |
|----|----|------|----|-----------|
| CON-DC01 | Windows Server 2025 Datacenter Eval, Server Core | AD DS + DNS | 10.20.0.10 | 2 / 2–3 GB |
| CON-SRV01 | Windows Server 2025 Datacenter Eval, Server Core | member server | 10.20.0.21 | 2 / 1–2 GB |
| CON-SRV02 | Windows Server 2025 Datacenter Eval, Desktop Experience | member server (GUI tools) | 10.20.0.22 | 2 / 2–3 GB |
| CON-SQL01 | Windows Server 2025 Datacenter Eval, Server Core | SQL Server 2022 Developer, default instance, TCP 1433, mixed auth | 10.20.0.30 | 2 / 2–6 GB |
| CON-CLI01 | Windows Server 2025 Datacenter Eval, Server Core | test client (DHCP/DNS/GPO demos) | 10.20.0.41 | 1 / 1–1.5 GB |

- The recording laptop itself is Windows: Power BI Desktop, VS Code, SSMS, browsers and terminals run on the host and
  reach the VMs at the IPs above.
- More VMs can be added in `lab/hyperv/lab.config.psd1` (keep the laptop's RAM in mind: the four VMs above use up to
  ~14 GB). If an episode needs an extra VM, add a `## Lab environment` entry in demo.md with name, OS/edition,
  vCPU/RAM/disk, IP in 10.20.0.40–99, role, and software.
- An episode that records a destructive or "from zero" step (e.g. promoting a new forest) uses a throwaway VM, never
  the shared ones, and says so in demo.md.
- Credentials are never written in any file in the repo; demo.md says "lab Administrator" and the recorder signs in.
