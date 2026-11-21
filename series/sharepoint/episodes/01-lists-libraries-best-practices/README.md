# DEVLADLOG SharePoint #1 — Lists & libraries best practices, as code

Most list problems are designed in on day one and only show up at item 5,001. In this episode the design of a list
is a JSON file, and a small PowerShell module:

- **lints** it against the SharePoint limits that actually bite (list view threshold, indexes, lookup joins,
  permissions, versioning) before anything exists in the tenant
- **provisions** it with PnP PowerShell, idempotently: clean internal names, indexes created up front, filtered views,
  version limits
- **audits** a live list with the same rules, for the size it will grow to

The sample is a fictional Contoso purchasing site: a **Purchase Requests** list (designed for 60,000 items) and a
**Contracts** library. Episode 2 (JSON formatting) formats the same list.

| Path | What it is |
|---|---|
| [`src/MgListDesign.psm1`](src/MgListDesign.psm1) | The module: `Test-MgListDesign` (14 rules), `ConvertTo-MgFieldXml`, `ConvertTo-MgViewQuery` (CAML), `ConvertTo-MgListDesign`, `New-MgSampleRequest`, `Invoke-MgListProvisioning`, `Get-MgListAudit` |
| [`src/designs/purchase-requests.json`](src/designs/purchase-requests.json) | The good design: list + library, every view filters first on an indexed column |
| [`src/designs/bad-design.json`](src/designs/bad-design.json) | Every common mistake in one file (13 findings) — the lint demo |
| [`src/Invoke-ListDesign.ps1`](src/Invoke-ListDesign.ps1) | End to end: lint → connect → provision → seed fictional items → audit the live lists. `-WhatIf` supported; `-AuditList` audits an existing list |
| [`src/designs/audit-demo.json`](src/designs/audit-demo.json) | A "legacy" list that provisions cleanly but breaks two view rules — provisioned with `-Force`, then audited live |
| [`tests/MgListDesign.Tests.ps1`](tests/MgListDesign.Tests.ps1) | 31 Pester tests. The 4 provisioning tests mock the **real** PnP cmdlets, so a wrong parameter name fails the test |

## Run it

```powershell
# Lint only: no tenant, no PnP needed
pwsh ./src/Invoke-ListDesign.ps1 -DesignPath ./src/designs/bad-design.json          # 9 errors, 4 warnings
pwsh ./src/Invoke-ListDesign.ps1 -DesignPath ./src/designs/purchase-requests.json   # No findings

# Tests
Install-Module PnP.PowerShell, Pester -Scope CurrentUser    # PnP is optional: without it 4 tests are skipped
Invoke-Pester ./tests -Output Detailed                       # Tests Passed: 31, Failed: 0
```

Verified in this repo (Linux, PowerShell 7.6, Pester 6.2, PnP.PowerShell 3.5.0): **31 passed, 0 failed**
(without PnP.PowerShell installed: 27 passed, 4 skipped).

Provision in a lab site (needs tenant; your own Entra app registration for PnP with delegated permissions —
see [episode 6](../../../../episodes/06-sharepoint-migration-pnp/setup/register-pnp-app.sh)):

```powershell
$site = 'https://contoso.sharepoint.com/sites/ListsDemo'
$app  = '00000000-0000-0000-0000-000000000000'    # your PnP app's client id
./src/Invoke-ListDesign.ps1 -DesignPath ./src/designs/purchase-requests.json -SiteUrl $site -ClientId $app -WhatIf
./src/Invoke-ListDesign.ps1 -DesignPath ./src/designs/purchase-requests.json -SiteUrl $site -ClientId $app `
    -SeedItems 40 -RequesterEmail alex.demo@contoso.com
