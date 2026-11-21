# DEVLADLOG Microsoft 365 #14 — Microsoft Forms & Data Collection

**Forms has no response API, so the design is: Form (by hand) → flow (by hand) → SharePoint list (as code) → analysis (as code).**
Learn's Forms connector page lists one trigger (*When a new response is submitted*) and two actions (*Get form details*, *Get response
details*): there is no public API to create a form or to read its responses. So this episode builds what *can* be code. One file
([`src/form.json`](src/form.json)) describes the questions; the module creates the **SharePoint list** that receives the responses through
Microsoft Graph, prints the **mapping** the Power Automate flow must follow, then reads the list back and finds **data-quality problems**
and summarises the answers. The demo builds the real form and the real flow in the lab tenant, so the screens show the product doing the real
thing. The scenario continues episode 13: a pulse survey about the Microsoft 365 Apps rollout.

1. **Spec** — `Get-FDSpec` refuses an http site URL, column names that are not plain internal names or that collide with built-in or response
   columns, duplicate columns/choices, unknown types, a rating without bounds, bad `maxLength`/thresholds.
2. **List as code** — `ConvertTo-FDListBody` / `ConvertTo-FDColumn`: question types → Graph `columnDefinition` facets (`text`, `choice`,
   `number`, `dateTime`, `boolean`), plus the response columns `ResponseId` (required, indexed, **unique**), `Responder`, `Submitted`.
3. **Provision** — `Set-FDList`: site by path, list by name; **creates the list, or adds only the missing columns**; an existing column that
   differs is reported as drift and **never** changed or deleted; honours `-WhatIf`.
4. **Flow mapping** — `Get-FDFlowMap`: column → type → the value the flow's *Create item* must send.
5. **Read** — `Get-FDResponse`: `items?expand=fields`, paged.
6. **Findings** — `Get-FDResponseFinding`: `DuplicateResponseId`, `MissingRequired`, `InvalidChoice`, `OutOfRange`, `NotANumber`,
   `LowRatingNoComment`, `PossibleDoubleSubmit`, `AnonymousResponder`, `ResponseIdGap`; thresholds come from the spec.
7. **Summary** — `Get-FDSummary` + `ConvertTo-FDMarkdown`: answers per choice, rating average and distribution, yes/no, responses per day.

Same fictional tenant as episodes 1–13 (`contoso`); lab users `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo`. The list
items in the tests are fictional, planted with nine problems, and **never** appear in the demo.

| Path | What it is |
|---|---|
| [`src/form.json`](src/form.json) | The form as data: site URL (placeholder), list name, six questions with types and rules, audit thresholds |
| [`src/FormsData/FormsData.psm1`](src/FormsData/FormsData.psm1) | The module: spec validation, Graph bodies, provision, flow map, paging, findings, summary, markdown |
| [`src/FormsData/FormsData.psd1`](src/FormsData/FormsData.psd1) | Module manifest |
| [`src/Invoke-FormsData.ps1`](src/Invoke-FormsData.ps1) | Runner: `-Validate`, `-FlowMap`, `-ListBody`, `-Provision [-WhatIf]`, `-Analyze [-ItemsFile]` |
| [`tests/FormsData.Tests.ps1`](tests/FormsData.Tests.ps1) | 48 Pester tests (Graph mocked with a small fake SharePoint site) |
| [`tests/fixtures/items.json`](tests/fixtures/items.json) | Fictional list items in the Graph `items?expand=fields` shape: duplicates, gaps, bad values, a double submit, an anonymous response |
| [`sample/list-body.json`](sample/list-body.json) · [`sample/responses-report.md`](sample/responses-report.md) | Generated offline from `form.json` and the fixture |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and the shot list |

## Run the tests

```bash
cd series/microsoft-365/episodes/14-microsoft-forms-data-collection
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Tests Passed: 48, Failed: 0, Skipped: 0
```

