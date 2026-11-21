# DEVLADLOG Power Apps #3 — Power Fx formulas and tips, as functions you can test

The **Equipment Desk (phone)** app from [episode 2](../02-canvas-apps-fundamentals/) gets a third screen: **Open loans**,
with an overdue count, an "overdue only" toggle, a colour per loan state, working days late, and a **Copy reminder**
button. The interesting part is where the logic lives: in `App.Formulas`, as **named formulas** and **user-defined
functions (UDFs)**, so every screen calls the same rules and the tests can call them too.

Power Fx tips covered, each with a test:

| Tip | Where |
|---|---|
| UDFs with typed parameters (`IsWorkingDay(d: Date): Boolean = ...`) and UDFs calling UDFs | `App.Formulas` |
| `Weekday(d, StartOfWeek.Monday)`: the default week starts on **Sunday** | `IsWorkingDay` |
| `Sequence` + `ForAll` + `CountIf` to count working days, with a holiday list (`d in Holidays`) | `WorkingDaysBetween` |
| `Switch(true, ...)` instead of nested `If`; `Switch(value, ...)` with a default | `LoanState`, `StateColor` |
| `With` for **scalars** only (a table in a `With` record silently loses delegation) | `lblLoanDetail`, lint |
| `Coalesce` treats blank **and** `""` the same | `lblLoanNotes` |
| String interpolation `$"...{expr}..."` and `Text(date, format, "en-GB")` so the result doesn't follow the user's language | `ReminderText` |
| A **behavior UDF** (`: Void = { ... }`) with `IfError` around `Copy()` | `CopyReminder` |
| Per-row maths in the gallery template, not `AddColumns` over the data source | `galLoans` |
| `CountIf` for an exact, delegable count | `OverdueCount` |

