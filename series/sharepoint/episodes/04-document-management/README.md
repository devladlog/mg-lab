# DEVLADLOG SharePoint #4 — Document management, as code

Document management fails quietly: files with no type, required metadata nobody filled in, contracts that expired
in a folder nobody opens. In this episode the Contoso purchasing site from [episode 3](../03-modern-sites-pages/)
gets a **Supplier Documents** library, and everything about it is a JSON design plus a small PowerShell module:

- **content types with correct IDs** — Purchasing Document → Contract and Invoice, and a **Supplier File document
  set** — linted against Learn's content type ID rules (lineage, `00` + GUID, the 1,024-character limit)
- **a library** with those content types only (the generic *Document* type removed), a default content type, a
  default value for Department, Document IDs on, and check-out *not* required
- **a filing plan**: rules that read the content type and metadata from the file name, decide the supplier's
  document set, and say *before upload* which files are ready, incomplete, invalid or unmatched
- **an audit** of the live library: empty required fields, untyped files, stale check-outs, contracts expiring or
  expired, files without a document ID

Episode 1 covered list limits, indexes and version history limits; this episode doesn't repeat them.

| Path | What it is |
|---|---|
| [`src/MgDocMgmt.psm1`](src/MgDocMgmt.psm1) | The module: `New-MgContentTypeId`, `Test-MgContentTypeId`, `Test-MgDocDesign` (DM001–DM015), `Test-MgFilingPlan` (FP001–FP004), `Resolve-MgFilingPlan`, `ConvertTo-MgSiteColumnXml`, `Test-MgDocumentItem` (DA001–DA006), `Invoke-MgDocMgmtProvisioning`, `Invoke-MgFiling`, `Get-MgLibraryAudit` |
| [`src/docmgmt/supplier-documents.json`](src/docmgmt/supplier-documents.json) | The design: 8 site columns, 4 content types, features, the library |
| [`src/docmgmt/filing-plan.json`](src/docmgmt/filing-plan.json) | Two rules (contracts `CTR-…`, invoices `INV-…`), named groups = field names, `{Supplier}` = document set |
| [`src/bad/legacy-documents.json`](src/bad/legacy-documents.json) | Every common mistake in one design: the lint demo (8 errors, 7 warnings) |
| [`src/New-SampleDocuments.ps1`](src/New-SampleDocuments.ps1) | Writes nine fictional text files; expiry dates are relative to `-Today` |
| [`src/Invoke-DocumentManagement.ps1`](src/Invoke-DocumentManagement.ps1) | End to end: lint → filing plan → provision → file → live audit. `-WhatIf`, `-Audit`, `-IncludeIncomplete` |
| [`tests/MgDocMgmt.Tests.ps1`](tests/MgDocMgmt.Tests.ps1) | 31 Pester tests. The 6 tenant tests mock the **real** PnP cmdlets |

## Run it

```powershell
cd src
./Invoke-DocumentManagement.ps1 -DesignPath ./bad/legacy-documents.json            # 8 error(s), 7 warning(s)
./New-SampleDocuments.ps1 -Path ./sample-files
./Invoke-DocumentManagement.ps1 -DesignPath ./docmgmt/supplier-documents.json `
    -PlanPath ./docmgmt/filing-plan.json -FilesPath ./sample-files                  # No findings + 5 Ready, 1 Incomplete, 1 Invalid, 2 Unmatched
cd ..

Install-Module PnP.PowerShell, Pester -Scope CurrentUser   # PnP is optional: without it 6 tests are skipped
Invoke-Pester ./tests -Output Detailed                      # Tests Passed: 31, Failed: 0
```

Verified in this repo (Linux, PowerShell 7.6, Pester 6.2, PnP.PowerShell 3.5.0): **31 passed, 0 failed**
(without PnP.PowerShell: 25 passed, 6 skipped).

In the lab (needs tenant; site owner + site collection admin for the features; your own Entra app for PnP with
delegated permissions — see [episode 6](../../../../episodes/06-sharepoint-migration-pnp/setup/register-pnp-app.sh)):

```powershell
$site = 'https://contoso.sharepoint.com/sites/Purchasing'      # the episode 3 site
$app  = '00000000-0000-0000-0000-000000000000'
./src/Invoke-DocumentManagement.ps1 -DesignPath ./src/docmgmt/supplier-documents.json -PlanPath ./src/docmgmt/filing-plan.json `
    -FilesPath ./src/sample-files -SiteUrl $site -ClientId $app -WhatIf
./src/Invoke-DocumentManagement.ps1 -DesignPath ./src/docmgmt/supplier-documents.json -PlanPath ./src/docmgmt/filing-plan.json `
    -FilesPath ./src/sample-files -SiteUrl $site -ClientId $app -IncludeIncomplete