Produced in this repo's container (PowerShell 7.6, Pester 6.2.0). PSScriptAnalyzer (Warning and Error) reports 0 issues on `src/`.
`Microsoft.Graph.Authentication` is not installed here: the tests use a stub with the documented parameter names (`Invoke-MgGraphRequest`),
so the real module's parameter binding was **not** checked in this episode.

## Run it

```powershell
cd src
# Offline (no tenant)
./Invoke-FormsData.ps1 -Validate
./Invoke-FormsData.ps1 -FlowMap
./Invoke-FormsData.ps1 -ListBody -OutFile ../sample/list-body.json
./Invoke-FormsData.ps1 -Analyze -ItemsFile ../tests/fixtures/items.json -Now 2026-11-25T12:00:00Z -OutFile ../sample/responses-report.md

# Needs tenant (see demo.md): copy form.json to form.lab.json and put the real site URL in it
./Invoke-FormsData.ps1 -SpecFile ./form.lab.json -Provision -WhatIf    # Graph: Sites.Read.All + Sites.Manage.All
./Invoke-FormsData.ps1 -SpecFile ./form.lab.json -Provision
./Invoke-FormsData.ps1 -SpecFile ./form.lab.json -Analyze               # Graph: Sites.Read.All
```

## Licensing and permissions (Learn)

| Feature | Needs |
|---|---|
| Microsoft Forms | Included in Microsoft 365 Business Basic/Standard/Premium, Apps for enterprise, and Enterprise E1/E3/E5 (Learn: *Set up Microsoft Forms*) |
| Forms connector in Power Automate | **Standard** class connector; works only with organizational accounts |
| Create the list and add columns (`POST /sites/{id}/lists`, `/columns`) | `Sites.Manage.All` (delegated and application, Learn) |
| Read site, lists, columns, items | `Sites.Read.All` |
| Admin settings for Forms | Microsoft 365 admin center > Settings > Org settings > Services > Microsoft Forms; an office apps administrator with the application administrator role (Learn) |

## What we learned / gotchas

- **There is no Forms response API.** Learn's connector page: one trigger and the actions *Get form details* / *Get response details*.
  The module therefore does not "call Forms"; it prepares the destination and checks it. (We did not search for unofficial endpoints.)
- **Group forms are not in the connector's drop-down.** Learn: paste the Form Id manually, only the part after `FormId=` in the address bar.
  Personal forms appear in the list.
- **Throttling.** Learn: 300 calls per connection per 60 seconds. A burst of responses is queued by the flow, but a very busy form
  with several flows on the same connection can be throttled.
- **Unique `ResponseId`.** A flow can run twice (retry, a second flow) or not at all. The `ResponseId` column is required, indexed and
  unique (`enforceUniqueValues` is a documented `columnDefinition` property), so a duplicate write is rejected, and `ResponseIdGap` lists
  numbers with no row. Learn does **not** promise that response ids are consecutive, so a gap is `Info`: it can be a deleted response.
  Whether Graph accepts these flags on a column created together with the list is **not verified** (demo.md, screen 1).
- **Columns are only added.** `Set-FDList` never updates or deletes a column that exists: that could lose answers. Learn documents
  update and delete for columns; the module reports drift instead.
