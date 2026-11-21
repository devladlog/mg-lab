# DEVLADLOG Copilot & AI #12 - Copilot for Windows Server Admins

What Copilot really does for a Windows Server admin today, and the part most demos skip: who reviews the script before
it touches a server. We use **Azure Copilot** (questions about Azure VMs and **Azure Arc**-enabled servers) and
**GitHub Copilot** in VS Code (PowerShell), and add a tested PowerShell review gate and a read-only health script.

What we found on Microsoft Learn (21 Nov 2026), and what we left out on purpose:
- **No Copilot feature is documented for Windows Admin Center**; the episode does not pretend otherwise.
- **AI Shell** is archived ("as of January 2026 ... no longer actively maintained"); not used.
- Azure Copilot works for "querying and remediating across Azure VMs and Azure Arc-enabled servers" and can write Resource
  Graph queries and Azure PowerShell. Limits listed by Learn: conversations last 24 hours, actions on more than 10 resources
  happen outside Copilot, lists show the top five items, resource IDs are sometimes needed.
- Arc: Windows Server 2025 is supported, the control plane is free; the Windows Server management benefits need Software
  Assurance or pay-as-you-go (not enabled); Arc is not recommended for ephemeral servers; the Run command extension runs as
  Local System by default, is controlled by Azure RBAC and can be blocked with `azcmagent config set extensions.blocklist`.

Nothing here fakes Copilot output. The risky samples are hand-written and labelled so; the Copilot screens are recorded live
(see `demo.md`). Series plan: [`../../README.md`](../../README.md). Shared lab: [`../../../LAB.md`](../../../LAB.md).
Previous: [episode 11, Copilot for SQL](../11-copilot-for-sql-ssms-and-azure-sql/) (same idea: Copilot gets least privilege and a
review gate) and episode 10, *Azure Copilot and the Azure MCP Server*. Next: episode 13, GitHub Copilot in VS Code (agent mode and instructions).
Category episodes this builds on: [PowerShell automation](../../../windows-server/episodes/05-powershell-automation/),
[Windows Admin Center](../../../windows-server/episodes/06-windows-admin-center/),
[Windows Server security](../../../windows-server/episodes/08-windows-server-security/).

| Path | What it is |
|---|---|
| [`src/AdminGate/AdminGate.psm1`](src/AdminGate/AdminGate.psm1) | `Test-AdminScript`: parses PowerShell (never runs it), walks the syntax tree, modes `ReadOnly` / `Change` |
| [`src/Invoke-AdminGate.ps1`](src/Invoke-AdminGate.ps1) | Command line wrapper: text or `-Json`, exit code 0 clean / 1 warnings / 2 blocked |
| [`src/scripts/Get-ServerHealth.ps1`](src/scripts/Get-ServerHealth.ps1) | Read-only health check: disk free, automatic services, pending restart, uptime, last hotfix |
| [`src/copilot-config/copilot-instructions.md`](src/copilot-config/copilot-instructions.md) | House rules for `.github/copilot-instructions.md` |
| [`src/azure/arc-servers.kql`](src/azure/arc-servers.kql) | Resource Graph query for Arc servers (property names from Learn; not executed here) |
| [`src/samples/`](src/samples) | `safe-health-check.ps1` and `risky-examples.ps1.txt` (hand-written, never run; `.txt` on purpose) |
| [`tests/`](tests) | Pester: `AdminGate.Tests.ps1` (56) and `ServerHealth.Tests.ps1` (11) |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (14 scenes, about 775 words) and shot list |

## Gate rules
| Rule | Severity | Meaning |
|---|---|---|
| AG-X001 | block | does not parse |
| AG-M001 | block | state change in `ReadOnly` mode (unless a literal `-WhatIf`) |
| AG-D001 | block | `Invoke-Expression`/`iex`, `-EncodedCommand`, `Set-ExecutionPolicy Bypass/Unrestricted` |
| AG-D002 | block | destructive command (Format-Volume, Remove-AD*, Remove-Item -Recurse on a root, firewall profile off ...) unless a literal `-WhatIf` |
| AG-S001 | block | literal secret (`-AsPlainText`, password variable or parameter with a string literal) |
| AG-H002 | block | parameter that the resolved command does not have |
| AG-H001 | warn | command not found on this machine (typo, invented, or module missing) |
| AG-C001 | warn | state change with no `SupportsShouldProcess` in the enclosing function or script |
| AG-C002 | warn | `-Confirm:$false` or `-Force` on a change |
| AG-R001 | warn | a collection (AD, file of names, services) pipes into a change |
| AG-T001 | warn | empty `catch` |

Limits, by design: the gate is a text review, not a security boundary (Azure RBAC, JEA and your permissions are). It does not
follow variables or dot-sourced files, so `& $cmd` and splatted parameters are not checked. The change-verb list is ours, not Learn's.

## Run and test
```powershell
cd series/copilot-ai/episodes/12-copilot-for-windows-server-admins
pwsh -NoProfile -File src/Invoke-AdminGate.ps1 src/scripts/Get-ServerHealth.ps1 -SkipResolution   # Clean, exit 0
pwsh -NoProfile -File src/Invoke-AdminGate.ps1 src/samples/risky-examples.ps1.txt -Mode Change -SkipResolution   # Blocked, exit 2
cd tests; Invoke-Pester     # Pester 5 or later: 67 passed (Linux, PowerShell 7.6, Pester 6.2)
```
Without `-SkipResolution` the gate asks `Get-Command` about every command and parameter. On the Linux build machine
Windows-only cmdlets then show as not found (AG-H001); on a Windows Server they resolve.

## Sources (Microsoft Learn unless noted)
Azure Copilot overview and capabilities; "Get resource information with Azure Copilot" (Resource Graph); Azure Arc-enabled servers
overview, prerequisites and VM extension management; Azure Resource Graph starter samples (Arc property names); AI Shell overview
(archived notice); about_Preference_Variables and "Everything you wanted to know about ShouldProcess"; Microsoft.Windows/RebootPending
DSC resource (reasons for a pending restart) and the Windows Admin Center known-issues page (Component Based Servicing check);
VS Code custom instructions (code.visualstudio.com); GitHub Copilot plans (docs.github.com).

## Not verified
Arc onboarding of an evaluation edition, Azure Copilot answers on a real Arc server, the collectors on Windows, and everything
Copilot says in VS Code: see `demo.md`, "What was verified where". The Windows Update `RebootRequired` registry key is a common
convention, not a Learn-documented check; Learn documents the pending-restart reasons (Windows Update, component servicing,
pending file rename, computer rename, domain join) in the DSC `RebootPending` resource, which is marked proof of concept.
