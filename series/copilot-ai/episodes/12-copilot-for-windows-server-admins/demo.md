# Demo shot list - Copilot & AI #12 Copilot for Windows Server Admins

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **One new throwaway VM, `CON-ARC01`**: Windows Server 2025 Datacenter Evaluation, Desktop Experience (the Azure Arc Setup wizard is a Desktop Experience feature; use the same evaluation media as the lab), 2 vCPU / 4 GB / 60 GB, `MGLab-NAT`, static **10.50.0.45**/24, gateway 10.50.0.1, DNS 10.50.0.10. 10.50.0.45 is not used in `series/LAB.md` or `series/LAB-REQUESTS.md` (checked 21 Nov 2026); the request line for LAB-REQUESTS.md is in the final report because this build may only write inside this folder. Not domain-joined (keeps the shared AD untouched). No shared VM (CON-DC01, CON-SRV01/02, CON-SQL01) receives any change from this episode |
| Recording machine | The Windows lab laptop: VS Code with the GitHub Copilot Chat extension, PowerShell 7.4 or later with Pester 5+ (`Install-Module Pester -Scope CurrentUser` if missing), a browser on the lab tenant for the Azure portal |
| Tenant / accounts | The Momento Galático lab tenant, `labadmin` (Owner of the Azure subscription) for the portal. Inside the VM: the VM's local Administrator, typed by the recorder off camera. Nothing is written in any file of this repo |
| GitHub account | The owner's GitHub account (same as the mg-lab repo), signed in inside VS Code. Confirm the plan at the recording. Prices checked on docs.github.com on 21 Nov 2026: Free 0 (limited), Pro 10 USD, Business 19 USD per seat, Enterprise 39 USD per seat per month. Re-check on the day |
| Azure | Resource group `rg-mglab-copilot-ai-12` (West Europe) holding only the Arc-enabled server resource for `CON-ARC01`. Azure Arc control plane: free per Learn. **Do not enable** Windows Server Management benefits (needs Software Assurance or pay-as-you-go) or Essential Machine Management (9.01 USD per server per month for servers without Software Assurance, per Learn on 21 Nov 2026), Defender, Update Manager or any extension. Azure Copilot: Learn says today's capabilities are free except the Observability agent (not used). Estimated cost for the recording window: **0 EUR** |
| Licences / purchases | Nothing bought. No Microsoft 365 Copilot licence. Windows Server evaluation edition: see open point 1 |
| Network | The VM needs outbound HTTPS to Azure (Arc endpoints, see Learn network requirements) and the laptop to GitHub and the portal |

## What was verified where

| Step | Verified in the build container (Linux, PowerShell 7.6, Pester 6.2) | Needs the lab |
|---|---|---|
| `AdminGate` module and `Invoke-AdminGate.ps1` (rules, modes, exit codes, JSON) | yes: 56 Pester tests, including real `Get-Command` lookups for built-in cmdlets | rerun on Windows: `Get-Service`, `Get-Volume` etc. resolve there, not on Linux |
| `Get-ServerHealth.ps1`: logic | yes: 11 Pester tests, fixture data and mocks for the pending-reboot flags | - |
| `Get-ServerHealth.ps1`: collectors (`Get-Volume`, `Get-Service`, `Get-HotFix`, CIM) | no (Windows-only commands) | **first real run on CON-ARC01** |
| `arc-servers.kql` | property names checked against Learn; the file was never executed | run in Azure Resource Graph Explorer |
| Everything Copilot says (Azure portal and VS Code) | no | **record it**, keep wrong answers |
| Arc onboarding of `CON-ARC01` | no | record it |

Open points to confirm at the first real run (each one changes the narration if different):
1. Whether a Windows Server **evaluation** edition can be connected to Azure Arc. Learn's prerequisites list supported operating
   systems; not checked for evaluation media. If it fails, say so on camera and use a licensed or Azure VM instead.
