# DEVLADLOG Copilot & AI #19 - Copilot Governance: Purview DSPM for AI and Admin Controls

Microsoft 365 Copilot returns only what the signed-in user can already open, so the real governance work is (1) how much
Contoso's users can open, (2) which Purview and SharePoint controls limit what Copilot may use, and (3) the evidence.
This episode walks the current **Data Security Posture Management (DSPM)** experience in Microsoft Purview and adds
code you can run:

- `Export-CopilotGovernanceSnapshot.ps1` reads the relevant settings (audit, labels, DLP, SharePoint tenant and sites)
  into one JSON file. Read-only, never signs in, records sections it could not read.
- `copilot_governance` (Python, standard library) turns that JSON into eight posture checks with a Learn link and a fix
  for each, and exits non-zero on a failed high-severity check (usable as a rollout gate).
- `graph_scan.py` lists sharing links (Anyone, organization, specific people) on the top level of SharePoint document
  libraries through Microsoft Graph, for tenants that do not own SharePoint Advanced Management; `oversharing.py` ranks
  the result.
- `New-CopilotLabelDlpPolicy.ps1` creates a DLP policy for the Copilot location that stops Copilot from processing items
  with chosen sensitivity labels. Dry run by default, simulation mode when applied.

Series plan: [`../../README.md`](../../README.md). Shared lab: [`../../../LAB.md`](../../../LAB.md). Previous in series:
[episode 17, Extending Microsoft 365 Copilot](../17-extending-microsoft-365-copilot-declarative-agents/) (18, Security Copilot,
is built separately). Episode 2 already reads the Copilot audit records ([audit tool](../02-microsoft-365-copilot-chat-in-a-real-tenant/)),
so this episode does not repeat it. Category episodes this builds on:
[Microsoft Purview compliance](../../../microsoft-365/episodes/05-microsoft-purview-compliance/),
[Microsoft 365 Copilot for Microsoft 365](../../../microsoft-365/episodes/08-microsoft-365-copilot-for-microsoft-365/),
[SharePoint Online administration](../../../microsoft-365/episodes/11-sharepoint-online-administration/).
Next: episode 20, [Azure AI Foundry Agent Service with Multiple Models](../20-azure-ai-foundry-agent-service-with-multiple-model/).

