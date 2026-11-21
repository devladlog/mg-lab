# Lab requests (extra VMs not in `lab/hyperv/lab.config.psd1`)

Requests from episode demo.md files. `lab.config.psd1` is not edited by episode builders: the lab owner decides
whether to add a VM there or create it by hand for the recording. IPs come from the free range 10.20.0.40–99
(CON-CLI01 already uses .41).

| VM name | OS / edition | Role | vCPU / RAM / disk | Network / IP | Episode | Lifetime |
|---|---|---|---|---|---|---|
| CON-FOREST01 | Windows Server 2025 Datacenter Evaluation, Server Core (same evaluation media/base image as the lab) | Throwaway server promoted to the first DC of a **new** forest (`lab.contoso.com` / `CONTOSO`) with `setup/New-LabForest.ps1`, for the "check first, then promote" screen. Not domain-joined before promotion; AD DS + DNS installed by the script | 2 / 2–3 GB dynamic / 60 GB (differencing disk is fine) | **Private** switch `MGLab-Isolated` only, never `MGLab-NAT`; static 10.20.0.90/24, no gateway, DNS 127.0.0.1 after promotion | windows-server #2 (`windows-server/episodes/02-active-directory-domain-services`) | Created right before the recording, deleted (VM, VHDX, Private switch) right after. Never the shared CON-DC01 |

Not VMs, but missing from `series/LAB.md` and needed by existing demo.md files:

| Item | Needed by | Notes |
|---|---|---|
| Azure DevOps organization connected to the lab tenant, private project `contoso-platform`, linked to the lab subscription for billing | azure #3 | Free tier; hosted parallelism needs the billing link |
| Power Automate Premium for `labadmin` (trial, if the process mining trial in `DEV` doesn't include premium connectors) | deep-dive #1, power-automate #4 | HTTP connector is premium |
| ~~Copilot Studio trial for `labadmin` and `sam.demo`~~ **done 21 Nov**: Copilot Studio viral trial licence assigned | deep-dive #2 | |
| Lab GitHub account | developer-tools #1 | public throwaway repo, created and deleted in the episode |
