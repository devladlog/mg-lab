# Lab requests (extra VMs not in `lab/hyperv/lab.config.psd1`)

Requests from episode demo.md files. `lab.config.psd1` is not edited by episode builders: the lab owner decides
whether to add a VM there or create it by hand for the recording. IPs come from the free range 10.50.0.40–99
(CON-CLI01 already uses .41).

| VM name | OS / edition | Role | vCPU / RAM / disk | Network / IP | Episode | Lifetime |
|---|---|---|---|---|---|---|
| CON-FOREST01 | Windows Server 2025 Datacenter Evaluation, Server Core (same evaluation media/base image as the lab) | Throwaway server promoted to the first DC of a **new** forest (`lab.contoso.com` / `CONTOSO`) with `setup/New-LabForest.ps1`, for the "check first, then promote" screen. Not domain-joined before promotion; AD DS + DNS installed by the script | 2 / 2–3 GB dynamic / 60 GB (differencing disk is fine) | **Private** switch `MGLab-Isolated` only, never `MGLab-NAT`; static 10.50.0.90/24, no gateway, DNS 127.0.0.1 after promotion | windows-server #2 (`windows-server/episodes/02-active-directory-domain-services`) | Created right before the recording, deleted (VM, VHDX, Private switch) right after. Never the shared CON-DC01 |
| CON-W11-01 | Windows 11 Enterprise **evaluation** (Microsoft Evaluation Center ISO), Hyper-V Generation 2 | Windows client for Intune: **Microsoft Entra joined** (not domain-joined) as the lab user `alex.demo`, auto-enrolled in Intune; shows compliance state, BitLocker with the virtual TPM, device sync | 2 / 4 GB static / 64 GB (dynamic VHDX) | `MGLab-NAT`, static 10.50.0.42/24, gateway 10.50.0.1, needs outbound HTTPS to the internet; vTPM + Secure Boot on | microsoft-365 #7 (`microsoft-365/episodes/07-intune-device-management`) | Created shortly before the recording (evaluation period is limited), deleted after together with its Intune and Entra device records |
| CON-HVT01 | **No operating system** (empty Hyper-V Generation 2 VM; no ISO, no licence) | Throwaway VM created and deleted by `Deploy-HvLab.ps1` on the laptop host, to show building a VM from a JSON spec, checkpoints, the differencing-disk chain and the cleanup/merge | 2 / 512 MB startup, dynamic 512-1024 MB / 20 GB dynamic VHDX; vTPM + Secure Boot on | No network adapter switch (`Switch` empty); no IP | windows-server #7 (`windows-server/episodes/07-hyper-v-virtualization`) | Created and removed in the same session by the script (the VM, its VHDX and its checkpoints; allow-listed name `CON-HVT01`, under the host's default paths). Nothing to provision beforehand |

Not VMs, but missing from `series/LAB.md` and needed by existing demo.md files:

| Item | Needed by | Notes |
|---|---|---|
| ~~Azure DevOps organization~~ existing org `devladlog` is used; **done 21 Nov**: billing linked, free hosted grant active | azure #3 | Free grant applies once billing is linked |
| Power Automate Premium for `labadmin` (trial, if the process mining trial in `DEV` doesn't include premium connectors) | deep-dive #1, power-automate #4 | HTTP connector is premium |
| ~~Copilot Studio trial for `labadmin` and `sam.demo`~~ **done 21 Nov**: Copilot Studio viral trial licence assigned | deep-dive #2 | |
| Microsoft 365 Copilot licence, **1 seat for `alex.demo`: OPTIONAL, owner's decision, not bought** | microsoft-365 #8 (only the optional "NEEDS COPILOT LICENCE" insert in `microsoft-365/episodes/08-microsoft-365-copilot-for-microsoft-365/demo.md`) | Episode 8 is built to be recorded **without** it. Microsoft's pricing page (en-us, read 21 Nov 2026): enterprise add-on 30.00 USD per user per month, paid yearly, annual subscription that auto-renews (Copilot Business 18.00 USD, Business licences only; marketing prices, real price at checkout). So one seat is an annual commitment of about 216 to 360 USD. Whether a trial tenant can buy it and the cancellation terms are not verified |
| Lab SharePoint site **MG Lab - Marketing** (owner `labadmin`) with fictional files, seeded sharing links, deleted after the recording | microsoft-365 #8 | Created and removed by the episode's own setup and tear-down steps; nothing to provision beforehand. Also needs the episode 5 sensitivity labels to exist (or the label screen reports their absence honestly) |
| ~~Lab GitHub account~~ decided: the same GitHub account as the mg-lab repo | developer-tools #1 | public throwaway repo, created and deleted in the episode |
