# DEVLADLOG SharePoint #2 — JSON formatting you can test

Column and view formatting is JSON, so it belongs in git, gets reviewed, and can be tested before anyone pastes it
into the **Format this column** pane. This episode formats the **Purchase Requests** list from
[episode 1](../01-lists-libraries-best-practices/) and builds the tooling to do that safely:

- four **column formats** (status pill, due date with overdue / due-soon, amount data bar, "that's me" requester)
  and one **view format** (overdue rows highlighted)
- **formatlint**, a small Python package that parses Excel-style expressions into the AST form documented on
  Microsoft Learn, **renders** a format for sample rows, and **lints** the rules the JSON schema can't check
  (allowed styles and attributes, unknown functions, link protocols, and fields that must be in the view)
- **Set-ListFormatting.ps1**, which lints, then applies the JSON with PnP PowerShell (`CustomFormatter`), and can
  export or reset what is live

| Path | What it is |
|---|---|
| [`src/formats/*.column.json`](src/formats/) | `status`, `due-date`, `amount`, `requester` column formats (schema v2) |
| [`src/formats/open-requests.view.json`](src/formats/open-requests.view.json) | View format: `additionalRowClass` for open, overdue requests |
| [`src/formats/map.json`](src/formats/map.json) | Which column/view gets which file, and **which fields each view shows** |
| [`src/formats/bad/`](src/formats/bad/) | A deliberately broken view format + a view without Status: the lint demo (10 errors, 3 warnings) |
| [`src/formatlint/expr.py`](src/formatlint/expr.py) | Tokenizer, Excel-style → AST parser, evaluator (dates as milliseconds, like the real thing) |
| [`src/formatlint/render.py`](src/formatlint/render.py) | Renders a column/view format for one row into a comparable tree |
| [`src/formatlint/lint.py`](src/formatlint/lint.py) | Rules FL001–FL010 (see below) |
| [`src/sample-rows.json`](src/sample-rows.json) | Six fictional requests and a fixed "now" (1 Dec 2026 09:00 UTC) |
| [`src/Set-ListFormatting.ps1`](src/Set-ListFormatting.ps1) | Lint → apply (`Set-PnPField`/`Set-PnPView -Values @{CustomFormatter=…}`), `-Export`, `-Reset`, `-WhatIf` |
| [`tests/`](tests/) | 62 pytest tests (parser, documented results, rendering, lint, Microsoft's JSON schemas) + 6 Pester tests |

## Run it

```bash
cd src
python3 -m formatlint lint formats/map.json                 # No findings.
python3 -m formatlint lint formats/bad/map.json             # 10 error(s), 3 warning(s)  (exit code 1)
python3 -m formatlint preview formats/map.json sample-rows.json --view "Open requests"
cd ..

pip install --user pytest jsonschema                         # jsonschema 4.18+ (uses 'referencing')
python3 -m pytest tests -q                                   # 62 passed
pwsh -c 'Invoke-Pester ./tests -Output Detailed'             # Tests Passed: 6 (5 skipped without PnP.PowerShell)
```

Verified here (Python 3.13, pytest 9.1, jsonschema 4.26, PowerShell 7.6, Pester 6.2, PnP.PowerShell 3.5.0):
**pytest 62 passed; Pester 6 passed**. The schema tests download Microsoft's schemas once into
`tests/.schema-cache/` (git-ignored) and are skipped when offline.

Apply to the lab list (needs tenant; the list from episode 1 must exist):

```powershell
./src/Set-ListFormatting.ps1 -SiteUrl https://contoso.sharepoint.com/sites/ListsDemo `
    -ClientId 00000000-0000-0000-0000-000000000000 -WhatIf
./src/Set-ListFormatting.ps1 -SiteUrl ... -ClientId ...                    # lint, then apply
./src/Set-ListFormatting.ps1 -SiteUrl ... -ClientId ... -Export ./backup   # what is live now
./src/Set-ListFormatting.ps1 -SiteUrl ... -ClientId ... -Reset             # default rendering again
```

## Lint rules

| Rule | Checks | Learn says |
|---|---|---|
| FL001 | `$schema` is the v2 column schema / a view schema | samples use the v2 column schema for SharePoint Online |
| FL002 | `elmType` is one of div, span, a, img, svg, path, button, p, filepreview | "Any other value will result in an error" |
| FL003 | attribute names (href, rel, src, class, target, title, role, iconName, d, aria, data-interception, viewBox, preserveAspectRatio, draggable) | "Any other attribute name will result in an error" |
| FL004 | style property is on the allowed list (`float` is no longer supported) | allowed style attributes list |
| FL005 | Excel-style expression parses; functions are known operators | operators list |
| FL006 | every `[$Field]` a format reads is in **every view that shows it** | "Reference to other fields will work only if they are included in the same view" |
| FL007 | `@currentField` in a view format (warning) | it "always resolves to the value of the Title field" there |
| FL008 | links start with http://, https://, mailto: or tel: | no other protocols |
| FL009 | `debugMode` left on (warning) | debugging only |
| FL010 | `additionalRowClass` next to a `rowFormatter` (warning) | it is ignored when a rowFormatter is present |

## What we learned / gotchas
- **A column format reads other fields only if the view shows them.** Our due-date format checks `[$RequestStatus]`
  so closed requests aren't red. Put Due date in a view without Status and the check has nothing to read. The map
  records each view's fields so FL006 catches it; the bad map's "Due dates only" view shows the failure.
- **Date-only vs `@now`.** Learn's simplest overdue sample is `[$DueDate] <= @now`. A date-only value has no time
  of day, so on the due date itself that comparison is already true in the morning (our test at 09:00 shows it).
  We add one day: `Number(@currentField) + 86400000 <= Number(@now)` means "the due day is over". Dates are
  milliseconds; adding 86,400,000 adds a day, as Learn documents. *Confirm with a row due today on the recording.*
- **Empty dates.** `Number('')` is 0, which is long overdue. Every date rule starts with `@currentField == ''`.
- **Microsoft's view schemas don't validate Learn's own example.** The schema URL Learn's view samples use points
  `additionalRowClass` at `…#definitions/expression` (missing `/`), which strict validators reject; the v2 view
  schema fixes the pointer but types `additionalRowClass` as an AST object only, so an Excel-style string fails. Our
  schema test validates everything else and checks that string with our parser. Both behaviours are tests.
- **`ConvertTo-Json` + PnP pipe binds.** The apply script stores compact JSON; in Pester mocks `-List` is a
  `ListPipeBind` (compare `"$List"`) and `-Identity` a `FieldPipeBind`/`ViewPipeBind` (`.Name` / `.Title`).
- **The local renderer is a harness, not SharePoint.** Dates are UTC, `toLocaleDateString()` is en-US, `forEach`
  isn't implemented, and a missing field raises instead of rendering empty. The real check is the lab demo.

## References
- [Use column formatting to customize SharePoint](https://learn.microsoft.com/sharepoint/dev/declarative-customization/column-formatting) — samples, `[$Field]`, `@now`, date math, `_x0020_`, predefined classes, supported column types
- [Formatting syntax reference](https://learn.microsoft.com/sharepoint/dev/declarative-customization/formatting-syntax-reference) — elmType, attributes, styles, operators, special values, "fields in the same view"
- [Use view formatting](https://learn.microsoft.com/sharepoint/dev/declarative-customization/view-formatting) and [List layout customizations](https://learn.microsoft.com/sharepoint/dev/declarative-customization/view-list-formatting) — `additionalRowClass`, `rowFormatter`, `@currentField` is Title
- [Field.CustomFormatter](https://learn.microsoft.com/dotnet/api/microsoft.sharepoint.client.field.customformatter?view=sharepoint-csom) and [View.CustomFormatter](https://learn.microsoft.com/dotnet/api/microsoft.sharepoint.client.view.customformatter?view=sharepoint-csom) — the properties the script sets
- [Upgrading from XSLT to list formatting — PnP provisioning](https://learn.microsoft.com/sharepoint/dev/sp-add-ins-modernize/from-xslt-to-list-formatting#pnp-provisioning-and-json-formatting) — formatters travel as `CustomFormatter`
- Schemas: `https://developer.microsoft.com/json-schemas/sp/v2/column-formatting.schema.json`, `.../sp/view-formatting.schema.json`, `.../sp/v2/view-formatting.schema.json`
- Blog: [JSON Formatting — Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-04-13-json-formatting-complete-guide-2026/)