- **Multi-select.** A Graph `choiceColumn` has `displayAs` `checkBoxes | dropDownMenu | radioButtons` and no separate "multiple" flag in the
  Learn page: we use `checkBoxes` for multi-select questions. What the Forms connector sends for a multi-select answer, and what the *Create item*
  column accepts, is **not verified** (the findings code accepts an array or a single string). Forms question types such as Likert, ranking,
  file upload (stored in the form owner's OneDrive) and Net Promoter Score are not modelled: **rating** is the closest (a number with bounds).
- **Limits (Learn, *Set up Microsoft Forms*).** For Microsoft 365 business and education: up to 200 forms, up to 50,000 responses per form; if you need
  more, export to Excel and clear. A list in SharePoint has its own limits (not covered here).
- **Admin settings (Learn).** External sharing has four options, all checked by default; *Record names by default* is on; *Internal phishing
  protection* is on; *Include Bing search, YouTube videos* is on. Forms runs automated reviews that can temporarily block a form from collecting
  responses for suspected phishing; global/security admins get notifications (the Message Center Privacy Reader role is needed for security
  admins), and Defender XDR shows the alerts. Learn also says these admin settings are "only available for Office 365 Education and Microsoft 365
  Apps for business customers": the demo checks what the lab tenant really shows.
- **Data location and retention (Learn).** Forms data is stored in the US except for European tenants (stored in Europe); account-related data
  is deleted 30 days after the user account is deleted from Entra ID. Responses copied into SharePoint are then governed by the site, not by Forms:
  the tear-down deletes them on purpose.
- **Names.** *Responders' Email* is the dynamic content Learn names for the responder; the exact name of the submission time output is not on the
  pages we checked: the mapping says "check the designer".
- **Not verified here (needs tenant, see [demo.md](demo.md))**: acceptance of `required`/`indexed`/`enforceUniqueValues` on create; multi-select
  columns; that Graph returns the same choices and bounds we sent (drift check); the real shape of Forms answers in the flow; whether a flow turned off
  misses responses.

Not covered (to keep the episode to 6 minutes): Forms branching, quizzes and grading, Forms Pro / Dynamics 365 Customer Voice, Copilot in Forms,
Excel workbooks and *Open in Excel*, group forms and ownership transfer, sensitivity labels and retention on forms, the audit log for Forms activities,
Power Apps and Power BI on the list.

## References

- [Microsoft Forms connector (triggers, actions, limits, throttling)](https://learn.microsoft.com/connectors/microsoftforms/) · [Overview of flows with Microsoft Forms](https://learn.microsoft.com/power-automate/forms/overview) · [Common ways to use a form in a flow](https://learn.microsoft.com/power-automate/forms/popular-scenarios)
- [Set up Microsoft Forms (licences, limits)](https://learn.microsoft.com/microsoft-forms/set-up-microsoft-forms) · [Administrator settings for Microsoft Forms](https://learn.microsoft.com/microsoft-forms/administrator-settings-microsoft-forms) · [Admin information (phishing, audit)](https://learn.microsoft.com/microsoft-forms/admin-information) · [Review and unblock forms blocked for potential phishing](https://learn.microsoft.com/microsoft-forms/review-unblock-forms-users-detected-blocked-potential-phishing) · [Forms and user accounts (data location)](https://learn.microsoft.com/microsoft-forms/microsoft-forms-user-accounts)
- [Create a list (Graph)](https://learn.microsoft.com/graph/api/list-create?view=graph-rest-1.0) · [columnDefinition](https://learn.microsoft.com/graph/api/resources/columndefinition?view=graph-rest-1.0) · [choiceColumn](https://learn.microsoft.com/graph/api/resources/choicecolumn?view=graph-rest-1.0) · [numberColumn](https://learn.microsoft.com/graph/api/resources/numbercolumn?view=graph-rest-1.0) · [dateTimeColumn](https://learn.microsoft.com/graph/api/resources/datetimecolumn?view=graph-rest-1.0) · [textColumn](https://learn.microsoft.com/graph/api/resources/textcolumn?view=graph-rest-1.0)
- [Get a site by path](https://learn.microsoft.com/graph/api/site-getbypath?view=graph-rest-1.0) · [List items](https://learn.microsoft.com/graph/api/listitem-list?view=graph-rest-1.0) · [Working with SharePoint sites in Graph](https://learn.microsoft.com/graph/api/resources/sharepoint?view=graph-rest-1.0)
- Blog: [Microsoft Forms & Data Collection — Complete Guide](https://www.devladlog.com/articles/office-365/2025-06-08-forms-data-collection-complete-guide-2025/)
