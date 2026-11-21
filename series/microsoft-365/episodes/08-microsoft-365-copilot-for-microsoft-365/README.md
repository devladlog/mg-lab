# DEVLADLOG Microsoft 365 #8 — Microsoft 365 Copilot for Microsoft 365

**Get ready before you buy.** The lab tenant has **no Microsoft 365 Copilot licence**, so this episode builds and shows
what works without one, for real, and says plainly which parts need the licence. Nothing in this folder fakes Copilot output.

1. **Licence readiness** — `Get-CopilotSku`, `Get-CopilotUserLicence`, `Test-CopilotReadiness`: reads the tenant's subscriptions and
   each user's service plans through Graph, answers "is there a Copilot licence?" and, per user, "Copilot licensed / Copilot Chat
   only / not ready" with the reason (disabled account, no Copilot Chat entitlement plan, no Exchange Online mailbox, no Microsoft 365 Apps plan).
   A Copilot Studio trial is **not** counted as a Copilot licence.
2. **Copilot Chat with Entra accounts** — the demo uses it for real (free with E5, enterprise data protection, files you upload); the
   code only checks that each user has the prerequisites.
3. **Oversharing review** — `Get-CopilotDrive`, `Get-CopilotSharedItem`, `Get-CopilotSharingFinding`: a bounded, read-only walk of
   document libraries that flags Anyone links, organization-wide links and **Everyone except external users**, with higher severity for
   names that look sensitive.
4. **Labels** — `Get-CopilotLabel`, `Get-CopilotLabelFinding`: reads the tenant's sensitivity labels (the ones episode 5 creates) and
   reports what is missing: nothing for files, nothing for sites and groups, no default, nothing applied automatically.
5. **Needs the licence** — `Get-CopilotUsageReport`: the Copilot usage report from Graph. Real code, tested against a fake, but **not
   run against a tenant**; the runner refuses to call it when the tenant has no Copilot licence.

Same fictional tenant as episodes 1–7 (`contoso`); lab users `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo`. The data
in the tests is fictional and **never** appears in the demo.

| Path | What it is |
|---|---|
| [`src/copilot.json`](src/copilot.json) | The plan names and SKU part numbers that count as Copilot, mailbox and Chat entitlement; walk limits; sensitive-name hints; which sharing signals and label gaps to flag |
| [`src/CopilotReadiness/CopilotReadiness.psm1`](src/CopilotReadiness/CopilotReadiness.psm1) | The module: Graph collection (GET only), pure analysis, markdown report |
| [`src/CopilotReadiness/CopilotReadiness.psd1`](src/CopilotReadiness/CopilotReadiness.psd1) | Module manifest |
| [`src/Invoke-CopilotReadiness.ps1`](src/Invoke-CopilotReadiness.ps1) | Runner: `-Check Licences,Labels,Sharing,Usage`, `-Snapshot` (offline), `-SaveSnapshot`, `-SiteSearch`, `-OutFile` |
| [`tests/CopilotReadiness.Tests.ps1`](tests/CopilotReadiness.Tests.ps1) | 49 Pester tests (a small fake Graph tenant; one test checks our calls against the real Microsoft.Graph.Authentication module) |
| [`tests/fixtures/`](tests/fixtures) | Fictional SKUs, users with service plans, labels, two document libraries with seeded sharing, and the snapshot built from them |
| [`sample/copilot-readiness.md`](sample/copilot-readiness.md) | Report for the fictional snapshot, generated offline |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and shot list (no new VM; no Copilot licence bought; licence-only inserts marked with their cost) |

## Run the tests

```bash
cd series/microsoft-365/episodes/08-microsoft-365-copilot-for-microsoft-365
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Without the real Graph module:  Tests Passed: 48, Failed: 0, Skipped: 1
# With Microsoft.Graph.Authentication installed (it adds the "real module parameters" test):
#                                 Tests Passed: 49, Failed: 0, Skipped: 0
```

Both results were produced in this repo's container (PowerShell 7.6, Pester 6.2.0; Microsoft.Graph.Authentication saved to a temp folder on
`PSModulePath`). PSScriptAnalyzer (Warning and Error) reports 0 issues on `src/`.

## Run it

