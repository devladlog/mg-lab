# DEVLADLOG Power Apps #2 — Canvas apps fundamentals, with tested formulas

**Equipment Desk (phone)** is a two-screen canvas app on the same Dataverse tables as [episode 1](../01-model-driven-apps/):
search the devices, tap one, lend it. Small on purpose, so we can cover the fundamentals properly: screens and controls,
a Dataverse data source, a **delegable** gallery formula, validation, **named formulas**, writing data with `Collect`/`Patch`,
and error handling that tells the truth.

The app is kept as **source code** (`*.pa.yaml`, the format Power Apps Studio writes into every `.msapp`), and its formulas are
**executed in tests** with Microsoft's open-source Power Fx interpreter against in-memory tables shaped like the Dataverse tables.

| Path | What it is |
|---|---|
| [`src/app/Src/App.pa.yaml`](src/app/Src/App.pa.yaml) | `StartScreen` and the named formulas `DefaultLoanDays = 14`, `MaxLoanDays = 90` |
| [`src/app/Src/BrowseScreen.pa.yaml`](src/app/Src/BrowseScreen.pa.yaml) | Search box, "available only" toggle, gallery with a delegable `Items` formula |
| [`src/app/Src/LendScreen.pa.yaml`](src/app/Src/LendScreen.pa.yaml) | Borrower email, two date pickers, one error label, Lend/Cancel; `OnSelect` with an `IfError` pair per write |
| [`tests/EquipmentDesk.Canvas.Tests`](tests/EquipmentDesk.Canvas.Tests) | 52 xUnit tests: schema validation, formula binding, gallery, validation, save paths, delegation lint |
| [`tests/EquipmentDesk.Canvas.Tests/Harness.cs`](tests/EquipmentDesk.Canvas.Tests/Harness.cs) | `RecalcEngine` with Dataverse-like tables (display names, local choices `'Status (Equipment)'`), stubs for `Navigate`/`Back`/`Notify` |
| [`tests/schema/pa.schema.yaml`](tests/schema/pa.schema.yaml) | The official pa.yaml v3.0 JSON schema Learn links to (MIT, see [NOTICE](tests/schema/NOTICE.md)) |

## Run the tests (no tenant needed)

```bash
cd tests
dotnet test EquipmentDesk.Canvas.Tests -m:1      # Passed! Failed: 0, Passed: 52, Total: 52 (.NET 10)
```

What the tests do and don't prove:
- **They prove** every file matches the official schema, control names are unique, every logic formula (`Items`, `Text`,
  `OnSelect`, `Default`, `DefaultDate`, `DisplayMode`, `HintText`) binds against the Dataverse-shaped tables, and the
  formulas return the right results — search, toggle, sort, every validation message, the save path and both failure paths.
- **They don't prove** delegation (only the real connector decides; `DelegationTests` is a lint against Learn's Dataverse
  table), layout, or that Studio accepts the hand-written control type names (`Label`, `Classic/TextInput`, `Gallery`, ...).
  See [`demo.md`](demo.md): the recorder builds the app in Studio and replaces these files with the exported source.

## Build it in the lab (needs tenant)
Dataverse tables from episode 1 → new blank **phone** canvas app → add data sources **Equipment** and **Loans** → create
`BrowseScreen` and `LendScreen` → set the formulas from the `.pa.yaml` files (or paste a control's YAML with **Paste code**,
Learn: "Use code view for canvas app controls") → **Settings → General → Data row limit = 1** while testing delegation.
Afterwards `pac canvas download --name "Equipment Desk (phone)" -d <dir>` (Learn: "View source code files") and copy
`Src/*.pa.yaml` over `src/app/Src`, then re-run the tests: they look controls up by name, so they keep working.

## What we learned / gotchas

- **`;` doesn't stop on an error.** Our first `OnSelect` was `IfError(Collect(...); Patch(...); Notify("Loan saved"); Back(), Notify(error))`.
  When the second write failed, the test showed *"Loan saved"*, then `Back()`, then the error. Learn (IfError): "The second
  Patch ... will be attempted even if the Patch to DS1 fails." Fix: one `IfError` **pair** per write, success last.
  The test `Chained_formulas_keep_going_after_an_error...` keeps the first version as evidence.
