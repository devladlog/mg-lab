# DEVLADLOG Power Apps #1 — Model-driven apps, built for real

**Equipment Desk** is a small model-driven app for lending Contoso laptops, monitors and phones. We build it twice over:
the **data model and the app shell from code** (Dataverse Web API, re-runnable), and the **form behaviour in TypeScript**
(a unit-tested form script). Then we open the result in the app designer and the running app.

- Two tables: **Equipment** (asset tag, category, serial number, status, purchase date) and **Loan** (equipment lookup,
  borrower email, loan date, due date, returned on, notes). Deleting a device with loan history is **restricted**.
- An app module **Equipment Desk** with a site map (one area, one group, both tables), validated with `ValidateApp`
  and published with `PublishXml`; optionally granted to a security role.
- A form script on the Loan form: defaults for new loans (today, due in 14 days), **blocking** field errors (due before
  loan date, more than 90 days, returned before the loan or in the future), an **overdue / due soon / returned** banner,
  fields locked once the device is back, and an automatic loan name.

| Path | What it is |
|---|---|
| [`src/model/equipmentDesk.ts`](src/model/equipmentDesk.ts) | The model as plain data: publisher, solution, tables, columns, lookup, app |
| [`src/provision/metadata.ts`](src/provision/metadata.ts) | Pure builders: model → `EntityDefinitions`, `Attributes`, `RelationshipDefinitions`, site map XML, app module, `PublishXml` |
| [`src/provision/dataverse.ts`](src/provision/dataverse.ts) | Small Web API client (about 80 lines); `fetch` is injected (tests and `--dry-run` never touch the network) |
| [`src/provision/provision.ts`](src/provision/provision.ts) | The run: publisher → solution → tables → columns → relationship → (web resource) → app → site map → components → validate → publish → (role). Each step checks first, so re-runs create nothing new |
| [`src/formscripts/loanRules.ts`](src/formscripts/loanRules.ts) | Pure loan rules (dates, limits, state, name) — no `Xrm` |
| [`src/formscripts/loanForm.ts`](src/formscripts/loanForm.ts) | The form script: `onLoad` wires the OnChange events and calls `refresh` |
| [`src/tests/`](src/tests) | 38 `node:test` tests (rules, form script against a fake `formContext`, payloads, provisioning order/idempotency/errors, bundle) |

## Run and test (no tenant needed)

Node 22.18 or later runs the TypeScript directly (type stripping), so there is no compile step for tests.

```bash
cd src
npm ci --no-audit --no-fund
npm run typecheck        # tsc --noEmit, strict, with @types/xrm
npm test                 # node --test: 38 passed, 0 failed
npm run build            # esbuild → dist/contoso_/scripts/loanform.js (IIFE, global Contoso.LoanForm, ~6 KB)
npm run plan             # dry run: prints the 39 Web API requests (19 writes) it would send to an empty environment
```

## Provision a real environment (needs tenant)

You need System Administrator or System Customizer in the target environment (Learn: required to create apps).

```bash
export DATAVERSE_URL=https://<your-dev-org>.crm4.dynamics.com
export DATAVERSE_TOKEN=$(az account get-access-token --resource $DATAVERSE_URL --query accessToken -o tsv)
npm run build
node provision/provision.ts --webresource dist/contoso_/scripts/loanform.js --role "Basic User"
```

Then, in the Loan main form: **Events → On Load → + Event handler**, library `contoso_/scripts/loanform.js`,
function `Contoso.LoanForm.onLoad`, **Pass execution context as first parameter** checked. Save and publish.
Only OnLoad is registered in the designer; the script attaches the OnChange handlers itself (`addOnChange`).

This path has **not yet run against the lab tenant**: everything above the Web API is unit-tested, the Web API
shapes are copied from the Learn articles in References, and [`demo.md`](demo.md) tells the recorder what to check.

## What we learned / gotchas

- **Date columns are UserLocal unless you say otherwise.** Learn: if you don't specify the behavior the column is created
  `UserLocal`, and "Date only" format with User local behavior can show a different day to users in other time zones.
  We send `DateTimeBehavior: DateOnly` for every date column — and once a column is DateOnly you can't change it back.
- **DateOnly in the form script is midnight in the browser's time zone.** Read it with `getFullYear/getMonth/getDate`, not the
  UTC getters (Learn: behavior-format-date-time-field, Examples). We count days through `Date.UTC(y, m, d)` so a 23-hour
  day at the March daylight-saving change still counts as one day; there's a test pinned to `Europe/Lisbon`.
- **App unique name: letters and numbers only, the prefix is added for you.** Our first dry run sent `contoso_EquipmentDesk`
  and looked for `contoso_contoso_EquipmentDesk`. Now `appModulePayload` rejects anything that isn't `[A-Za-z0-9]+`.
- **New apps and site maps are unpublished**, and a plain `GET appmodules` only returns published apps, so the "does it exist"
  checks go through `RetrieveUnpublishedMultiple()`.
- **A control notification blocks Save** (Learn: `setNotification`). Good for real errors; the overdue banner uses
  `setFormNotification` instead, which informs without blocking.
- **`XrmEnum.FormType.Create` doesn't exist at runtime.** `@types/xrm` declares it as an ambient `const enum`; esbuild and
  Node's type stripping compile files one at a time and can't inline it. We use the literal `1` with a comment.
- **Node's type stripping rejects parameter properties and enums** (`constructor(private x)`), so the client uses plain fields
  (`erasableSyntaxOnly` in `tsconfig.json` catches it at typecheck time).
- **Licensing:** every user who runs a model-driven app needs a Power Apps premium licence, and makers need a licence to
  build one (Learn: Power Apps licensing FAQ). Microsoft has announced stricter enforcement for model-driven apps from
  February 2027.

## References
- [Create, manage, and publish model-driven apps using code](https://learn.microsoft.com/power-apps/developer/model-driven-apps/create-manage-model-driven-apps-using-code)
- [Create and update table definitions using the Web API](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/create-update-entity-definitions-using-web-api)
- [Create and update column definitions using the Web API](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/create-update-column-definitions-using-web-api)
- [Create and update table relationships using the Web API](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/create-update-entity-relationships-using-web-api)
- [Web API table schema operations sample (publisher and solution)](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/web-api-metadata-operations-sample)
- [Site Map (SiteMap) table reference](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/sitemap)
- [Web Resource table reference (type 3 = Script)](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/webresource)
- [Behavior and format of the date and time column](https://learn.microsoft.com/power-apps/maker/data-platform/behavior-format-date-time-field)
- [Configure date and time behavior using code](https://learn.microsoft.com/power-apps/developer/data-platform/behavior-format-date-time-attribute)
- [Client API form context (Xrm.Page deprecated)](https://learn.microsoft.com/power-apps/developer/model-driven-apps/clientapi/clientapi-form-context)
- [setNotification](https://learn.microsoft.com/power-apps/developer/model-driven-apps/clientapi/reference/controls/setnotification)
- [Write your first client script](https://learn.microsoft.com/power-apps/developer/model-driven-apps/clientapi/walkthrough-write-your-first-client-script)
- [Power Apps licensing FAQs](https://learn.microsoft.com/power-platform/admin/powerapps-licensing-faq)
- [Power Apps Developer Plan (developer environment deprecation)](https://learn.microsoft.com/power-platform/developer/plan)
- Blog: [Model-Driven Apps — Complete Guide](https://www.devladlog.com/articles/powerapps/2026-02-10-model-driven-apps-complete-guide-2026/)
