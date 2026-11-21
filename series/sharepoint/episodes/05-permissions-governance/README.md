# DEVLADLOG SharePoint #5 — Permissions and governance, as code

Permissions drift quietly: someone gets Full Control "just for today", a list breaks inheritance for one person,
"Everyone except external users" lands in the Visitors group, an edit link to an invoice goes to the whole company.
In this episode the Contoso Purchasing site from [episode 3](../03-modern-sites-pages/) and its Supplier Documents
library from [episode 4](../04-document-management/) get a **governance policy in JSON** and a small PowerShell module
that:

- **lints the policy** before it's used: valid sharing values, the site can't be more permissive than the
  organization, no "Anyone" default link where Anyone links can't exist, at least two owners, unique-permission limits
- **takes a snapshot** of the live site: site sharing settings and sensitivity label (SharePoint admin), site admins,
  groups and their members, role assignments on the site, every list that breaks inheritance and every item that does,
  and the sharing links on files
- **audits** the snapshot against the policy with 15 rules (GV001–GV015)
- **builds a remediation plan** and applies it with the real PnP cmdlets (`-WhatIf` first), then audits again

Earlier episodes covered list design (1), formatting (2), the site and pages (3) and content types (4); this episode
doesn't repeat them. Search and metadata are [episode 6](../06-search-metadata/).

| Path | What it is |
|---|---|
| [`src/MgGovernance.psm1`](src/MgGovernance.psm1) | The module: `Test-MgGovernancePolicy` (GP001–GP007), `Test-MgPermissionSnapshot` (GV001–GV015), `Get-MgRemediationPlan`, `Get-MgScopeSummary`, `Get-MgPermissionSnapshot`, `Invoke-MgRemediation` |
| [`src/governance/purchasing.policy.json`](src/governance/purchasing.policy.json) | The policy: only people in the organization, specific-people view links by default, label *Confidential*, 2–5 owners, Full Control only for the Owners group, Supplier Documents is the one list allowed its own permissions (and with which groups) |
| [`src/bad/loose.policy.json`](src/bad/loose.policy.json) | A policy with the usual mistakes: the lint demo (5 errors, 2 warnings) |
| [`src/fixtures/drifted.snapshot.json`](src/fixtures/drifted.snapshot.json) | A fictional snapshot of the drifted lab site, in exactly the shape `Get-MgPermissionSnapshot` returns: the offline demo and the test data (4 errors, 8 warnings) |
| [`src/New-PermissionDrift.ps1`](src/New-PermissionDrift.ps1) | **Lab only.** Creates that drift in the lab site so the audit has something real to find. `-WhatIf` |
| [`src/Invoke-Governance.ps1`](src/Invoke-Governance.ps1) | End to end: lint → snapshot (file or live) → audit → plan → `-Fix` → audit again. `-WhatIf`, `-ExportSnapshot` |
| [`tests/MgGovernance.Tests.ps1`](tests/MgGovernance.Tests.ps1) | 23 Pester tests. The 5 tenant tests mock the **real** PnP cmdlets |

## Run it

```powershell
cd src
./Invoke-Governance.ps1 -PolicyPath ./bad/loose.policy.json                       # 5 error(s), 2 warning(s)
./Invoke-Governance.ps1 -PolicyPath ./governance/purchasing.policy.json `
    -SnapshotPath ./fixtures/drifted.snapshot.json -SensitivityLabelId 00000000-0000-0000-0000-000000000000
                                                                                   # 4 error(s), 8 warning(s); 11 can be fixed automatically
cd ..

Install-Module PnP.PowerShell, Pester -Scope CurrentUser   # PnP is optional: without it 5 tests are skipped
Invoke-Pester ./tests -Output Detailed                      # Tests Passed: 23, Failed: 0
```

Verified in this repo (Linux, PowerShell 7.6, Pester 6.2, PnP.PowerShell 3.5.0): **23 passed, 0 failed**
(without PnP.PowerShell: 18 passed, 5 skipped).

In the lab (needs tenant; SharePoint admin for the site sharing settings and the label, site collection admin for the
rest; your own Entra app for PnP with delegated permissions — see
[episode 6 of MG Lab](../../../../episodes/06-sharepoint-migration-pnp/setup/register-pnp-app.sh)):

```powershell
$site  = 'https://contoso.sharepoint.com/sites/Purchasing'     # the episode 3 site
$app   = '00000000-0000-0000-0000-000000000000'
$label = '00000000-0000-0000-0000-000000000000'                # Get-Label | ft Name, Guid  (Security & Compliance PowerShell)
./src/New-PermissionDrift.ps1 -SiteUrl $site -ClientId $app -DirectUser lee.gu@contoso.com `
    -ShareWithUser megan.bowen@contoso.com -ContractManager isaiah.langer@contoso.com          # lab only
./src/Invoke-Governance.ps1 -PolicyPath ./src/governance/purchasing.policy.json -SiteUrl $site -ClientId $app `
    -SensitivityLabelId $label -ExportSnapshot ./src/snapshots/before.json
