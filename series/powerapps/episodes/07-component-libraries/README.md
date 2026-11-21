# DEVLADLOG Power Apps #7 — Component libraries: build it once, update it everywhere

The Equipment Desk app had a hand-made title label on every screen, a hand-made confirm prompt nowhere (so nothing asked
before a change), and its colour rule (`StateColor`) as a UDF that only that one app could use. This episode moves those
pieces into a **component library**, **Equipment Desk Kit**, and rebuilds episode 6's **Open loans** screen with it:

- **DeskHeader** — data in (`Title`, `ShowBack`, `Accent`), one **event** out (`OnBack`). The app decides what "back" means.
- **ConfirmDialog** — `OnConfirm` / `OnCancel` events and no data at all. The new **Returned** button only remembers the loan;
  the dialog asks; the app's `OnConfirm` does the two `Patch` calls.
- **DeskRules** — no controls, only **output function** properties: `StateColor(state)` (moved out of `App.Formulas`) and
  `TagIsValid(tag)` (used by episode 8's barcode scanner). The gallery rows call `deskRules.StateColor(...)`.

Why these shapes? Learn: components in a library "can never access app scope", data sources can't be saved with components,
flows in component libraries aren't supported, and "you can't insert a component into a gallery or a form". So the library
holds look and logic, and the app keeps the data.

| Path | What it is |
|---|---|
| [`src/library/Src/Components/DeskHeader.pa.yaml`](src/library/Src/Components/DeskHeader.pa.yaml) | Header: 3 inputs with defaults, `OnBack` event, back icon 88 x 88 with `AccessibleLabel` and `TabIndex` 0 |
| [`src/library/Src/Components/ConfirmDialog.pa.yaml`](src/library/Src/Components/ConfirmDialog.pa.yaml) | Scrim, panel, title, message, Cancel/Confirm; `Destructive` paints confirm red; scrim tap = cancel |
| [`src/library/Src/Components/DeskRules.pa.yaml`](src/library/Src/Components/DeskRules.pa.yaml) | Two `OutputFunction` properties with typed parameters |
| [`src/library/Src/LibraryTestScreen.pa.yaml`](src/library/Src/LibraryTestScreen.pa.yaml) | The library's own test screen (Learn: screens in a library are for testing only) |
| [`src/app/Src/LoansScreen.pa.yaml`](src/app/Src/LoansScreen.pa.yaml) | Episode 6's screen with `hdrLoans`, `deskRules`, `btnReturn`, `dlgReturn` (library instances: `Control: CanvasComponent`) |
| [`src/app/Src/App.pa.yaml`](src/app/Src/App.pa.yaml) | Episode 5's `App.Formulas` without `StateColor` |
| [`tests/EquipmentDesk.Components.Tests`](tests/EquipmentDesk.Components.Tests) | 109 xUnit tests on the open-source Power Fx interpreter |
| [`tests/EquipmentDesk.Components.Tests/Harness.cs`](tests/EquipmentDesk.Components.Tests/Harness.cs) | Hosts the components: instance inputs as a record named after the definition, events dispatched to the instance's handler, output functions compiled as UDFs |
| [`tests/schema/pa.schema.yaml`](tests/schema/pa.schema.yaml) | The official pa.yaml v3.0 schema (MIT, see [NOTICE](tests/schema/NOTICE.md)), same copy as episodes 2 and 3 |

## Run the tests (no tenant needed)

```bash
cd tests
dotnet test EquipmentDesk.Components.Tests -m:1
# Passed!  - Failed: 0, Passed: 109, Skipped: 0, Total: 109 (.NET 10, Microsoft.PowerFx.Interpreter 1.8.1)
```

What the groups prove:
- **SourceTests**: every library and app file is valid against the official schema (which has `ComponentDefinitions`,
  `CustomProperties`, `PropertyKind: Event/OutputFunction` and `ComponentLibraryUniqueName`); names are unique; every UDF and
  output function compiles; every logic formula binds — app controls, instance properties (handlers included) and the formulas
  *inside* each component (with its inputs in scope); the call rewrite touches nothing but component function calls.
- **LibraryRulesTests** (Learn's rules as lints): `AllowCustomization` set (and off) on every library component, no
  `AccessAppScope`, at most 20 components, no data source / flow / `UpdateContext` / `Patch` in library formulas, no code
  components, **no component instance inside a gallery or form** (with a test that the lint catches a status badge in a row),
  every `Definition.Property` reference is declared, inputs have defaults, events return `None`, **each output function binds
  in an empty engine** (Learn: function properties can't read variables or component properties) plus a test that this check
  fails when it should, instances only set Input/Event properties, one valid library unique name.
- **ComponentTests**: header defaults and the Loans header; back raises `OnBack` and two instances handle it differently;
  dialog texts, defaults and the red destructive button; Cancel, scrim and Confirm each raise their event; `StateColor` gives
  episode 3's four colours; `TagIsValid` accepts whole tags only; the library test screen shows the functions working.
- **AppTests**: Returned opens the dialog and changes nothing; Confirm closes the loan (30 Nov 2026), frees the device, closes the
  dialog, the overdue count drops and the row leaves the gallery; Cancel and a scrim tap change nothing; a user who can't write
  Loans gets the error and the device stays on loan; if only the device update fails the app says so; `StateColor` left
  `App.Formulas` and every colour formula uses `deskRules`.

We checked the tests bite: making Confirm raise `OnCancel` and changing one colour's alpha fails 6 tests.

What they **don't** prove: that Studio accepts these hand-written definitions exactly (control type names, `ReturnType: None`,
the library unique name), how Studio hosts components (the harness rewrites `inst.Prop(` to `inst__Prop(` because Power Fx names
can't contain dots, see `Harness.cs`), layout, the import, the update prompt, or the publish delay. That's the lab run in
[`demo.md`](demo.md).

## Build it in the lab (needs tenant)
Solution **Equipment Desk** → new component library **Equipment Desk Kit** → three components with the custom properties from
the files (table in `demo.md`), **Allow customization** off → test screen → **Save with version notes** → **Publish**. In the
app: **Settings → Updates → New → Enhanced component properties** on → **Insert → Get more components** → import all → replace
the title label, add `deskRules`, `btnReturn` and `dlgReturn` from `LoansScreen.pa.yaml`, delete the `StateColor` UDF → publish.
Then change the library, publish, and accept the update in the app. This has **not yet run against the lab tenant**.

## What we learned / gotchas

- **IsMatch isn't the same in every host.** Our first `TagIsValid` was `IsMatch(tag, "CT-\d{4}")`; the test said `CT-00421` and
  `XCT-0042` were valid. Learn: `MatchOptions.Complete` is the default for IsMatch **on Power Apps**, `Contains` outside Power Apps
  (where the open-source engine is). Anchoring with `^...$` makes the rule mean the same everywhere; a test keeps both versions.
- **No components in galleries or forms** (Learn, known limitations). A per-row status badge component isn't possible; ship the
  rule as an **output function** and call it from the row's own label.
- **Library components can never access app scope** (Learn, Scope), and data sources can't be saved with components. Design
  library components as "data in, events out": the app handles `OnConfirm` and does the writes.
- **Function properties get arguments, nothing else.** Learn: they "cannot access variables or component values and properties".
  The empty-engine test enforces it.
- **"Experimental" or not?** The canvas component overview still calls enhanced component properties experimental; the
  "Canvas component properties" page says the feature is on by default for new apps and gives the switch for existing ones
  (Settings > Updates > New). Event, Function and Action properties need it; the classic input/output properties don't.
- **Editing a library component in the app breaks the link.** Learn: with customization allowed, **Edit component** creates a local
  copy that doesn't receive updates. We set `AllowCustomization: false` on all three (the schema says library definitions should
  always specify it).
- **Updates are a two-step publish.** Only *published* library versions reach apps; makers get **Review → Update** when they edit
  the app, or use **Check for updates**; Learn mentions a delay of up to 5 minutes after publishing; the app is then published again.
- **ALM:** an app that imports a library component depends on the library. Ship them in the same solution or install the library
  first, otherwise "Import failed due to missing dependencies". Learn: keep a library to about 20 components; solution export
  always exports the latest library version, so update apps before exporting.
- **Not in a library:** code (PCF) components, Power Automate flows. The library also doesn't show in Power Apps Mobile (Learn).
- **A library can't be deleted while an app uses it**, and an imported-but-unused component still counts as a dependency (Learn):
  remove it from the app first (`demo.md` tear-down).
- **Accessibility comes with the component:** icon used as a button gets `AccessibleLabel` and `TabIndex` 0, one `Heading1` per
  screen via the header's `Role` (Learn: accessibility properties). Learn also lists that overlays can't be dismissed with the
  Escape key, so the dialog has a real Cancel button besides the scrim tap.

## References
- [Canvas component overview (custom properties, Scope / Access app scope, known limitations)](https://learn.microsoft.com/power-apps/maker/canvas-apps/create-component)
- [Component library (create, publish, import, update, customization, permissions, limitations)](https://learn.microsoft.com/power-apps/maker/canvas-apps/component-library)
- [Component library ALM (solutions, dependencies, 20 components, 5-minute delay)](https://learn.microsoft.com/power-apps/maker/canvas-apps/component-library-alm)
- [Canvas component properties (data, function, action, event properties; enhanced component properties setting)](https://learn.microsoft.com/power-apps/maker/canvas-apps/component-properties)
- [Behavior formulas for components (OnReset, experimental custom behaviour)](https://learn.microsoft.com/power-apps/maker/canvas-apps/component-behavior)
- [IsMatch, Match, and MatchAll functions (MatchOptions.Complete default on Power Apps)](https://learn.microsoft.com/power-platform/power-fx/reference/function-ismatch)
- [Accessibility properties (AccessibleLabel, Role, TabIndex)](https://learn.microsoft.com/power-apps/maker/canvas-apps/controls/properties-accessibility)
- [Create accessible canvas apps](https://learn.microsoft.com/power-apps/maker/canvas-apps/accessible-apps)
- [Accessibility limitations in canvas apps (no Escape-key handling)](https://learn.microsoft.com/power-apps/maker/canvas-apps/accessible-apps-limitations)
- [View source code files for canvas apps (pa.yaml)](https://learn.microsoft.com/power-apps/maker/canvas-apps/power-apps-yaml)
- [Use code view for canvas app controls (Paste code)](https://learn.microsoft.com/power-apps/maker/canvas-apps/code-view)
- Power Fx interpreter: NuGet `Microsoft.PowerFx.Interpreter` 1.8.1 (open source, github.com/microsoft/Power-Fx)
- Blog: [Component Libraries — Complete Guide](https://www.devladlog.com/articles/powerapps/2026-02-28-component-libraries-complete-guide-2026/)