2. What Azure Copilot answers for one idle Arc server (and whether it asks for a resource ID: Learn says resource IDs are sometimes needed).
3. Whether `Get-ServerHealth.ps1` runs clean on Windows Server 2025 and what it reports on a fresh VM.
4. Whether the `-WhatIf` take behaves as scripted: a script **without** `[CmdletBinding(SupportsShouldProcess)]` must fail with
   "parameter cannot be found"; the same script with it must print "What if:" lines.
5. The gate's AG-H001/H002 results on Windows with the real modules (on Linux, Windows-only cmdlets show as "not found").

## Prerequisites
- Terminal: dark theme, 18 pt, 1600x900. VS Code dark theme, font 16 pt. Browser dark, 125 %.
- `cd src; pwsh -NoProfile -File Invoke-AdminGate.ps1 scripts/Get-ServerHealth.ps1` -> Clean, exit 0.
- `cd tests; Invoke-Pester` -> 67 passed (takes about a minute: the tests start `pwsh` and call `Get-Command`).

## Setup
1. Hyper-V (off camera): create `CON-ARC01` as above from the lab evaluation media; install updates; rename; set the static IP.
2. Azure (off camera): create resource group `rg-mglab-copilot-ai-12`; register the resource providers Azure Arc needs if the portal asks.
3. On the VM: sign in as the local Administrator (recorder types it). Run the **Azure Arc Setup** wizard from the Start menu
   (Windows Server 2025 includes it) and connect to the resource group above. Wait for status **Connected** in the portal.
4. Copy `src/copilot-config/copilot-instructions.md` to `.github/copilot-instructions.md` in a scratch repo opened in VS Code.
5. Clear old Copilot chats; start a new conversation per prompt.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `arc-onboard` | `screens/arc-onboard.jpg` | Portal > Azure Arc > Servers: `CON-ARC01`, Windows Server 2025, status Connected, resource group. Mask subscription ID and tenant name |
| `azure-copilot` | `screens/azure-copilot.jpg` | Copilot pane in the portal. Prompt 1: *List my Azure Arc-enabled servers and their agent status.* Prompt 2 (Learn's sample): *Help me troubleshoot my Arc server extension.* Capture the actual answers and any limits message. Optional take: *Write a Resource Graph query for Arc servers with their OS and agent version*, then compare with `src/azure/arc-servers.kql` |
| `vscode-script` | `screens/vscode-script.jpg` | VS Code Chat with the prompt from the script's `demo` field; Copilot's answer saved as `copilot-draft.ps1`; run the gate on it in the terminal and show the findings, whatever they are. Then run `src/scripts/Get-ServerHealth.ps1` on `CON-ARC01` and show its output |
| `whatif` | `screens/whatif.jpg` | On `CON-ARC01` only: a Copilot-written change for a harmless target (stop and start the Print Spooler), gate in Change mode, `-WhatIf` output; then a draft without SupportsShouldProcess failing on `-WhatIf` |
| terminal (code scene `gate`) | no screen file | `pwsh -File Invoke-AdminGate.ps1 samples/risky-examples.ps1.txt -Mode Change -SkipResolution` (hand-written sample, never run); then `scripts/Get-ServerHealth.ps1` (Clean) |

Masking: tenant domain, subscription ID, GitHub account name if personal. The VM is internal and fictional: no masking.

## Needs a licence the lab lacks (not recorded, mention only)
- **Windows Server management benefits through Arc** (Software Assurance or pay-as-you-go) and **Essential Machine Management**
  (9.01 USD per server per month without Software Assurance): not enabled; mentioned on the `arc` scene only.
- Any Copilot inside Windows Admin Center: none found on Learn on 21 Nov 2026, so nothing to demo.

## Tear-down
1. On the VM, in an elevated PowerShell: `azcmagent disconnect` (needs the lab credential; the recorder signs in).
2. Portal: delete the Arc server resource if it remains, then delete resource group `rg-mglab-copilot-ai-12`.
3. Hyper-V: stop and delete `CON-ARC01` and its VHDX. Remove the scratch repo and `copilot-draft.ps1`.
4. Sign out of GitHub in VS Code if the account is personal. Delete screenshots with real names; keep the masked JPEGs in `screens/`.
