# DEVLADLOG SharePoint #3 — Modern sites and pages, as code

A modern SharePoint site is two things: the **site** (regional settings, branding, navigation, lists, sharing) and the
**pages** people read. Both can live in git. In this episode the Contoso purchasing team gets a communication site
whose configuration is a **site template** (site scripts in JSON) and whose pages are **page designs** (JSON), and a
small PowerShell module that:

- **lints** the site script and the pages before anything exists: documented verbs only, the 30/300-action and
  100,000-character limits, re-run safety (field IDs), actions that only work on communication sites or are blocked
  on channel sites, section/column layouts, and the Page Diagnostics baselines for iframes and search requests
- optionally validates every action against **Microsoft's published site script schema**
- **registers** the template with PnP PowerShell (idempotent), **applies** it asynchronously and reads back **what
  each action actually did**
- **provisions the pages** section by section, publishes them and sets the home page
- **exports** a site script from a site someone built by hand, so it can be linted and kept

It builds on the fictional Contoso purchasing scenario from [episode 1](../01-lists-libraries-best-practices/) (the
Purchase Requests list) and [episode 2](../02-json-formatting/) (its formatting): this is the site people land on.

| Path | What it is |
|---|---|
| [`src/MgSitePages.psm1`](src/MgSitePages.psm1) | The module: `Test-MgSiteScript` (SS000–SS011), `Test-MgPageDesign` (PG001–PG009), `Test-MgSiteTemplate`, `Invoke-MgSiteTemplateRegistration`, `Invoke-MgSiteTemplateApply`, `Get-MgSiteTemplateRunReport`, `Invoke-MgPageProvisioning`, `Export-MgSiteScript` |
| [`src/purchasing/template.json`](src/purchasing/template.json) | The template manifest: title, web template (CommunicationSite = 68), site scripts, pages, home page |
| [`src/purchasing/purchasing.site-script.json`](src/purchasing/purchasing.site-script.json) | 11 actions: regional settings (pt-PT, 24-hour), compact header + mega menu + footer, external sharing off, a Purchasing FAQ list with ID'd fields and a default view, three navigation links |
| [`src/purchasing/pages/`](src/purchasing/pages/) | `purchasing-home` (Home layout: text, News, the FAQ list), `how-to-buy` (article), `news-approval-limits` (promoted as news) |
| [`src/bad/`](src/bad/) | A team-site template with every common mistake: the lint demo (10 errors, 9 warnings) |
| [`src/Invoke-ModernSite.ps1`](src/Invoke-ModernSite.ps1) | End to end: lint → register (admin) → create site (optional) → apply async → wait → run report → pages. `-WhatIf`, `-RunReport`, `-ExportFrom` |
| [`tests/MgSitePages.Tests.ps1`](tests/MgSitePages.Tests.ps1) | 40 Pester tests. The 9 tenant tests mock the **real** PnP cmdlets; 4 schema tests use Microsoft's schema |

## Run it

```powershell
cd src
./Invoke-ModernSite.ps1 -TemplatePath ./purchasing/template.json        # No findings.
./Invoke-ModernSite.ps1 -TemplatePath ./bad/template.json               # 10 error(s), 9 warning(s)
cd ..

Install-Module PnP.PowerShell, Pester -Scope CurrentUser   # PnP is optional: without it 9 tests are skipped
Invoke-Pester ./tests -Output Detailed                      # Tests Passed: 40, Failed: 0
```

Verified in this repo (Linux, PowerShell 7.6, Pester 6.2, PnP.PowerShell 3.5.0): **40 passed, 0 failed**
(without PnP.PowerShell: 31 passed, 9 skipped). The schema tests download
`https://developer.microsoft.com/json-schemas/sp/site-design-script-actions.schema.json` once into
`tests/.schema-cache/` (delete it to refresh; skipped when offline). Lint with the schema too:
`./Invoke-ModernSite.ps1 -TemplatePath ./purchasing/template.json -SchemaPath ../tests/.schema-cache/site-script.schema.json`.

In the lab (needs tenant; SharePoint admin for the template, your own Entra app for PnP with delegated permissions —
see [episode 6](../../../../episodes/06-sharepoint-migration-pnp/setup/register-pnp-app.sh)):

