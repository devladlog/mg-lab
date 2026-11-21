# DEVLADLOG Copilot & AI #5 - Copilot in Power Apps

Contoso's facilities team wants an **equipment loan** app. Copilot in Power Apps can create the Dataverse tables and a
canvas app from a sentence and write formulas in the formula bar. This episode records what it really does in the lab
environment `DEV`, what it needs, what it costs, and then does the part Copilot cannot do for you: **check the Power Fx it
wrote**, with a small tool you can run:

- `PowerFxReview` reads the formulas out of canvas app source (`*.pa.yaml`) or takes one you pasted, type-checks them with
  Microsoft's published Power Fx engine (NuGet `Microsoft.PowerFx.Core` and `.Interpreter`), applies a few extra rules, and
  can **run** a formula on sample rows.

Series plan: [`../../README.md`](../../README.md) (read "Licensing reality in the lab"). Shared lab: [`../../../LAB.md`](../../../LAB.md).
Previous: episode 4, [Copilot Studio: actions, agent flows and Dataverse](../04-copilot-studio-actions-agent-flows-and-dataverse/).
Next: episode 6, [Copilot in Power Automate](../06-copilot-in-power-automate/).
Category episodes this builds on: [Power Fx formulas and tips](../../../powerapps/episodes/03-power-fx-formulas-tips/),
[Dataverse integration](../../../powerapps/episodes/04-dataverse-integration/) and
[Build a canvas app from start to end](../../../powerapps/episodes/11-build-a-canvas-app-from-start-to-end/).

| Path | What it is |
|---|---|
| [`src/PowerFxReview/`](src/PowerFxReview) | .NET 8 console tool. `FormulaExtractor` (YAML), `ReviewContext` (tables, controls, variables, sample rows), `Reviewer` (engine check + rules), `Evaluator` (run), `Program` (CLI) |
| [`src/samples/Src/`](src/samples/Src) | `App.pa.yaml` and `ListScreen.pa.yaml`, **hand-written** in the documented `.pa.yaml` shape with 15 formulas, some wrong on purpose. Not Copilot output |
| [`src/samples/context.json`](src/samples/context.json), [`sample-data.json`](src/samples/sample-data.json) | What the formulas may name, and five fictional loans (dates relative to today) |
| [`tests/PowerFxReview.Tests/`](tests/PowerFxReview.Tests) | 40 xUnit tests |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (16 scenes, about 900 words) and the recording shot list, starting with `## Lab environment` |

## Rules of the checker