./src/Invoke-ListDesign.ps1 -DesignPath ./src/designs/audit-demo.json -SiteUrl $site -ClientId $app -Force
./src/Invoke-ListDesign.ps1 -AuditList 'Legacy Requests' -ExpectedItems 60000 -SiteUrl $site -ClientId $app
```

## The rules

| Rule | Checks | Source |
|---|---|---|
| LD001 | More than 30 million items | SharePoint limits |
| LD002 | Duplicate internal names | design hygiene |
| LD003 | Internal name with spaces or symbols (SharePoint encodes `Due Date` as `Due_x0020_Date`) | column formatting docs |
| LD004 | Versioning off (error on libraries, warning on lists) | house rule |
| LD005 | Manual limit under 100 major versions | version history limits docs |
| LD006 | Breaking inheritance on a list above 100,000 items | SharePoint limits |
| LD007 | Unique permission scopes above 5,000 (warning) / 50,000 (error) | SharePoint limits |
| LD008 | Folders more than 2 levels deep (prefer metadata; 400-character path limit) | house rule + limits |
| LD009 | View uses a column that doesn't exist | design hygiene |
| LD010 | More than 12 lookup/person columns in a view, **counting Created By and Modified By** | list view lookup threshold |
| LD011 | A view's filter still returns more than 5,000 items (`expectedRows`) | list view threshold |
| LD012 | Unfiltered view on a list expected to exceed 5,000 items | list view threshold |
| LD013 | First filter column not indexed on a large list | list view threshold, index limit |
| LD014 | First filter on an indexed **Lookup** column | Field schema docs |

## Design choices
- **Indexes are created with the column** (`Indexed="TRUE"` in the field XML). Adding or removing an index is limited
  to lists under 20,000 items, so it is a day-one decision, not a fix for later.
- **Columns are created from field XML** with `Name`/`StaticName` set to a clean internal name and a friendly
  `DisplayName`. No `_x0020_` to remember in every formatter, filter and API call.
- **Every view of a large list filters first on an indexed column**, and the filter is the first `FieldRef` in the
  CAML, because that's what the audit reads back.
- **Libraries use automatic version history limits** (`Set-PnPList -EnableAutoExpirationVersionTrim $true`); lists
  keep a manual count (100 major versions).
- **The unfiltered default view goes.** SharePoint creates *All Items* / *All Documents* with no filter. On a list
  designed for 60,000 items the design lists them in `removeViews`, and provisioning deletes them after a filtered
  view has become the default (house rule).
- **Idempotent and `-WhatIf`-able.** Re-running creates only what is missing, adds a missing index, and updates views.

## What we learned / gotchas
- **An indexed Lookup column doesn't save you from the threshold.** Learn's field schema says so explicitly; the
  first filter has to be another indexed column type. That's rule LD014.
- **Created By and Modified By are person columns.** They count towards the 12 lookup joins per view, which is how
  a view with "only ten people columns" still fails. That's rule LD010.
- **Our own audit would fail a freshly provisioned list.** SharePoint adds an unfiltered *All Items* view to every
  new list, so the live audit of a list designed for 60,000 items would report LD012 on it. We caught this while
  writing the audit (not yet confirmed on the lab recording); hence `removeViews`.
- **The 5,000 threshold is per query, not per list.** A 60,000-item list is fine if every view's filter is indexed
  and returns fewer than 5,000 rows; that's why the design records `expectedRows` per view.
- **PnP pipe-bind parameters aren't strings.** In the Pester mocks, `-Identity` arrives as a `FieldPipeBind`/
  `ViewPipeBind`; use `$Identity.Name` / `$Identity.Title`, not `"$Identity"`. We only found this because the mocks
  copy the real PnP parameter metadata.
- **`Format-Table -Wrap` printed nothing** in a non-interactive `pwsh -Command` run; the script writes findings with
  `Write-Host` instead, so the output also reads well on screen.

## References
- [SharePoint limits](https://learn.microsoft.com/office365/servicedescriptions/sharepoint-online-service-description/sharepoint-online-limits) — 30 million items, 100,000-item inheritance limit, 50,000/5,000 unique permissions, 400-character paths
- ["The number of items in this list exceeds the list view threshold"](https://learn.microsoft.com/troubleshoot/sharepoint/lists-and-libraries/items-exceeds-list-view-threshold) — 5,000-item list view threshold
- ["Cannot show the value of the filter"](https://learn.microsoft.com/troubleshoot/sharepoint/lists-and-libraries/fails-filtering-sharepoint-column) — indexed columns + filters; 20,000-item limit to add or remove an index
- [Software boundaries and limits](https://learn.microsoft.com/sharepoint/install/software-boundaries-limits-2019#list-and-library-limits) and [SharePoint Online list connector — join limit](https://learn.microsoft.com/power-query/connectors/sharepoint-online-list#troubleshooting) — 12 joins per query
- [Field element (Field) — `Indexed` attribute](https://learn.microsoft.com/sharepoint/dev/schema/field-element-field) — indexed Lookup columns and the threshold
- [Use column formatting — `_x0020_` in internal names](https://learn.microsoft.com/sharepoint/dev/declarative-customization/column-formatting#apply-formatting-based-on-date-ranges)
- [Overview of version history limits](https://learn.microsoft.com/sharepoint/document-library-version-history-limits) and [Plan version storage](https://learn.microsoft.com/sharepoint/plan-version-storage)
- [PnP PowerShell](https://pnp.github.io/powershell/) — `New-PnPList`, `Add-PnPFieldFromXml`, `Set-PnPField`, `Add-PnPView`, `Remove-PnPView`, `Set-PnPList`
- Blog: [Lists & Libraries Best Practices — Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-03-22-lists-libraries-best-practices-complete-guide-2026/)
