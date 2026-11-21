# Demo shot list - Copilot & AI #19 Copilot Governance: Purview DSPM for AI and Admin Controls

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Tenant | Momento Galático lab tenant: Microsoft 365 E5 trial (until 20 Dec 2026: Purview, SharePoint, Entra ID P2). Auditing on by default |
| Accounts | `labadmin` (Global Administrator) for Purview, SharePoint admin and the scripts; `alex.demo` (E5, **no Copilot add-on**) for the Copilot Chat prompt screen; `sam.demo` optional |
| Licences / purchases | **No Microsoft 365 Copilot licence, no SharePoint Advanced Management add-on, no pay-as-you-go billing.** Cost 0. Screens that need them are listed below as NEEDS COPILOT LICENCE: Microsoft pricing page (en-us, read 21 Nov 2026 in `series/LAB-REQUESTS.md`): 30.00 USD per user per month, paid yearly (enterprise add-on); owner's decision, not in the script |
| Azure | none |
| Sites (created by the setup below) | Two throwaway SharePoint team sites, `MG Lab - HR Salaries` (deliberately overshared, fictional files) and `MG Lab - Marketing`; one sensitivity label `Highly Confidential` (created by the episode 5 / Purview setup, or created here if missing). Deleted in tear-down |
| Recording machine | Windows lab laptop: browser profiles for `labadmin` and `alex.demo`; PowerShell 7 terminal with `ExchangeOnlineManagement` and `Microsoft.Online.SharePoint.PowerShell` installed (`Install-Module ... -Scope CurrentUser`); Python 3.10+ |

## What was verified where

| Step | Build container (Linux) | Needs the lab tenant |
|---|---|---|
| Checks G01-G08, CLI, exit codes, link classification | yes: pytest on fictional snapshots built from documented property names | - |
| `Export-CopilotGovernanceSnapshot.ps1` flow (sections, per-site reads, error capture) | yes, under `pwsh` with stand-in cmdlets | **first real run**: real property shapes of `Get-DlpCompliancePolicy`, `Get-Label`, `Get-SPOSite` |
| `New-CopilotLabelDlpPolicy.ps1` (dry run, parameters passed to the cmdlets, label GUID resolution) | yes, stand-in cmdlets | **first real create** in simulation mode; whether the policy appears in the portal exactly as shown |
| `graph_scan.py` paging, retry, bearer header | yes, against a loopback server | real Graph call; which token and consent (Files.Read.All or Sites.Read.All) |
| All Purview, SharePoint and Copilot Chat screens | no | **record them** |

Open points that change the script if the answer differs: (1) does `Get-DlpCompliancePolicy` expose `EnforcementPlanes` and
`Locations` so G03 recognises the policy (if not, fix `is_copilot_dlp_policy`); (2) is the prompt-block preview in the tenant;
(3) does the default data risk assessment have results (first results 4 days after creation: see setup step 1).

## Prerequisites and setup (do these days before)
1. **At least 5 days before recording**, as `labadmin` open `purview.microsoft.com`, Solutions, **DSPM** (not the classic entries)
   and accept the initial setup tasks if asked. Learn: allow a day before data shows; the default data risk assessment has
   a 4 day delay the first time. Without activity on the sites the assessment may be empty: do step 2 first.
2. Create the two sites (SharePoint admin center or `labadmin` in the browser): `MG Lab - HR Salaries` (Microsoft 365 group,
   public) and `MG Lab - Marketing` (private). In HR Salaries upload fictional files `salary-bands-2026.xlsx` (10 rows of
   invented bands) and `holiday-calendar.docx`; create one **Anyone** link on `salary-bands-2026.xlsx` and one
   **People in your organization** link on both files. Anyone links need tenant sharing set to Anyone: note the current value
   (`Get-SPOTenant | Select SharingCapability`), change it only if needed and restore it in tear-down. Open the files as
   `alex.demo` and `sam.demo` a few times so the sites count as "used".
3. Labels: Purview, Information Protection, confirm a label named `Highly Confidential` exists and is published; if not,
   create it (no encryption needed) and a label policy for all users. Note it in tear-down.