| Code | Severity | What |
|---|---|---|
| PF001 | error | Syntax error, unknown name or column (message of the Power Fx engine, with the fragment) |
| PF002 | error / warning | Result type does not fit the property: `Text` gets a table or record, `Items` gets a non-table (errors); `Visible` / `Required` get a non-boolean (warning). Only these four properties |
| PF003 | warning | E-mail address or GUID typed inside a string literal |
| PF004 | warning | A function Learn lists as nondelegable (`FirstN`, `Last`, `LastN`, `Choices`, `Concat`, `Collect`, `ClearCollect`, `GroupBy`, `Ungroup`, plus `Mid` and `Len` from Learn's example) used in a formula that names a data source |
| PF005 | warning | `Patch`, `Remove`, `RemoveIf`, `Update`, `UpdateIf`, `SubmitForm` (or `Collect` into a data source) in a behavior property (`On...`) with no `IfError` / `Errors`. A house rule of this tool, not a Learn requirement |
| PF006 | info | The formula uses a host function (`Navigate`, `Patch`, `Set`, a connector call ...): only syntax and names were checked |
| PF007 | info | `Filter` with several predicates: canvas accepts it, the standalone engine does not (see gotchas) |

Exit code: 1 when at least one formula has an error, 2 for a usage error, 0 otherwise.

## Run and test

```bash
cd series/copilot-ai/episodes/05-copilot-in-power-apps/tests/PowerFxReview.Tests
dotnet test -m:1                       # Passed: 40, Failed: 0 (first run restores NuGet packages, about 45 s)
cd ../../src/PowerFxReview
dotnet run -- review ../samples/Src --context ../samples/context.json
# 15 formulas: 5 clean, 4 with warnings, 5 partly checked, 3 with errors   (exit code 1)
dotnet run -- check 'Upper(txtSearch.Text)' --context ../samples/context.json
dotnet run -- run 'CountRows(Filter(Loans, IsBlank(ReturnedOn) && DueDate < Today()))' \
    --context ../samples/context.json --data ../samples/sample-data.json      # 2
```

Verified here: `dotnet test` 40 passed (.NET SDK 8.0.134, Linux, Power Fx 1.8.1). Not verified without the tenant: everything
Copilot and Studio do, and how the real `.pa.yaml` of a Copilot-built app checks (see `demo.md`, "Open points").
`bin/` and `obj/` were deleted after the test run.

## What we learned / gotchas

- **The standalone engine is not Studio.** Learn's `Filter` page says that with more than one formula "the results of all
  formulas are combined with the And function". The engine refuses it with *Use the And operator to combine multiple
  predicates*. The tool reports that as PF007 (info), not as an error, and then only checks syntax and names.
- **Host functions are recognised, not run.** `Navigate`, `Notify`, `Set`, `UpdateContext`, `Defaults` answer
  *'Navigate' is a recognized but not supported function*, `Patch` against a table reports invalid arguments, and
  connector calls like `Office365Outlook.SendEmailV2` are unknown. Such formulas get status `partial`; a typo elsewhere in
  them is still reported. Screens, `ScreenTransition` and `NotificationType` values are declared so `Navigate` and `Notify` arguments bind.
- **Names created by `Set` or `Collect` are not typed.** Declare them under `variables` in the context file to check where they are used.
- **Do not turn on `InvariantGlobalization`.** With it on, the engine throws `CultureNotFoundException: en is an invalid culture
  identifier` the first time it has to build an error message.
- **A colon in a one-line YAML formula breaks the file.** Learn (*Power Fx YAML formula grammar*): `#` and `:` are not allowed
  anywhere in a single-line formula. A record such as `{Status: "x"}` needs a `|` block. The tool reports the YAML error and exits 2.
- **Source files are read-only.** Learn: `*.pa.yaml` files "are read-only and should only be used to review changes made in
  Power Apps Studio" (editing is supported through Git integration). That fits a reviewer, not an editor.
- **Delegation.** Learn: a nondelegable query works on the first 500 records (limit up to 10,000). Studio shows a yellow
  triangle in most cases, but "not every nondelegable case shows this warning"; Live monitor shows what is really sent.
- **Copilot formula bar limits (Learn):** works on one control and property, does not take existing formula text into
  account, only default properties, no user-defined functions, no Power Apps-specific functions such as `Navigate()` in
  comment-generated formulas; explanation limit 5,000 characters; *Create a formula* is preview and English only.
- **Switches.** Generally available Copilot features are on and only Microsoft Support turns them off. Preview features:
  Power Platform admin center, environment, Settings, Features, **Copilot**; or tenant setting *Copilot in Power Apps (preview)*, which
  turns Copilot off for makers only. *Build apps through conversation* and *Describe a new table* are in Learn's data-movement
  table (not available in GCC): outside the US the environment may need **Move data across regions**; Europe uses the EU Data Boundary.
- **Licences.** Learn: no licence to build canvas apps; Dataverse use needs premium rights for users. *Microsoft Copilot in canvas apps*
  (preview, replaces the Copilot control) needs a Microsoft 365 Copilot licence, Dataverse Search and the tenant Dataverse setting.
  Apps built in Copilot Studio (GitHub Copilot harness) bill in Copilot Credits from the start of building. I found no Copilot
  Credit charge documented on the pages for the maker-side Copilot features used in the demo; the Copilot Credits Guide is the place to confirm.
- **Renamed or retiring (Learn, read 21 Nov 2026):** the *Copilot control* cannot be added to new canvas apps since 2 February 2026,
  *Microsoft Copilot in canvas apps* replaces it; *Notify* was called *ShowError*; the *Power Apps vibe experience* (preview) is limited
  to US, Australia, Asia and India, English only, and Learn now says app building is available in Copilot Cowork and will roll out to
  Microsoft Copilot Studio; *Plans* is generally available.
- `Today()` reads the machine clock, so the sample data uses `today-5`, `today+7` and so on.

## References
- Copilot and AI features in Power Apps: <https://learn.microsoft.com/power-apps/copilot-landing-page>
- Copilot in Power Apps overview: <https://learn.microsoft.com/power-apps/maker/canvas-apps/ai-overview>
- Build apps through conversation with Copilot: <https://learn.microsoft.com/power-apps/maker/canvas-apps/ai-conversations-create-app>
- Use Copilot to create and edit Power Fx formulas: <https://learn.microsoft.com/power-apps/maker/canvas-apps/ai-formulas-formulabar>
- Move data across regions for Copilots and generative AI features: <https://learn.microsoft.com/power-platform/admin/geographical-availability-copilot>
- Overview of plans: <https://learn.microsoft.com/power-apps/maker/plan-designer/plan-designer>
- Power Apps vibe experience (preview): <https://learn.microsoft.com/power-apps/vibe/overview>
- Apps in Microsoft Copilot Studio: <https://learn.microsoft.com/microsoft-copilot-studio/apps-experience/apps-overview>
- Add a Copilot control to a canvas app (preview): <https://learn.microsoft.com/power-apps/maker/canvas-apps/add-ai-copilot>
- Add Microsoft Copilot for app users in canvas apps (preview): <https://learn.microsoft.com/power-apps/maker/canvas-apps/microsoft-365-copilot-canvas-app>
- Create and edit canvas apps with AI code generation tools: <https://learn.microsoft.com/power-apps/maker/canvas-apps/create-canvas-external-tools>
- View source code files for canvas apps (`.pa.yaml`): <https://learn.microsoft.com/power-apps/maker/canvas-apps/power-apps-yaml>; schema: <https://github.com/microsoft/PowerApps-Tooling/blob/master/schemas/pa-yaml/v3.0/pa.schema.yaml>
- Power Fx YAML formula grammar: <https://learn.microsoft.com/power-platform/power-fx/yaml-formula-grammar>
- Export an `.msapp`: <https://learn.microsoft.com/power-apps/maker/canvas-apps/export-import-single-app>
- Delegation overview: <https://learn.microsoft.com/power-apps/maker/canvas-apps/delegation-overview>
- Filter, Back and Navigate, Notify: <https://learn.microsoft.com/power-platform/power-fx/reference/function-filter-lookup>, `.../function-navigate`, `.../function-showerror`
- Power Apps licensing FAQ: <https://learn.microsoft.com/power-platform/admin/powerapps-licensing-faq>
- Power Fx overview (the engine is published on GitHub and NuGet): <https://learn.microsoft.com/power-platform/power-fx/overview>
- This series has no devladlog.com Complete Guide; every fact above is from Microsoft Learn.
