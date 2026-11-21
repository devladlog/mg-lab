# Demo shot list - Copilot & AI #2 Microsoft Copilot Chat in a Real Tenant

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Tenant | The Momento Galático lab tenant: Microsoft 365 E5 trial (25 licences, until 20 Dec 2026). Auditing is on by default; check with `Get-AdminAuditLogConfig \| Format-List UnifiedAuditLogIngestionEnabled` in Exchange Online PowerShell (must be `True`) |
| Accounts | `alex.demo` (E5, **no Microsoft 365 Copilot add-on**) is the user in every Copilot screen; `sam.demo` optional second user for a few extra interactions; `labadmin` (Global Administrator) for the admin pages and the audit export. Global Administrators are automatically in the Exchange Online *Organization Management* role group, which holds the *Audit Logs* and *View-Only Audit Logs* roles (Learn) |
| Licences / purchases | **No Microsoft 365 Copilot licence, no pay-as-you-go billing policy, nothing bought.** Cost 0. The "Graph grounding" screen shows what an unlicensed user gets; showing the licensed behaviour would need one add-on seat (US$30 per user per month, paid yearly, en-US pricing page): the owner decides, it is not in this script |
| Azure | none |
| Recording machine | Windows lab laptop: browser on the lab tenant (alex.demo in a separate browser profile, labadmin in another), PowerShell 7 terminal, Python 3.10+, `Install-Module ExchangeOnlineManagement -Scope CurrentUser` |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the lab tenant |
|---|---|---|
| Parser, summary, CLI, licence split | yes: 18 pytest tests on a fictional export built from the schema in Learn | - |
| `Export-CopilotInteractions.ps1`: paging with one SessionId until an empty page, query parameters, CSV, error without a connection | yes: executed under `pwsh` with a stand-in `Search-UnifiedAuditLog` (test only); its CSV is parsed by the Python tool | **first real run** |
| `Search-UnifiedAuditLog` parameters (`-Operations`, `-SessionId`, `-SessionCommand ReturnLargeSet`, `-ResultSize` max 5,000) | against the cmdlet page on Learn | run on the tenant |
| Which AuditData properties a *Basic* (unlicensed) chat record really carries | **no**: Learn documents the schema, the build has no real record | **check on the first real export** |
| Everything the browser shows (Copilot Chat answers, admin pages) | no | **record it** |

Open points to confirm on the tenant, each changes the script if the answer is different:
1. Do conversations by an unlicensed user (Copilot Chat Basic) produce `CopilotInteraction` records? Learn lists the
   Copilot Chat hosts (BizChat, Bing, Edge...) in the audit schema, but not explicitly per licence. If there are none,
   the `audit-screen` scene and the narration about "Alex's conversations are in the log" must be rewritten.
2. Where `AppIdentity` sits in a real record (top level or inside `CopilotEventData`): the parser accepts both.
3. What Copilot Chat answers to "Summarise my last five emails" for an unlicensed user (see screen 3).

## Prerequisites
- Terminal: dark theme, 18 pt, window 1600x900, short prompt (`function prompt { 'PS> ' }`). Browser dark theme, 125 %.
- `python -m pip install -r src/requirements.txt`; `python -m pytest -q` -> `18 passed`.
- **Day before the recording** (audit records are not instant: Learn says availability for core services is typically
  60 to 90 minutes and may be longer for others, with no commitment): as `alex.demo`, do the three prompts of screens
  1 to 3 below, plus two or three other prompts; optionally one or two as `sam.demo`.
- Create `contoso-vendor-summary.docx`: open Word for the web as `alex.demo`, paste the text of
  `src/samples/contoso-vendor-summary.txt`, save. (Fictional vendors; total yearly cost 45,000 euros; first renewal
  Fabrikam Cloud on 31 March.)

## Setup
1. As `alex.demo` open `copilot.cloud.microsoft` and confirm the **Work** label and the green data protection shield.
   If Copilot Chat is blocked, fix it first (admin centre, Copilot, Settings) and note what you changed.
2. Run the three prompts (screens 1 to 3) a first time off camera and write down the answers, so the recording takes
   the same path.
3. As `labadmin` in PowerShell: `Connect-ExchangeOnline -UserPrincipalName <labadmin UPN>` (sign in on camera or off
   camera, never paste a password).

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `chat-web` | `screens/chat-web.jpg` | `copilot.cloud.microsoft` as `alex.demo`: Work label + shield; question "What is the difference between a Copilot Studio agent and a declarative agent?"; answer with citations and the section showing the web search queries. Mask tenant and email domain |
| `chat-upload` | `screens/chat-upload.jpg` | `contoso-vendor-summary.docx` attached; question "Which vendor renews first in the calendar year, and what is the total yearly cost?". Expected: Fabrikam Cloud, 31 March, 45,000 euros (18,400 + 4,200 + 9,900 + 12,500). Record whatever it answers; if it is wrong keep it and say so |
| `chat-graph` | `screens/chat-graph.jpg` | Same chat: "Summarise my last five emails". Capture the real answer. Learn: Basic cannot use Microsoft Graph. **If Copilot reads the mailbox, stop and rewrite the scene and the `what` slide before publishing** |
| `policy-screen` | `screens/web-search-policy.jpg` | `config.office.com` as `labadmin`, Microsoft 365 Cloud Policy: the setting *Allow web search in Copilot* open, three options visible (unsaved). Optional extra capture: Microsoft 365 admin center, **Copilot > Settings > Pin Microsoft Copilot Chat** (AI Administrator role is the documented minimum; Global Administrator works). Change nothing |
| `audit-screen` | `screens/audit-summary.jpg` | Terminal: `./src/scripts/Export-CopilotInteractions.ps1 -StartDate (Get-Date).AddDays(-2) -OutFile $HOME/copilot-interactions.csv` then `cd src; python -m copilot_chat_audit $HOME/copilot-interactions.csv`. Visible: interaction count, web search share above 0 %, app-host lines, Alex Demo. Mask the tenant domain (pipe through `-replace`, or crop) |

Optional extra take (not in the script): Microsoft Purview portal, **Audit**, search for activity *Interacted with Copilot*
(Learn: *Copilot activities*) to show the same records in the UI.

## Masking notes
- Tenant name, `*.onmicrosoft.com`, tenant ID, organisation ID in AuditData, client IPs: never on screen. The CSV
  contains `OrganizationId`, `ClientIP` and the real UPNs: keep it in `$HOME`, never in the repo, and show only the
  summary output.
- Lab users appear only as "Alex Demo", "Sam Demo", "Lab Admin".

## Tear-down
1. Delete `$HOME/copilot-interactions.csv` and `contoso-vendor-summary.docx` (Alex's OneDrive).
2. Delete the demo conversations in the Copilot app history for `alex.demo` (and `sam.demo`).
3. `Disconnect-ExchangeOnline -Confirm:$false`.
4. Revert anything changed in Copilot settings or Cloud Policy (the script changes nothing by design).