- **Two writes are not a transaction.** If the loan is saved and the device update fails (user can create loans but not
  write Equipment), the loan stays. The app now says *"Loan saved, but the device status wasn't updated"* instead of
  pretending. For a hard guarantee, move the status change server-side (a plug-in like episode 4 of MG Lab, or a flow).
- **Delegation:** if any part of a query can't be delegated, Power Apps works on the first **500** rows (Data row limit,
  max **10,000**) and only shows a warning. For Dataverse, `Filter`, `StartsWith`, `Search` and `in` on text, `=`/`<>` on
  choices, `Sort` on one column delegate; `Text(column)`, `Len`, `Trim` don't. Learn's tip: set the limit to **1** while testing.
- **Local choices are named `'Column (Table plural)'`**, e.g. `'Status (Equipment)'.Available` (Learn: "Category (Accounts)").
- **The official v3.0 schema has a broken regex.** `CodeComponent-ComponentName` has an unbalanced `)`; JsonSchema.Net refuses to
  load the schema. We patch that one pattern in memory, and a test fails the day Microsoft fixes it.
- **The open-source Power Fx 1.8.1 engine rejects `Filter(T, a, Status = X)`** with "Use the And operator to combine multiple
  predicates": it reads a second argument that starts with `Column =` as a named argument. We combine with `&&`. (Not
  checked in Studio, which may accept the comma form.)
- **Named formulas over `OnStart`:** Learn reports Studio load times dropping "by as much as 80%" when `App.OnStart` variables
  move to `App.Formulas`; named formulas are evaluated only when needed and can't be changed with `Set`.
- **Licensing:** building canvas apps needs no licence; running this one does — Dataverse makes it a premium app, so every
  user needs a Power Apps premium licence (Learn: licensing FAQ). On SharePoint lists the same app would be standard.
- **pa.yaml is read-only source.** Learn: the files are "used to review changes made in Power Apps Studio" and aren't used when
  the app loads; external editing is supported only with Power Platform Git integration. Treat these files as reviewable,
  testable source, and Studio (or Git integration) as the way changes get into the app.

## References
- [View source code files for canvas apps (pa.yaml)](https://learn.microsoft.com/power-apps/maker/canvas-apps/power-apps-yaml)
- [Use code view for canvas app controls (copy/paste YAML)](https://learn.microsoft.com/power-apps/maker/canvas-apps/code-view)
- [Delegation and query limits](https://learn.microsoft.com/power-apps/maker/canvas-apps/delegation-overview)
- [Delegable functions for Dataverse](https://learn.microsoft.com/power-apps/maker/canvas-apps/connections/connection-common-data-service#power-apps-delegable-functions-and-operations-for-dataverse)
- [Error, IfError, IsError functions](https://learn.microsoft.com/power-platform/power-fx/reference/function-iferror)
- [App object: Formulas (named formulas) and OnStart](https://learn.microsoft.com/power-platform/power-fx/reference/object-app)
- [Build large and complex canvas apps (App.Formulas instead of App.OnStart)](https://learn.microsoft.com/power-apps/maker/canvas-apps/working-with-large-apps)
- [Choices in canvas formulas: 'Category (Accounts)'](https://learn.microsoft.com/power-apps/maker/canvas-apps/use-native-cds-connector)
- [StartsWith / EndsWith](https://learn.microsoft.com/power-platform/power-fx/reference/function-startswith)
- [Power Apps licensing FAQs](https://learn.microsoft.com/power-platform/admin/powerapps-licensing-faq)
- Power Fx interpreter: NuGet `Microsoft.PowerFx.Interpreter` 1.8.1 (open source, github.com/microsoft/Power-Fx)
- Blog: [Canvas Apps Fundamentals — Complete Guide](https://www.devladlog.com/articles/powerapps/2026-02-06-canvas-apps-fundamentals-complete-guide-2026/)