./src/Invoke-DocumentManagement.ps1 -DesignPath ./src/docmgmt/supplier-documents.json -Audit -SiteUrl $site -ClientId $app
```

## The rules

| Rule | Checks | Source |
|---|---|---|
| DM001 | Content type ID isn't `0x` + pairs of hex digits | Content Type IDs |
| DM002 | ID longer than 1,024 characters (512 bytes) | Content Type IDs |
| DM003 | ID doesn't start with the parent's ID (lineage); unknown parent | Content Type IDs |
| DM004 | Suffix is `00`, or `00` not followed by a 32-digit GUID | "the two hexadecimal values cannot be '00'" |
| DM005 | Direct child of a built-in type with a two-digit suffix (warning) | "use the GUID approach … if the parent content type is … a default content type" |
| DM006 | Duplicate content type name or ID | "A content type ID must be unique within a site collection" |
| DM007 | Content type uses a field that isn't a site column of the design; unsupported column type | design hygiene |
| DM008 | Document set content type with the Document Sets feature off | "To use Document Sets in a site collection, the Document Sets feature must be enabled" |
| DM009 | Document set allows an unknown content type or shares an unknown field | design hygiene |
| DM010 | Require check-out on (warning) | a checked-out document is locked and can't be co-authored |
| DM011 | Document IDs + content type hub (warning) | Document IDs aren't assigned unless the feature is on in the hub and types are republished |
| DM012 | Library content type unknown; default content type not in the library | design hygiene |
| DM013 | Required field with no library default and no filing rule (warning) | modern library uploads don't prompt for required columns |
| DM014 | Default value for a field the library doesn't have (warning) | design hygiene |
| DM015 | Site column without a fixed ID (warning) | house rule (re-runs) |
| FP001–FP004 | Plan: invalid regex; content type not in the library; named group that isn't a field; folder token that isn't a group | — |
| DA001 | Live item: required field empty | — |
| DA002 | Live item: content type isn't one of the library's (e.g. *Document*) | — |
| DA003 | Checked out and unchanged for more than 14 days | — |
| DA004 / DA005 | Contract expires within 60 days / has expired | — |
| DA006 | File without a document ID although the Document ID Service is on | — |

## Design choices
- **IDs are written down, not generated at run time.** The base type is `0x0101` + `00` + GUID (Learn's advice for
  children of built-in types); Contract and Invoice append `01` and `02`; the document set is `0x0120D520` + `00` +
  GUID. Every environment gets the same IDs, so content types match across sites. Site columns have fixed IDs too.
- **Inheritance does the work.** Supplier and Department live on *Purchasing Document*; Contract and Invoice inherit
  them. `Get-MgEffectiveField` computes the inherited, required set that both the lint and the audit use.
- **One document set per supplier.** Contracts and invoices of a supplier land in its *Supplier File*; Supplier is a
  shared field, so the set and its documents agree.
- **No generic *Document* type in the library.** Every upload gets a real type; Contract is the default.
- **Defaults for what a person can't type wrong.** Department defaults to Purchasing at the library root; everything
  the file name knows comes from the filing plan.
- **The plan runs before the upload.** Unmatched and invalid files are never uploaded; incomplete ones only with
  `-IncludeIncomplete` (we use it on camera to show the audit catching it).
- **Check-out not required.** The library is for co-authoring; versioning stays on (limits as in episode 1).
- **Idempotent and `-WhatIf`-able.** Existing columns, content types, field links, libraries, document sets and files
  are detected and left alone.

## What we learned / gotchas
- **"Required" doesn't mean filled in.** Learn documents that uploads to a modern library don't prompt for required
  columns, so files arrive without them. That's why DM013 checks every required field is covered by a default or a
  filing rule, and why the audit's DA001 exists.
- **Two hex digits are legal, but not for direct children of built-in types.** `0x010105` is a valid ID; Learn still
  recommends `00` + GUID there, so a future built-in type can't take the same ID. DM005 is a warning, not an error.
- **Learn's own examples are the best test data.** The `0x0101000728167cd9…` Financial Document hierarchy and the
  list content type ID from the Content Type IDs page are test cases; our generator must reproduce their shape.
- **Document IDs and the content type hub.** On a site that gets its content types from the hub, turning on the
  Document ID Service locally isn't enough (DM011, from the Learn troubleshooting article).
- **Euro isn't a country.** The Field schema's currency `LCID` table has no Portugal entry; the euro is the special
  value `-1` (symbol before) or `-2` (symbol after, as in "125 €"). Our first draft used 2070 (pt-PT); the currency
  columns now use `-2`.
- **StrictMode and empty objects.** `(...).PSObject.Properties.Name` on an empty `[pscustomobject]` throws under
  `Set-StrictMode -Version Latest`; the first lint run of the good design failed on a filing rule with no `values`.
  `| ForEach-Object Name` is safe.
- **Pipe binds in mocks.** `-ContentType` and `-List` arrive as pipe binds (compare `"$ContentType"`), `-Field` and
  `-DocumentSet` expose `.Name`, `-Folder` exposes `.ServerRelativeUrl`. The tests only work because the mocks
  copy the real PnP parameter types.
- **Not verified yet (lab recording):** that `Add-PnPContentType -ContentTypeId` under our own parent inherits the
  parent's field links in SharePoint Online (the design relies on it), that date-only values read back through CSOM
  give the expected days to expiry (they come back as UTC), and how long the Document ID Service takes to stamp new
  files. demo.md says what to check.

## References
- [Content Type IDs](https://learn.microsoft.com/previous-versions/office/developer/sharepoint-2010/aa543822(v=office.14)) — the two conventions, "cannot be 00", GUID approach for built-in parents, 512 bytes / 1,024 characters, unique within a site collection (page marked "available in SharePoint Online")
- [Create a content type (Microsoft Graph)](https://learn.microsoft.com/graph/api/site-post-contenttypes) — Document Set base ID `0x0120D520`
- [SPMT supported SharePoint site features](https://learn.microsoft.com/sharepointmigration/spmt-supported-site-features) — feature IDs DocId `B50E3104-…` and DocumentSet `3BAE86A2-…`
- [Plan document sets](https://learn.microsoft.com/sharepoint/governance/document-set-planning) — Document Sets feature must be enabled first (SharePoint Server guidance)
- [Document IDs aren't assigned to items in a document library](https://learn.microsoft.com/troubleshoot/sharepoint/lists-and-libraries/document-ids-unassigned) — content type hub scenario
- [You aren't prompted for required information when you upload a file](https://learn.microsoft.com/troubleshoot/sharepoint/lists-and-libraries/upload-file-using-new-experience) — modern library uploads and required columns
- [Plan versioning, content approval and check-out](https://learn.microsoft.com/sharepoint/governance/versioning-content-approval-and-check-out-planning) and [Overview of co-authoring](https://learn.microsoft.com/sharepoint/governance/co-authoring-overview) — check-out locks the document, prevents co-authoring (SharePoint Server guidance)
- [Field element (Field)](https://learn.microsoft.com/sharepoint/dev/schema/field-element-field) and [Currency element (Regional Settings)](https://learn.microsoft.com/sharepoint/dev/schema/currency-element-regional-settings) — field XML attributes, currency `LCID` (-1/-2 = euro)
- [PnP PowerShell](https://pnp.github.io/powershell/) — `Add-PnPContentType`, `Add-PnPFieldToContentType`, `Add-PnPContentTypeToDocumentSet`, `Set-PnPDocumentSetField`, `Add-PnPDocumentSet`, `Set-PnPDefaultColumnValues`, `Add-PnPFile -Values -ContentType`, `Get-PnPListItem -IncludeContentType`
- Blog: [Document Management — Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-03-18-document-management-complete-guide-2026/)