```powershell
cd src
# Offline (no tenant): analyse the fictional snapshot
./Invoke-CopilotReadiness.ps1 -Snapshot ../tests/fixtures/snapshot.json -OutFile ../sample/copilot-readiness.md
#   -> no Copilot licence; 6 users (4 Chat only, 2 not ready); 2 label findings; 4 broad-sharing findings

# Needs tenant (see demo.md): copy copilot.json to copilot.lab.json first
./Invoke-CopilotReadiness.ps1 -ConfigFile ./copilot.lab.json -Check Licences   # LicenseAssignment.Read.All, User.Read.All
./Invoke-CopilotReadiness.ps1 -ConfigFile ./copilot.lab.json -Check Labels     # SensitivityLabel.Read
./Invoke-CopilotReadiness.ps1 -ConfigFile ./copilot.lab.json -Check Sharing    # Sites.Read.All, Files.Read.All
./Invoke-CopilotReadiness.ps1 -Check Usage   # needs a Copilot licence in the tenant: Reports.Read.All + a report-reader role
```

## What we learned / gotchas

- **Product names moved.** Learn now calls the product **Microsoft Copilot** (and Copilot Chat **Microsoft Copilot Chat**), with the app at
  `copilot.cloud.microsoft` (allow `*.cloud.microsoft`). The SKU part numbers and service plans still use the old names
  (`Microsoft_365_Copilot`, `M365_Copilot`, `M365_COPILOT_APPS`, ...), which is what the code matches. The blog article and the episode title use the old name.
- **A Copilot Studio trial is not a Copilot licence**, even though `COPILOT_STUDIO_IN_COPILOT_FOR_M365` is one of the plans inside the
  Copilot SKU. The check matches the Copilot SKU part numbers or the plans that put Copilot in the apps (`M365_COPILOT_APPS`,
  `M365_COPILOT_BUSINESS_CHAT`), and only counts a plan whose `provisioningStatus` is `Success`.
- **Copilot Chat vs the add-on (Learn):** Chat needs an eligible base licence and an Entra account; the add-on adds Copilot in the apps,
  automatic grounding in Microsoft Graph, SharePoint Advanced Management (SAM) features and the app usage reports. Without the add-on, Chat can use
  organizational content only if you upload it, have it open in Outlook or Teams, or use a pay-as-you-go agent.
- **Copilot respects permissions, so oversharing is the risk.** What a person can already open, Copilot can surface. Restricted content
  discovery hides a site from Copilot answers without changing permissions; it is a stopgap while you fix them.
- **Library permissions have no `inheritedFrom`** (Learn: *permission resource type*), so the same permission can repeat down a tree. The review
  reports it once, at the shallowest path.
- **A non-owner sees only the sharing permissions that apply to them** (Learn: *list permissions*). Run the review as the site owner, or the
  numbers are too low. A tenant-wide review needs application permissions (`Files.Read.All`) and an app registration: not done here.
- **This is a sampled walk** (200 items, 3 levels per library by default). The tenant-wide answer is the SAM data access governance reports
  (site permission reports, Everyone except external users, sharing links), which the lab does not have (SAM needs a Copilot licence or the add-on).
- **The usage report only lists licensed users** (Learn); unlicensed Copilot Chat usage isn't available through Graph reports (use the admin
  center Copilot Chat usage report or the Purview audit log).