| Path | What it is |
|---|---|
| [`src/scripts/Export-CopilotGovernanceSnapshot.ps1`](src/scripts/Export-CopilotGovernanceSnapshot.ps1) | Collector. Needs `Connect-ExchangeOnline`, `Connect-IPPSSession`, `Connect-SPOService` first |
| [`src/scripts/New-CopilotLabelDlpPolicy.ps1`](src/scripts/New-CopilotLabelDlpPolicy.ps1) | Copilot-location DLP policy for labelled content. Needs `Connect-IPPSSession`; `-Apply` to create |
| [`src/copilot_governance/checks.py`](src/copilot_governance/checks.py) | Checks G01 to G08 |
| [`src/copilot_governance/graph_scan.py`](src/copilot_governance/graph_scan.py) | Graph collector (token in `GRAPH_TOKEN`, capped, honours `Retry-After`) |
| [`src/copilot_governance/oversharing.py`](src/copilot_governance/oversharing.py) | Link classification and per-site summary |
| [`src/samples/`](src/samples) | Fictional snapshots before/after and a fictional Graph scan (tests only) |
| [`tests/`](tests) | 15 pytest tests, including `pwsh` runs of both scripts and a loopback HTTP server for the Graph client |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (14 scenes) and shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/19-copilot-governance-purview-dspm-for-ai-and-admin-c
python3 -m pip install -r src/requirements.txt     # pytest only; the tool is standard library
python3 -m pytest -q                                # 15 passed (needs pwsh for 3 of them)
cd src
python3 -m copilot_governance samples/snapshot-before.json --sharing samples/sharing-scan.json   # exit 1: G03 fails
python3 -m copilot_governance samples/snapshot-after.json                                        # exit 0
```

Against the tenant (needs the tenant, read-only except where stated):

```powershell
Connect-ExchangeOnline; Connect-IPPSSession; Connect-SPOService -Url https://<tenant>-admin.sharepoint.com
./src/scripts/Export-CopilotGovernanceSnapshot.ps1 -OutFile before.json
python -m copilot_governance before.json
./src/scripts/New-CopilotLabelDlpPolicy.ps1 -LabelName 'Highly Confidential'          # dry run
./src/scripts/New-CopilotLabelDlpPolicy.ps1 -LabelName 'Highly Confidential' -Apply   # creates, simulation mode
$env:GRAPH_TOKEN = '<token, typed off camera>'; python -m copilot_governance.graph_scan --out scan.json
python -m copilot_governance before.json --sharing scan.json
```

Verified here: pytest 15 passed (Python 3.13, PowerShell 7.6). The PowerShell scripts run under `pwsh` against stand-in
cmdlets (test only), the Graph client against a local loopback server (test only). **Not verified without the tenant:**
the real property names and shapes returned by `Get-DlpCompliancePolicy`, `Get-Label` and `Get-SPOSite` (the checks are
tolerant, see "gotchas"), the Graph token source and consent, and every portal screen.

## What we learned / gotchas

- **Renamed.** The current Purview solution is *Data Security Posture Management*; the earlier *DSPM for AI* is now
  *DSPM for AI (classic)* and *DSPM (classic)*, and Learn says new features go to the current version only. Setup,
  objectives, **AI observability**, **Discover > Data risk assessments**. Many Learn pages (prerequisites, one-click policies,
  activity explorer events) still sit under the classic article.
- **Licences are the plot.** Learn lists as a prerequisite that for Microsoft 365 Copilot and agents, users are assigned a
  Microsoft 365 Copilot licence (to monitor their interactions). Restricted Content Discovery needs a Copilot licence and
  SharePoint Advanced Management. The item-level *Everyone except external users* report is a SharePoint Advanced Management
  report. DSPM itself needs "a supporting licence" per the Purview service description (not checked per SKU here).
- **Default data risk assessment:** runs weekly for the top 100 SharePoint sites by usage; the first time it is created
  there is a 4 day delay before results show; custom assessments need at least 48 hours; limit 200,000 items per location;
  item-level scanning (custom assessment) is limited to 10 SharePoint sites and needs an Entra app with Graph application
  permissions (Files.ReadWrite.All, Sites.ReadWrite.All and others, per Learn).
- **DLP for the Copilot location** (*Microsoft Copilot, Copilot Chat, and Copilot Cowork*): only in the Custom template,
  disables all other locations of that policy; label rules and sensitive-information-type rules cannot share one rule;
  labelled items still appear in citations; files uploaded into a prompt are not scanned; Word/Excel/PowerPoint evaluate
  at file open; policy changes take up to four hours; simulation mode exists. Blocking sensitive information types in
  prompts is **preview** and "rolling out" per Learn (check the tenant). Emails count only if sent on or after 1 January 2025.
- **PowerShell creation** (Learn, `New-DlpCompliancePolicy` example): `-Locations` JSON with Workload `Applications`
  and Location `470f2276-e011-4e9d-a6ec-20768be3a4b0`, `-EnforcementPlanes @('CopilotExperiences')`, and a rule with
  `-RestrictAccess @(@{setting='ExcludeContentProcessing';value='Block'})`. `-WhatIf` does not work in Security &
  Compliance PowerShell, which is why the script has its own dry run.
- **`Get-SPOSite` gotcha (Learn):** with `-Limit` or `-Filter` properties such as `SensitivityLabel` and `SharingCapability`
  are not populated. The collector lists sites, then reads each one by `-Identity`.
- **`SharingCapability` values** (Learn, `Set-SPOApplication`/`Set-SPOTenant`): `Disabled`, `ExternalUserSharingOnly`,
  `ExternalUserAndGuestSharing`, `ExistingExternalUserSharingOnly`. The mapping to the admin center names (Anyone =
  `ExternalUserAndGuestSharing`) comes from general knowledge, not from that page: confirm on the tenant.
- **Retention for Copilot** has its own location now (*Microsoft Copilot experiences*, enterprise AI apps, other AI apps;
  previously part of *Teams chats and Copilot interactions*). Content sits in a hidden mailbox folder; a "delete after 1 day"
  policy can take 16 days to remove it from eDiscovery. The documented retention cmdlet `New-RetentionCompliancePolicy`
  has no Copilot location parameter, so this episode shows retention in the portal only.
- **Restricted Content Discovery** is described as a temporary control; it does not change permissions and also removes AI
  entry points (Copilot button, *Create pages with AI*) from the restricted site. `Set-SPOSite -RestrictContentOrgWideSearch`.
- **Graph sharing links:** `scope` is `anonymous`, `organization`, `existingAccess` or `users`; permission properties that
  hold secrets are returned only to callers able to create them; for a non-owner caller only permissions that apply to the
  caller are returned. So a scan as a plain user under-reports; use an account or app with Files.Read.All or Sites.Read.All.
  The file-name keyword list is a heuristic and had a bug found by a test ("calendar" contains "nda").
- **Everyone except external users** is added to the Members group of public modern team sites automatically; for private
  team sites it cannot be granted permissions (Learn, permission levels). Hiding the claim from the people picker
  (`ShowEveryoneExceptExternalUsersClaim`) does not remove existing grants.

## References

Microsoft Learn
- [Microsoft Purview data security and compliance protections for generative AI apps](https://learn.microsoft.com/purview/ai-microsoft-purview)
- [Learn about Data Security Posture Management](https://learn.microsoft.com/purview/data-security-posture-management-learn-about)
- [Permissions for Data Security Posture Management](https://learn.microsoft.com/purview/data-security-posture-management-permissions)
- [Prevent oversharing with data risk assessments](https://learn.microsoft.com/purview/data-security-posture-management-oversharing)
- [DSPM for AI (classic): considerations, prerequisites, one-click policies](https://learn.microsoft.com/purview/dspm-for-ai-considerations)
- [DLP to protect interactions with Microsoft 365 Copilot, Copilot Chat, and Cowork](https://learn.microsoft.com/purview/dlp-microsoft365-copilot-location-learn-about)
- [New-DlpCompliancePolicy](https://learn.microsoft.com/powershell/module/exchange/new-dlpcompliancepolicy)
- [Retention for Copilot & AI apps](https://learn.microsoft.com/purview/retention-policies-copilot)
- [Restricted Content Discovery](https://learn.microsoft.com/sharepoint/restricted-content-discovery)
- [SharePoint Advanced Management features in Copilot licenses](https://learn.microsoft.com/sharepoint/sharepoint-advanced-management-features-copilot-license)
- [Item-level permissions for Everyone except external users](https://learn.microsoft.com/sharepoint/data-access-governance-detailed-eeeu-everyone-permissions-report)
- [Get-SPOSite](https://learn.microsoft.com/powershell/module/microsoft.online.sharepoint.powershell/get-sposite) and [Set-SPOTenant](https://learn.microsoft.com/powershell/module/microsoft.online.sharepoint.powershell/set-spotenant)
- [List sharing permissions on a driveItem](https://learn.microsoft.com/graph/api/driveitem-list-permissions) and [sharingLink resource](https://learn.microsoft.com/graph/api/resources/sharinglink)
- [Data protection and auditing for Microsoft Copilot](https://learn.microsoft.com/copilot/plan/architecture-data-protection-auditing)

No devladlog.com blog guide: this series is built from vendor documentation only.