4. Terminal: dark theme, 18 pt, 1600x900. `python -m pip install -r src/requirements.txt`; `python -m pytest -q` -> `15 passed`.
5. Sign in on camera or off camera for `Connect-ExchangeOnline`, `Connect-IPPSSession`, `Connect-SPOService -Url https://<tenant>-admin.sharepoint.com`. Never paste a password.
6. **Day before:** run the snapshot once off camera (`before.json`), read G03 and the warnings, and keep it as the safety take.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `dspm-posture` | `screens/dspm-posture.jpg` | Purview, Solutions, **DSPM**: Posture page, then Objectives (cards *Prevent oversharing of sensitive data*, *Prevent data exposure in Microsoft 365 Copilot and Microsoft Copilot interactions*) and Setup tasks. Real state; Copilot interaction numbers will be empty (no Copilot licence): say so. Mask tenant name |
| `assessment` | `screens/risk-assessment.jpg` | DSPM, Discover, **Data risk assessments**, Microsoft 365 tab: default assessment summary and a site flyout (Overview, Identify, Protect, Monitor). If the default assessment has no results yet, create a **custom assessment** for the two lab sites and wait at least 48 hours (Learn); results do not refresh, create a new one for changes. Item-level scan is optional and needs an Entra app: skip it |
| `check-screen` | `screens/posture-before.jpg` | Terminal: `./src/scripts/Export-CopilotGovernanceSnapshot.ps1 -OutFile before.json` then `cd src; python -m copilot_governance ../before.json`. Expect G03 FAIL (no Copilot DLP policy) and WARN lines for G05/G06/G07. Record what the tenant really returns; any `????` (not collected) line is real and is explained on camera. Add `--sharing scan.json` only if the Graph scan worked (see below) |
| `dlp-screen` | `screens/dlp-policy.jpg` | Terminal: `./src/scripts/New-CopilotLabelDlpPolicy.ps1 -LabelName 'Highly Confidential'` (dry run JSON), then `... -Apply`. Browser: Purview, Data Loss Prevention, Policies: `MG Lab - Copilot: block labelled content`, location *Microsoft Copilot, Copilot Chat, and Copilot Cowork*, mode simulation. Then re-run the snapshot and the checker: G03 passes, G04 warns (simulation) |
| `prompt-block` | `screens/prompt-block.jpg` | **Conditional.** Only if the preview "block sensitive information types in prompts" is available (Learn: rolling out; check by adding the rule in the portal). Add a rule: Content contains, Sensitive information types, Credit Card Number; action *Prevent Copilot from processing content*, *Processing prompts*; set the policy to Enable; wait up to four hours. As `alex.demo` in `copilot.cloud.microsoft` send a prompt containing the public test number `4111 1111 1111 1111`. Capture the real result. If nothing is blocked, **delete the scene and the narration about it** |

Optional graph scan (for the item-level link list, not a screen): get a Microsoft Graph token for `labadmin` yourself off camera
(for example from Graph Explorer or `az account get-access-token --resource https://graph.microsoft.com`: not verified to carry
Files.Read.All/Sites.Read.All; if the call returns 403, drop it), `$env:GRAPH_TOKEN='...'`, `python -m copilot_governance.graph_scan --query "MG Lab" --out scan.json`.
Expected: the `salary-bands-2026.xlsx` item flagged high. The token is never shown on screen or saved.

### NEEDS COPILOT LICENCE (optional inserts, not in the script)
- SharePoint admin center, Sites, Active sites, a site's Settings: *Restrict content from Microsoft Copilot* (Restricted Content Discovery) and
  `Set-SPOSite -RestrictContentOrgWideSearch $true`. Learn prerequisites: a Microsoft Copilot licence and SharePoint Advanced Management.
- SharePoint admin center, Reports, Data access governance: *Sites and files shared via special SharePoint groups* (EEEU/Everyone item-level).
- DSPM and the label-based Copilot DLP on a licensed user: ask the owner about one seat for `alex.demo` (annual commitment; owner's decision).

## Tear-down
1. Purview, Data Loss Prevention: delete `MG Lab - Copilot: block labelled content` (portal, or `Remove-DlpCompliancePolicy -Identity 'MG Lab - Copilot: block labelled content'`; the rule goes with it). Policy deletion shows *PendingDeletion* for a while.
2. Delete both sites and empty the SharePoint recycle bin (admin center, Deleted sites). Remove the Anyone/organization links (they go with the files).
3. Restore `SharingCapability` if you changed it; remove any label or label policy you created for this episode.
4. Delete `before.json`, `scan.json` and any token from the shell history (`Remove-Variable`, close the session); do not commit them.
5. Delete the custom data risk assessment if created (30-day expiry otherwise).