./src/Invoke-Governance.ps1 -PolicyPath ./src/governance/purchasing.policy.json -SiteUrl $site -ClientId $app `
    -SensitivityLabelId $label -Fix -WhatIf
./src/Invoke-Governance.ps1 -PolicyPath ./src/governance/purchasing.policy.json -SiteUrl $site -ClientId $app `
    -SensitivityLabelId $label -Fix
```

## Licensing (what each part needs)

| Feature used | Licence | Notes |
|---|---|---|
| Site sharing settings, default link type and permission, groups, permissions, sharing links | SharePoint (any plan; the lab's Microsoft 365 E5) | SharePoint Administrator to change site sharing settings; site owners can't |
| Sensitivity label on the site (*Confidential*) | Microsoft Purview sensitivity labels, included in the lab's Microsoft 365 E5 | Labels for containers must be enabled once (Entra `EnableMIPLabels` + `Execute-AzureAdLabelSync`), the label scoped to *Groups & sites* and published; wait at least an hour for a new label |
| Not used: Restricted access control, data access governance reports, site ownership policy | **SharePoint Advanced Management** | Not included in Microsoft 365 E5: it needs a Microsoft 365 Copilot licence in the organization or the SharePoint Advanced Management Plan 1 add-on. The audit in this episode does the site-level part without it |

## The rules

| Rule | Checks | Source |
|---|---|---|
| GP001 | Unknown sharing capability, link type, link permission or link scope | `Set-SPOSite` / PnP `SharingCapabilities`, `SharingLinkType`, `SharingPermissionType`; Graph link scopes |
| GP002 | Site sharing more permissive than the organization | "The available settings depend on your organization-level setting" |
| GP003 | Default link *Anyone* on a site that can't create Anyone links | change-default-sharing-link + site sharing options |
| GP004 | Fewer than two owners required (warning) | house rule |
| GP005 | Max unique items per list above 5,000 (warning) or 50,000 (error) | SharePoint limits |
| GP006 | Label named but no label id (warning) | — |
| GP007 | `@Role` that isn't Owners, Members or Visitors | — |
| GV001 | Site sharing more permissive than the policy | — |
| GV002 / GV003 | Default sharing link type / permission differs (warning) | — |
| GV004 | Sensitivity label missing or different | — |
| GV005 | Owners group has fewer or more people than the policy says (warning, no automatic fix) | — |
| GV006 | More site admins than allowed (warning) | — |
| GV007 | *Everyone* or *Everyone except external users* in a group or granted anywhere | EEEU makes content visible to the whole organization |
| GV008 | A person granted directly on the site or a list instead of through a group (warning) | house rule |
| GV009 | Full Control for anyone but the Owners group | — |
| GV010 | A list with unique permissions the policy doesn't list (warning) | — |
| GV011 | A grant on an allowed list that the policy doesn't declare (warning) | — |
| GV012 | An item with unique permissions (warning) | — |
| GV013 | Unique items per list above the policy, 5,000 or 50,000 | SharePoint limits |
| GV014 | Sharing link with a forbidden (error) or discouraged (warning) scope | — |
| GV015 | A guest (`#EXT#` in the login) on a site that allows no external sharing | Existing guests have #EXT# in their UPN |

*Limited Access* is ignored everywhere: SharePoint assigns it so people can reach an item they were given, and it
can't be edited.

## Design choices
- **The policy names roles, not groups.** `@Owners`, `@Members`, `@Visitors` resolve to the site's associated groups,
  so the same policy works on any site.
- **A snapshot is plain JSON.** `Get-MgPermissionSnapshot` is the only part that reads the tenant; the audit works
  on the JSON. Save it with `-ExportSnapshot` and you have a dated record of who had access.
- **Every finding says how to fix it, or that a person must.** Owners and guests aren't fixed automatically.
- **One call for site settings, links before items before lists.** The plan merges sharing, default link and label
  into one `Set-PnPTenantSite`, and drops grant removals on a list whose inheritance is going to be reset.
- **`-WhatIf` everywhere** (remediation and the drift script), and the remediation audits again at the end.
- **The drift is created by a script, except one step.** Adding *Everyone except external users* is done in the
  browser, the way it happens in real sites; the script prints that reminder.

## What we learned / gotchas
- **SharePoint Advanced Management isn't in E5.** Learn's prerequisites say SAM comes with a Microsoft 365 Copilot
  licence in the organization or the SAM Plan 1 add-on (or Microsoft 365 E7). The lab is an E5 trial, so the episode
  uses only base SharePoint features plus Purview labels, and says so.