```powershell
$admin = 'https://contoso-admin.sharepoint.com'
$site  = 'https://contoso.sharepoint.com/sites/Purchasing'
$app   = '00000000-0000-0000-0000-000000000000'
./src/Invoke-ModernSite.ps1 -TemplatePath ./src/purchasing/template.json -AdminUrl $admin -SiteUrl $site -ClientId $app -CreateSite -WhatIf
./src/Invoke-ModernSite.ps1 -TemplatePath ./src/purchasing/template.json -AdminUrl $admin -SiteUrl $site -ClientId $app -CreateSite
./src/Invoke-ModernSite.ps1 -RunReport -AdminUrl $admin -SiteUrl $site -ClientId $app
./src/Invoke-ModernSite.ps1 -ExportFrom https://contoso.sharepoint.com/sites/HandBuilt -ClientId $app
```

## The rules

| Rule | Checks | Source |
|---|---|---|
| SS000 | Action doesn't validate against Microsoft's site script schema (one finding per action, with the reason) | published JSON schema (optional, `-SchemaPath`) |
| SS001 | Unknown verb, or a verb in the wrong place (subaction at top level, `subactions` under a verb that has none). Case-sensitive | "Only the verb actions listed here can be used; otherwise, an 'unable to handle action' error" |
| SS002 | More than 300 actions or 100,000 characters | site template overview |
| SS003 | More than 30 actions: too many for a synchronous `Invoke-SPOSiteDesign`; apply asynchronously | site template overview |
| SS004 | `addSPField`/`createSiteColumn` without `id`, field XML without `ID` (re-runs can duplicate the field) | JSON schema page |
| SS005 | `setTitle` inside `createSPList` (the list can no longer be updated on re-apply) | JSON schema page |
| SS006 | `templateType` not in the supported list (100–109, 119, 1100) | JSON schema page |
| SS007 | `setSiteLogo` on anything but a communication site (error); `navigationLayout` on a team site (warning) | JSON schema page |
| SS008 | `addSiteColumn` / `addContentType` referencing something the script doesn't create (warning) | JSON schema page |
| SS009 | `hubSiteId`, solution `id`, `featureId` not a GUID (error) or the empty GUID (warning) | JSON schema page |
| SS010 | `locale` isn't a real LCID (checked with .NET `CultureInfo`) | — |
| SS011 | Actions automatically blocked on channel sites (template 69) | site template overview |
| PG001 | Unknown page layout or section template | PnP `PageLayoutType` / `CanvasSectionTemplate` |
| PG002 | Control in a column the section doesn't have (vertical sections add one) | — |
| PG003 | Full-width section on a team site | "Modern pages in communication sites offer an additional section layout named Full-width column" |
| PG004 | Unknown web part type | PnP `DefaultWebPart` |
| PG005 | Iframe web parts (Embed, File viewer): 1–2 warning, 3+ error | Page Diagnostics: "three or more web parts using iFrames" = Attention required |
| PG006 | More than 3 search-driven web parts (Events, Highlighted content) | "Modern site pages should contain no more than 3 search requests" |
| PG007 | Page name isn't lowercase words and hyphens (it becomes the file name and URL) | house rule |
| PG008 | Empty section | house rule |
| PG009 | Duplicate page names; home page not among the pages | design hygiene |

## Design choices
- **Site script for the site, PnP for the pages.** Site scripts have no verb for page content, so the template
  configures the site and `Invoke-MgPageProvisioning` builds the pages with `Add-PnPPage`, `Add-PnPPageSection`,
  `Add-PnPPageTextPart`, `Add-PnPPageWebPart`, `Set-PnPPage -Publish` and `Set-PnPHomePage`.
- **Asynchronous apply.** `Add-PnPSiteDesignTask` is the path Learn gives the 300-action limit (like the UI);
  synchronous `Invoke-SPOSiteDesign` is capped at 30. Our script has 11, but the template will grow.
- **Read back the run.** The actions run in the background, so "queued" isn't "done". `Get-PnPSiteDesignRun` +
  `Get-PnPSiteDesignRunStatus` show the outcome per action, and the script prints them after the apply.
- **Every field has an ID.** Learn recommends it so re-applying the template updates instead of duplicating; the
  IDs in the purchasing script are random GUIDs generated for this sample.
- **New home page, not an edited one.** The communication site's own `Home.aspx` stays; `purchasing-home` is created
  and set as the home page, so re-runs never touch a page someone edited by hand. Existing pages are skipped unless
  `-Force` (then recreated).
