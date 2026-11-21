# DEVLADLOG SharePoint #6 — Search and metadata, as code

The Supplier Documents library from [episode 4](../04-document-management/) has good metadata: supplier, expiry date,
invoice date, department. Search still can't answer "which contracts expire in the next 60 days?" or "show me
everything from Fabrikam, by supplier". The metadata is there; the search schema isn't. In this episode the Contoso
Purchasing site gets:

- **a managed metadata term set with fixed IDs** (*Purchasing Categories*), a **Category** column on the episode 4
  content types, and every file tagged from its supplier
- **a search plan**: which site column goes into which *default unused* refinable managed property, under which alias,
  linted against Learn's rules for SharePoint in Microsoft 365 (you can't create refinable properties, only reuse
  `RefinableString00`–`219`, `RefinableDate00`–`19`, …)
- **a KQL linter** that knows the plan's property types: white space around `:`, lowercase `and`, ranges on text
  properties, dates that aren't ISO 8601, leading wildcards, unknown properties, unclosed quotes, length limits
- **search tests**: real queries with expected results, run with `Submit-PnPSearchQuery` after the schema is mapped
  and the library re-indexed, plus a check of the site collection's mappings with `Get-PnPSearchConfiguration`

Permissions were [episode 5](../05-permissions-governance/); this episode doesn't touch them.

| Path | What it is |
|---|---|
| [`src/MgSearchMeta.psm1`](src/MgSearchMeta.psm1) | The module: `Get-MgAutoPropertyName`, `Get-MgManagedPropertyInfo`, `Test-MgTermSet` (TX001–TX003), `Test-MgSearchPlan` (SP001–SP007, TX004–TX005), `ConvertTo-MgKql`, `Test-MgKql` (KQ001–KQ010), `Test-MgSearchMapping` (SM001–SM003), `Test-MgSearchResult`, `Invoke-MgTaxonomyProvisioning`, `Invoke-MgCategoryColumn`, `Invoke-MgCategoryTagging`, `Get-MgSiteSearchMapping`, `Invoke-MgSearchTest` |
| [`src/search/purchasing-categories.termset.json`](src/search/purchasing-categories.termset.json) | Term group *Contoso Purchasing*, term set *Purchasing Categories*: 5 terms, 9 child terms, all with fixed GUIDs |
| [`src/search/search-plan.json`](src/search/search-plan.json) | Columns, 4 mappings (Supplier → `RefinableString00` alias `PurchSupplier`, PurchDepartment → `RefinableString01` `PurchDept`, ExpiryDate → `RefinableDate00` `PurchExpiry`, InvoiceDate → `RefinableDate01` `PurchInvoiceDate`), the Category column, supplier → category |
| [`src/search/search-tests.json`](src/search/search-tests.json) | 6 search tests with expected results for the episode 4 sample files, plus the lint-only "gotcha" query. Tokens: `{site}`, `{today+60d}`, `{ct:Contract}`, `{term:Facilities}` |
| [`src/bad/bad-search-plan.json`](src/bad/bad-search-plan.json) | A plan with the usual mistakes: the lint demo (5 errors, 3 warnings) |
| [`src/bad/bad-queries.json`](src/bad/bad-queries.json) | Seven real-world queries, one KQL mistake each (4 errors, 3 warnings) |
| [`src/Invoke-SearchMetadata.ps1`](src/Invoke-SearchMetadata.ps1) | End to end: lint → `-Provision` (term set, column, tagging) → `-CheckMapping` → `-Reindex` → `-RunTests`. `-WhatIf` |
| [`tests/MgSearchMeta.Tests.ps1`](tests/MgSearchMeta.Tests.ps1) | 31 Pester tests. The 6 tenant tests mock the **real** PnP cmdlets |

## Run it

```powershell
cd src
./Invoke-SearchMetadata.ps1 -PlanPath ./bad/bad-search-plan.json                          # 5 error(s), 3 warning(s)
./Invoke-SearchMetadata.ps1 -PlanPath ./search/search-plan.json -TestsPath ./bad/bad-queries.json   # 4 error(s), 3 warning(s)
./Invoke-SearchMetadata.ps1 -PlanPath ./search/search-plan.json -TermSetPath ./search/purchasing-categories.termset.json `
    -TestsPath ./search/search-tests.json                                                  # 0 error(s), 0 warning(s); the gotcha query shows KQ005
cd ..

Install-Module PnP.PowerShell, Pester -Scope CurrentUser   # PnP is optional: without it 6 tests are skipped
Invoke-Pester ./tests -Output Detailed                      # Tests Passed: 31, Failed: 0
```

Verified in this repo (Linux, PowerShell 7.6, Pester 6.2, PnP.PowerShell 3.5.0): **31 passed, 0 failed**
(without PnP.PowerShell: 25 passed, 6 skipped).

In the lab (needs tenant; Term Store admin for the term set, site collection admin for the column, the search schema
and the re-index; your own Entra app for PnP with delegated permissions):

```powershell
$site = 'https://contoso.sharepoint.com/sites/Purchasing'     # the episode 3 site, with the episode 4 library filed
$app  = '00000000-0000-0000-0000-000000000000'
$p = @{ PlanPath = './src/search/search-plan.json'; TermSetPath = './src/search/purchasing-categories.termset.json'
           TestsPath = './src/search/search-tests.json'; SiteUrl = $site; ClientId = $app }