- **Limited Access is noise.** In the drifted site Megan and Contract Managers appear on the site itself, but only with
  *Limited Access*: Learn documents it as the level SharePoint combines with fine-grained permissions so people can
  reach one list or item, and it can't be edited. Counting it would flag every item share twice, so the audit ignores it.
- **Breaking inheritance with "copy" keeps everyone.** `Set-PnPList -BreakRoleInheritance -CopyRoleAssignments`
  copies the site's role assignments (that's what the CSOM `copyRoleAssignments` parameter does), so Members keep *Edit* on the "restricted" library. GV011
  exists for exactly that.
- **`"$Group"` in a mock isn't the group name.** PnP's `GroupPipeBind` doesn't stringify to its name; the tests compare
  `$Group.Name`. `ListPipeBind` and `SPOSitePipeBind` do.
- **Sharing links come from Microsoft Graph, one call per file.** `Get-PnPFileSharingLink` returns all permissions of
  a file; only the ones with a `Link` are links. The snapshot skips libraries above 500 items (`-MaxFilesForLinks`).
- **Not verified yet (lab recording):** that `Get-PnPListItem -Includes HasUniqueRoleAssignments` loads the property
  for every item in paged reads, that `Set-PnPTenantSite -SensitivityLabel` accepts the label GUID for a communication
  site, the exact principal type PnP reports for *Everyone except external users*, and that
  `Remove-PnPFileSharingLink` removes an organization link by its Graph permission id. `Get-MgRoleAssignment` (CSOM
  `RoleAssignments`, `Member`, `RoleDefinitionBindings`) only runs against the tenant. demo.md says what to check.
- The fixture's login names are illustrative; the code matches people by display name and principal type, never by a
  claim string.

## References
- [Change the sharing settings for a site](https://learn.microsoft.com/sharepoint/change-external-sharing-site) — site options, "depend on your organization-level setting", defaults per site type (communication site: only people in your organization), SharePoint Administrator required
- [Manage sharing settings](https://learn.microsoft.com/sharepoint/turn-external-sharing-on-or-off) — Anyone / New and existing guests / Existing guests / Only people in your organization
- [Set external sharing on site collections](https://learn.microsoft.com/sharepoint/dev/solution-guidance/set-external-sharing-on-site-collections-in-office-365) — `SharingCapabilities` values
- [Change the default sharing link type for a site](https://learn.microsoft.com/sharepoint/change-default-sharing-link) and [How shareable links work](https://learn.microsoft.com/sharepoint/shareable-links-anyone-specific-people-organization)
- [Set-SPOSite](https://learn.microsoft.com/powershell/module/microsoft.online.sharepoint.powershell/set-sposite) — `SharingCapability`, `DefaultSharingLinkType`, `DefaultLinkPermission`, `SensitivityLabel`
- [SharePoint limits](https://learn.microsoft.com/office365/servicedescriptions/sharepoint-online-service-description/sharepoint-online-limits) and [Manage permission scopes](https://learn.microsoft.com/sharepoint/manage-permission-scope) — 50,000 supported, 5,000 recommended unique permissions per list or library
- [User permissions and permission levels](https://learn.microsoft.com/sharepoint/sites/user-permissions-and-permission-levels) — Limited Access can't be edited
- [Default SharePoint groups](https://learn.microsoft.com/sharepoint/default-sharepoint-groups) and [Data access governance PowerShell](https://learn.microsoft.com/sharepoint/powershell-for-data-access-governance) — *Everyone except external users* makes content visible to the entire organization
- [Grant the Everyone claim to external users](https://learn.microsoft.com/troubleshoot/microsoft-365/admin/access-management/grant-everyone-claim-to-external-users) — use Entra groups instead of default claims
- [Use sensitivity labels with groups and sites](https://learn.microsoft.com/purview/sensitivity-labels-teams-groups-sites) — enabling container labels, `Execute-AzureAdLabelSync`, label settings for sites, applying with `Set-SPOSite -SensitivityLabel`
- [Prerequisites for SharePoint Advanced Management](https://learn.microsoft.com/sharepoint/sharepoint-advanced-management-prerequisites) — Copilot licence or SAM Plan 1 add-on
- [SecurableObject.BreakRoleInheritance](https://learn.microsoft.com/dotnet/api/microsoft.sharepoint.client.securableobject.breakroleinheritance) — `copyRoleAssignments`, `clearSubscopes`
- [PnP PowerShell](https://pnp.github.io/powershell/) — `Get-PnPTenantSite`, `Set-PnPTenantSite`, `Get-PnPGroup -Associated*Group`, `Get-PnPGroupMember`, `Get-PnPListItem -Includes`, `Get-PnPFileSharingLink`, `Remove-PnPFileSharingLink`, `Set-PnPWebPermission`, `Set-PnPListPermission`, `Set-PnPListItemPermission -InheritPermissions`, `Set-PnPList -ResetRoleInheritance`
- Blog: [Permissions & Governance — Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-03-26-permissions-governance-complete-guide-2026/)