- **Cost** (Microsoft's pricing pages, read 21 Nov 2026; shown for marketing, real price at checkout): Copilot enterprise add-on 30.00 USD per user
  per month paid yearly; Copilot Business 18.00 USD per user per month paid yearly (up to 300 users, Business licences; a discount window to 31 Dec 2026 is shown).
  Annual subscription, auto-renews.
- Pitfalls hit while building: returning arrays with the comma trick nests them (callers use `@()` instead); `Format-Table` prints nothing
  without a console (the runner uses `Out-String -Width`).
- **Not verified** (needs tenant, see [demo.md](demo.md)): how Graph renders the *Everyone except external users* grant (the code matches the
  documented display name and the common claim fragment `spo-grid-all-users`); that the `Bing_Chat_Enterprise` service plan ("Commercial data
  protection for Microsoft Copilot" in the plan list) is exactly what gates Copilot Chat: it is used as the entitlement signal; whether `sites?search=*`
  returns every site the signed-in user can reach; the format of `applicableTo` on labels (parsed as a comma/space separated string); that the usage report
  arrives as CSV on v1.0 (Learn shows CSV for the v1.0 page and JSON for the preview page; the code downloads a CSV); whether a trial tenant can buy
  Copilot and the cancellation terms of the annual subscription.

Not covered (to keep the episode to 6 minutes): agents and Copilot Studio, Copilot Search and connectors, Purview DSPM for AI and DLP for
Copilot, restricted SharePoint search, site access reviews and inactive-site policies, rollout and adoption planning, Copilot Analytics.

## References

- [Microsoft Copilot overview](https://learn.microsoft.com/copilot/plan/copilot-overview) · [Requirements](https://learn.microsoft.com/copilot/plan/microsoft-copilot-requirements) · [License options](https://learn.microsoft.com/copilot/plan/copilot-license-options) · [Enterprise data protection](https://learn.microsoft.com/copilot/plan/enterprise-data-protection)
- [Secure and govern Copilot: foundational deployment guidance](https://learn.microsoft.com/copilot/plan/secure-govern-copilot-foundational-deployment-guidance) · [SAM features in Copilot licenses](https://learn.microsoft.com/sharepoint/sharepoint-advanced-management-features-copilot-license) · [Data access governance reports](https://learn.microsoft.com/sharepoint/data-access-governance-reports) · [Everyone except external users, item-level report](https://learn.microsoft.com/sharepoint/data-access-governance-detailed-eeeu-everyone-permissions-report) · [Data access governance with PowerShell](https://learn.microsoft.com/sharepoint/powershell-for-data-access-governance) · [Restricted content discovery](https://learn.microsoft.com/sharepoint/restricted-content-discovery)
- [Product names and service plan identifiers for licensing](https://learn.microsoft.com/entra/identity/users/licensing-service-plan-reference) · [List subscribedSkus](https://learn.microsoft.com/graph/api/subscribedsku-list?view=graph-rest-1.0) · [subscribedSku](https://learn.microsoft.com/graph/api/resources/subscribedsku?view=graph-rest-1.0) · [List licenseDetails](https://learn.microsoft.com/graph/api/user-list-licensedetails?view=graph-rest-1.0)
- [Search for sites](https://learn.microsoft.com/graph/api/site-search?view=graph-rest-1.0) · [List sharing permissions on a driveItem](https://learn.microsoft.com/graph/api/driveitem-list-permissions?view=graph-rest-1.0) · [Permission resource type](https://learn.microsoft.com/graph/api/resources/permission?view=graph-rest-1.0) · [sharingLink (scope values)](https://learn.microsoft.com/graph/api/resources/sharinglink?view=graph-rest-1.0) · [Create a sharing link (demo setup)](https://learn.microsoft.com/graph/api/driveitem-createlink?view=graph-rest-1.0)
- [List sensitivityLabels (v1.0)](https://learn.microsoft.com/graph/api/tenantdatasecurityandgovernance-list-sensitivitylabels?view=graph-rest-1.0) · [sensitivityLabel resource](https://learn.microsoft.com/graph/api/resources/security-sensitivitylabel?view=graph-rest-1.0) · [Get Copilot usage user detail](https://learn.microsoft.com/microsoft-365/copilot/extensibility/api/admin-settings/reports/copilotreportroot-getmicrosoft365copilotusageuserdetail)
- Pricing (not Learn; read 21 Nov 2026): [Microsoft Copilot pricing](https://www.microsoft.com/microsoft-365/copilot/pricing) · [enterprise plans](https://www.microsoft.com/en-us/microsoft-365-copilot/pricing/enterprise)
- Blog: [Microsoft 365 Copilot for Microsoft 365 — Complete Guide](https://www.devladlog.com/articles/office-365/2026-06-04-copilot-m365-complete-guide-2026/)
  (note: the current article has no licence names or requirements and its code uses placeholder cmdlets `Set-Configuration` and
  `Get-DeploymentStatus`, an `api.microsoft.com` endpoint that isn't Microsoft Graph, and `Directory.ReadWrite.All` scopes; this folder's code
  is meant to replace it. Its date also doesn't match its URL)