- **Tokens for tenant values.** The List web part needs the list's GUID; the page design says
  `{listid:Purchasing FAQ}` and provisioning resolves it with `Get-PnPList`.
- **Regional settings for Portugal.** Locale 2070 (pt-PT), time zone 2 (Greenwich Mean Time, Learn's sample value),
  sort order 25 (the value in Learn's exported example), 24-hour clock.

## What we learned / gotchas
- **Microsoft's schema and Learn's verb list disagree.** `enableApprovals` is documented on Learn but isn't in the
  published schema; the schema has `addFile`, `addFolder`, `setDocumentTemplates`, `setFooterLogo` and others that
  the Learn page doesn't describe. The linter accepts both lists; a test pins the drift so we notice when it changes.
- **The schema requires more than the docs show.** `addSPField` and `createSiteColumn` need `isRequired`,
  `createContentType` needs `hidden`, `setRegionalSettings` needs `sortOrder`, `installSolution` needs `name`.
- **Learn's own samples aren't strict JSON.** The `setRegionalSettings` and `addPrincipalToSPGroup` samples contain
  `/* comments */`; paste them as-is and `ConvertFrom-Json` or the upload will fail. A test shows it.
- **Schema errors are noisy.** The schema is one big `anyOf`, so one bad action produced dozens of errors from
  `Test-Json`. We validate each action against its own definition and keep one finding per action.
- **The mocks caught a scoping bug.** The list-ID resolver was a `GetNewClosure()` scriptblock; that bound it to a
  new dynamic module, so the mocked `Get-PnPList` was bypassed and the real one ran ("You are not signed in"). Without
  the closure it runs in the module's scope. We only saw it because the tests mock the real PnP cmdlets.
- **`$home` is `$HOME`.** A variable named `$home` in a module is the read-only automatic variable; we renamed it.
- **Not verified yet (lab recording):** the List web part property names (`isDocumentLibrary`, `selectedListId`), the
  order in which `Get-PnPSiteDesignRun` returns runs (we report the first; the template ID filters it), and whether
  the three `Connect-PnPOnline -DeviceLogin` sign-ins can share one token. demo.md says what to check.

## References
- [SharePoint site template and site script overview](https://learn.microsoft.com/sharepoint/dev/declarative-customization/site-design-overview) — 30 (sync) / 300 actions or 100,000 characters (async), 100 scripts and 100 templates per tenant, WebTemplate 64/1/68/69, channel-site blocked actions, non-destructive re-runs
- [Site template JSON schema](https://learn.microsoft.com/sharepoint/dev/declarative-customization/site-design-json-schema) — verbs, `id` on fields, `setTitle` note, supported `templateType` values, `setSiteLogo` (68 only), navigation layout, regional settings
- [Site design and site script REST API — GetSiteScriptFromWeb](https://learn.microsoft.com/sharepoint/dev/declarative-customization/site-design-rest-api#getsitescriptfromweb) — exported example (sort order 25)
- [Site design: PnP PowerShell cmdlets](https://learn.microsoft.com/sharepoint/dev/declarative-customization/site-design-pnppowershell) and [Get-SPOSiteDesignRunStatus](https://learn.microsoft.com/powershell/module/microsoft.online.sharepoint.powershell/get-spositedesignrunstatus) — run status per action
- [Use web parts with the full-width column](https://learn.microsoft.com/sharepoint/dev/spfx/web-parts/basics/use-web-parts-full-width-column) — full-width column on communication sites
- [Optimize iFrames in SharePoint modern pages](https://learn.microsoft.com/microsoft-365/enterprise/modern-iframe-optimization) and [Optimize search requests](https://learn.microsoft.com/microsoft-365/enterprise/modern-search-optimization) — Page Diagnostics baselines, group-level caching on Events and Highlighted content
- [Use the Page Diagnostics for SharePoint tool](https://learn.microsoft.com/microsoft-365/enterprise/page-diagnostics-for-spo)
- Schema: `https://developer.microsoft.com/json-schemas/sp/site-design-script-actions.schema.json`
- [PnP PowerShell](https://pnp.github.io/powershell/) — `Add-PnPSiteScript`, `Add-PnPSiteDesign`, `Add-PnPSiteDesignTask`, `Get-PnPSiteDesignRun(Status)`, `Get-PnPSiteScriptFromWeb`, `New-PnPSite`, page cmdlets
- Blog: [Modern Sites & Pages — Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-03-15-modern-sites-pages-complete-guide-2026/)