./src/Invoke-SearchMetadata.ps1 @p -Provision -WhatIf
./src/Invoke-SearchMetadata.ps1 @p -Provision
# map the four properties in Site settings > Search Schema (demo.md), then:
./src/Invoke-SearchMetadata.ps1 @p -CheckMapping -Reindex
# after the next crawl:
./src/Invoke-SearchMetadata.ps1 @p -RunTests
```

## Licensing (what each part needs)

| Feature used | Licence | Notes |
|---|---|---|
| Managed metadata (term store, managed metadata column) | SharePoint (any plan; the lab's Microsoft 365 E5) | Term Store admin (SharePoint admin center → Term store) to create the group and terms |
| Search schema at site collection level, re-index, KQL, `Submit-PnPSearchQuery` | SharePoint (any plan) | Site collection admin for *Site settings → Search Schema* |
| Not used: term set import in SKOS format, autofill / taxonomy tagging | SharePoint Premium (pay-as-you-go) | Learn: SKOS import needs a pay-as-you-go licence; this episode creates terms with PnP instead |

## The rules

| Rule | Checks | Source |
|---|---|---|
| TX001 | Group, term set or term ID isn't a GUID, is empty, or is used twice | fixed IDs: house rule |
| TX002 | Same label twice at one level (case ignored) | SKOS reference: unique default label per level |
| TX003 | Empty label | — |
| TX004 | Category column bound to another term set; supplier mapped to a path that isn't a term | — |
| TX005 | Term set not available for tagging (warning) | — |
| SP001 | Target isn't a default unused managed property, or is out of its range (e.g. `RefinableString250`) | "Refinable Managed Properties cannot be created"; unused property table |
| SP002 | Column type doesn't fit the property type (a date into `RefinableString…`) | unused property table (types) |
| SP003 | One managed property used for two columns | — |
| SP004 | Alias with characters other than letters and digits (warning) | "Consider using only letters and digits in managed property names" |
| SP005 | Alias equal to an existing managed property (built-in, unused, or the column's automatic property) | "ensure a managed property with the same name as the alias does not already exist" |
| SP006 | `refine: true` on a property that can't refine (`Date00`–`09`, `Int00`–`49`, …) (warning) | unused property table |
| SP007 | Crawled property name doesn't match the column type (warning) | automatically created properties naming |
| KQ001 | Empty, or only operators | "If the KQL query contains only operators or is empty, it isn't valid" |
| KQ002 | `and` / `or` / `not` in lowercase (warning) | "operators are case-sensitive (uppercase)" |
| KQ003 | White space before or after the property operator | "must not include white space … or the property restriction is treated as a free-text query" |
| KQ004 | Property that isn't a known managed property or alias (warning) | "You must specify a valid managed property name" |
| KQ005 | `<` `>` `<=` `>=` `..` on a Text or Yes/No property | operator table: DateTime, Integer, Decimal, Double only |
| KQ006 | Wildcard at the start of a term (warning) | "KQL queries don't support prefix matching with the wildcard * as prefix" |
| KQ007 | Date that isn't `YYYY-MM-DD[Thh:mm:ss[.fffffff][Z]]` or a reserved keyword | date formats, UTC; `today`, `this month`, … |
| KQ008 | Longer than 4,096 (error) or 2,048 (warning; error with `-FrontEnd`); a restriction longer than 2,048 | length limits |
| KQ009 | Unclosed quote, unbalanced parentheses | — |
| KQ010 | `=` combined with `*` (warning) | "We do not recommend combining the = operator together with asterisk" |
| SM001–SM003 | Live: plan mapping missing; alias missing; extra crawled properties mapped (warning) | — |

## Design choices
- **Terms have fixed IDs.** The same term set in every tenant, and queries can name a term by ID (`{term:Facilities}`)
  without looking it up. Terms are created with PnP (`New-PnPTerm -Id`, `Add-PnPTermToTerm -Id`), not by CSV import
  (Learn: the term store tool's import fails above 5,000 terms; SKOS import needs a pay-as-you-go licence).
- **Tag from what you already know.** The supplier is filled in by the episode 4 filing plan; the category comes from
  the supplier. `SystemUpdate` keeps the files' *Modified* dates.
- **Map at site collection level, verify with code.** Learn recommends tenant-level mapping for consistency; we map
  on the Purchasing site collection only, so the lab tenant stays clean. The mapping is done in the browser (with
  cmdlets it means importing a search configuration XML with `Set-PnPSearchConfiguration`) and
  `Get-PnPSearchConfiguration -Scope Site -OutputFormat ManagedPropertyMappings` proves it's right.
- **Aliases, not RefinableStringNN, in queries.** `PurchExpiry<{today}` reads like the business question; the plan
  remembers it's `RefinableDate00`.
- **Search tests are tests.** Expected counts and file names, run after every schema change. The gotcha query is
  `lintOnly`: it documents the mistake without running it.

## What we learned / gotchas
- **Automatically created managed properties are text.** Learn's reference for automatically created properties
  (written for SharePoint Server) says they're all of type Text, so `ExpiryDateOWSDATE<2027-01-01` can't work: KQL
  ranges need DateTime, Integer, Decimal or Double. Map the crawled property to `RefinableDate00` instead.
- **You can't create a refinable property in SharePoint in Microsoft 365.** New managed properties are Text or Yes/No
  only and can't refine or sort; reuse the unused ones and give them an alias. Learn's table lists 220 `RefinableString`
  properties (00–219) and 20 `RefinableDate` (00–19).
- **An alias can shadow a real property.** Learn warns that aliases take precedence; SP005 checks the alias against
  built-in names, unused names and the column's own automatic property.
- **Nothing changes until the content is crawled again.** Changing the schema doesn't re-crawl the library; request a
  re-index (`Request-PnPReindexList`), once, after all mapping changes: Learn warns it can put a massive load on search.
- **Auto-generated managed properties are case-sensitive** when you read them through REST (Learn). The plan uses
  aliases everywhere.
- **PowerShell: `"$type:"` isn't `$type` followed by a colon.** In a double-quoted string `$type:` is parsed as a
  scope-qualified variable and the module failed to load; it's `${type}:` now.
- **PowerShell: an empty array passed to an untyped parameter arrives as `$null`.** Under `Set-StrictMode` the
  term-tree recursion then read `.name` of `$null` on every leaf; the loop now filters `$null`.
- **Not verified yet (lab recording):** which crawled property SharePoint Online lists for each column
  (`ows_q_DATE_ExpiryDate` or `ows_ExpiryDate`; the plan accepts both and records the one picked), that
  `owstaxIdPurchCategory:"GPP|#<id>"` returns the child terms' files in SharePoint Online (documented for SharePoint
  Server), that `Set-PnPListItem -Values @{ PurchCategory = '<term id>' }` sets a taxonomy value, the refiner row keys
  (`RefinerName`, `RefinementName`) in PnP's result tables, and how long the re-index takes. demo.md says what to check.

## References
- [Manage the search schema in SharePoint](https://learn.microsoft.com/sharepoint/manage-search-schema) — auto-generated properties, aliases (and the precedence warning), "Refinable Managed Properties cannot be created", Text/Yes-No only for new properties, letters and digits, site collection schema page, default unused managed properties table, re-index and its load, case-sensitive auto-generated properties
- [Overview of crawled and managed properties in SharePoint Online](https://learn.microsoft.com/sharepoint/crawled-and-managed-properties-overview) and [in SharePoint Server](https://learn.microsoft.com/sharepoint/technical-reference/crawled-and-managed-properties-overview) — built-in properties and types (Author, ContentTypeId, Filename, IsDocument, LastModifiedTime, Path, …)
- [Automatically created managed properties](https://learn.microsoft.com/sharepoint/technical-reference/automatically-created-managed-properties-in-sharepoint) — `ows_q_<CODE>_`, `ows_r_`, `ows_taxId_`, `<Name>OWS<CODE>`, `owstaxId<Name>`, all of type Text, `GP0|#` / `GPP|#` / `GTSet|#` (SharePoint Server reference)
- [Keyword Query Language (KQL) syntax reference](https://learn.microsoft.com/sharepoint/dev/general-development/keyword-query-language-kql-syntax-reference) — operators, white space, length limits, operator/type table, date formats and keywords, wildcards
- [Introduction to managed metadata](https://learn.microsoft.com/sharepoint/managed-metadata) and [Create and manage terms](https://learn.microsoft.com/sharepoint/create-and-manage-terms)
- ["Not all terms were imported successfully"](https://learn.microsoft.com/troubleshoot/sharepoint/search/troubleshoot-error-when-importing-a-term-set) — the term store import tool and 5,000 terms
- [Import a term set using SKOS](https://learn.microsoft.com/microsoft-365/documentprocessing/import-term-set-skos) and [SKOS format reference](https://learn.microsoft.com/microsoft-365/documentprocessing/skos-format-reference) — pay-as-you-go licence; unique label per level
- [PnP PowerShell](https://pnp.github.io/powershell/) — `New-PnPTermGroup`, `New-PnPTermSet`, `New-PnPTerm`, `Add-PnPTermToTerm`, `Add-PnPTaxonomyField`, `Add-PnPFieldToContentType -UpdateChildren`, `Set-PnPListItem -UpdateType SystemUpdate`, `Get-PnPSearchConfiguration -OutputFormat ManagedPropertyMappings`, `Request-PnPReindexList`, `Submit-PnPSearchQuery`
- Blog: [Search & Metadata — Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-03-29-search-metadata-complete-guide-2026/)