| Path | What it is |
|---|---|
| [`src/app/Src/App.pa.yaml`](src/app/Src/App.pa.yaml) | `App.Formulas`: 4 named formulas, 7 UDFs, 1 behavior UDF (episode 2's two named formulas are kept) |
| [`src/app/Src/LoansScreen.pa.yaml`](src/app/Src/LoansScreen.pa.yaml) | Summary label, toggle, delegable gallery, template labels and the reminder button |
| [`tests/EquipmentDesk.Formulas.Tests`](tests/EquipmentDesk.Formulas.Tests) | 39 xUnit test methods (208 cases with theory rows) on the open-source Power Fx interpreter |
| [`tests/EquipmentDesk.Formulas.Tests/Harness.cs`](tests/EquipmentDesk.Formulas.Tests/Harness.cs) | `RecalcEngine` with Dataverse-shaped tables, a **fixed clock** (Today() = Mon 30 Nov 2026), a user language, stubs for `Copy`/`Notify` |
| [`tests/EquipmentDesk.Formulas.Tests/CanvasSource.cs`](tests/EquipmentDesk.Formulas.Tests/CanvasSource.cs) | Reads `*.pa.yaml`; splits `App.Formulas` into definitions (handles `{ }` bodies and `$"...{...}..."`) |
| [`tests/schema/pa.schema.yaml`](tests/schema/pa.schema.yaml) | The official pa.yaml v3.0 schema (MIT, see [NOTICE](tests/schema/NOTICE.md)), same copy as episode 2 |

## Run the tests (no tenant needed)

```bash
cd tests
dotnet test EquipmentDesk.Formulas.Tests -m:1
# Passed!  - Failed: 0, Passed: 208, Skipped: 0, Total: 208 (.NET 8, Microsoft.PowerFx.Interpreter 1.8.1)
```

How the harness runs `App.Formulas`: named formulas are evaluated and stored as values (re-evaluated by `Recalc()` when a
test changes the clock or the data); all UDFs are added in one `AddUserDefinedFunction` call so they can call each other.
`Today()` comes from an injected clock, so "overdue" tests don't depend on the day you run them.

What the tests do and don't prove:
- **They prove** both files match the official schema, every UDF compiles with its declared types, every logic formula
  binds, and the results: working days across weekends and holidays, every loan state and colour, the singular/plural text,
  the reminder text in English for a Portuguese-language user, the copy success and failure paths, the gallery rows, the
  summary and the toggle.
- **They don't prove** delegation (only the real Dataverse connector decides: `DelegationLintTests` lints against Learn),
  layout, or that Studio accepts these exact UDF definitions and control type names. See [`demo.md`](demo.md).

## Build it in the lab (needs tenant)
Episode 2's app → **App → Formulas**: replace with the `Formulas` block from `App.pa.yaml` → add a blank screen
`LoansScreen` with the controls from `LoansScreen.pa.yaml` (right-click → **Paste code** per control, or by hand with the same
names) → add a button on `BrowseScreen` with `Navigate(LoansScreen)`. Then `pac canvas download` and copy `Src/App.pa.yaml`
and `Src/LoansScreen.pa.yaml` back here and re-run the tests (they find controls by name). Steps in [`demo.md`](demo.md).

## What we learned / gotchas

- **`Weekday()` starts on Sunday.** Learn: by default the result ranges from 1 (Sunday) to 7 (Saturday). `Weekday(d) <= 5`
  reads as "Monday to Friday" and means "Sunday to Thursday". Always pass `StartOfWeek.Monday`; a test pins both versions.
- **`With` hides a delegation problem.** Learn (delegation overview): "When you use With, UpdateContext, or Set, these
  functions create collections internally ... You don't see a delegation warning." So `With({ open: Filter(Loans, ...) }, ...)`
  quietly works on the first rows only. The test `In_memory_the_With_version_gives_the_same_rows...` shows why unit tests
  can't catch it, so there's a lint: no data source inside a `With` record.
- **`AddColumns` output is capped.** Learn (table shaping): the arguments delegate, but the output is "subject to the
  non-delegation record limit" (500 by default, up to 10,000). So the gallery is a plain delegable `Sort(Filter(...))` and
  the working-days maths runs in the template labels, only for the rows on screen.
- **`Today()` doesn't block delegation.** Learn: values that don't depend on a column, such as `Today()`, "are sent to the
  data source as a constant". `'Due date' < Today()` stays delegable.
- **`Text()` follows the user's language.** Without the third argument, `Text(due, "dddd d mmmm")` gives
  "segunda-feira 16 novembro" for a Portuguese user. The reminder is English, so `ReminderText` passes `"en-GB"`.
- **`Copy()` doesn't work everywhere.** Learn: embedded hosts (SharePoint, Power BI, Teams, ...) don't support it, and
  you should wrap it in `IfError`. `CopyReminder` does; a test simulates a host without clipboard access.
- **Coalesce and IsBlank treat `""` as blank** (Learn). Handy for a Notes column that's sometimes empty, sometimes `""`.
- **UDF limits** (Learn, App object): every parameter and the return value need a type, recursion isn't supported, and
  record parameters must not carry extra fields. A behavior UDF wraps its body in `{ }` and can return `Void`.
- **Open-source engine vs Power Apps** (found while building the harness, `Microsoft.PowerFx.Interpreter` 1.8.1):
  `GroupBy` is "recognized but not supported", the `[$-en-US]` language placeholder in a `Text` format is rejected (the
  third argument works), `Sequence(60000)` returns 60,000 rows although Learn limits `Sequence` to 50,000 in Power Apps,
  `AddUserDefinedFunction` doesn't accept named formulas (it asks for `:=`), and text is coerced to a `Date` parameter.
  We also didn't use `Summarize`: its Learn page doesn't list canvas apps under "Applies to".
- **Holidays as a named formula is a demo shortcut.** In production keep them in a Dataverse table and read them once.

## References
- [App object: Formulas (named formulas, user-defined functions, behavior UDFs, user-defined types)](https://learn.microsoft.com/power-platform/power-fx/reference/object-app)
- [Day, Month, Year, Weekday functions (StartOfWeek)](https://learn.microsoft.com/power-platform/power-fx/reference/function-datetime-parts)
- [DateAdd, DateDiff, TimeZoneOffset](https://learn.microsoft.com/power-platform/power-fx/reference/function-dateadd-datediff)
- [Sequence function (limited to 50,000 records)](https://learn.microsoft.com/power-platform/power-fx/reference/function-sequence)
- [ForAll function](https://learn.microsoft.com/power-platform/power-fx/reference/function-forall)
- [Blank, Coalesce, IsBlank, IsEmpty](https://learn.microsoft.com/power-platform/power-fx/reference/function-isblank-isempty)
- [Text function (language placeholder and result language tag)](https://learn.microsoft.com/power-platform/power-fx/reference/function-text)
- [Global support in Power Fx](https://learn.microsoft.com/power-platform/power-fx/global)
- [Copy function](https://learn.microsoft.com/power-platform/power-fx/reference/function-copy)
- [Error, IfError, IsError](https://learn.microsoft.com/power-platform/power-fx/reference/function-iferror)
- [AddColumns, DropColumns, RenameColumns, ShowColumns (delegation of the output)](https://learn.microsoft.com/power-platform/power-fx/reference/function-table-shaping)
- [Delegation overview (constants such as Today(); With/Set create collections)](https://learn.microsoft.com/power-apps/maker/canvas-apps/delegation-overview)
- [Delegable functions for Dataverse](https://learn.microsoft.com/power-apps/maker/canvas-apps/connections/connection-common-data-service#power-apps-delegable-functions-and-operations-for-dataverse)
- [Summarize function (Applies to)](https://learn.microsoft.com/power-platform/power-fx/reference/function-summarize)
- [View source code files for canvas apps (pa.yaml)](https://learn.microsoft.com/power-apps/maker/canvas-apps/power-apps-yaml)
- Power Fx interpreter: NuGet `Microsoft.PowerFx.Interpreter` 1.8.1 (open source, github.com/microsoft/Power-Fx)
- Blog: [Power Fx Formulas & Tips — Complete Guide](https://www.devladlog.com/articles/powerapps/2026-02-14-power-fx-formulas-tips-complete-guide-2026/)
