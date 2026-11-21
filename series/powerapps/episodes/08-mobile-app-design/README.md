# DEVLADLOG Power Apps #8 — Mobile app design: rotate it, tap it, take it offline

Episode 7's **Open loans** screen worked on a phone held upright, online, by someone with thin fingers. This episode redesigns
it for the phone it really runs on:

- **Screen size and orientation.** Scale to fit off; the screen's Width/Height use Learn's orientation formulas, so a phone
  turned sideways gets a short, wide screen instead of a tall one you scroll. `App.SizeBreakpoints` is written out as Learn's
  phone default `[1200, 1800, 2400]`. **Small**: the list *or* the selected loan (tap a row; the header's back arrow returns to
  the list). **Medium and up** (phone sideways, tablet, desktop): list *and* loan side by side in auto-layout containers.
- **Touch.** `TapTarget = 88` phone-layout units; every tappable control passes a test. The row buttons moved out of the gallery
  rows into the detail pane; the whole row is the target.
- **Offline-first.** Dataverse offline (Learn: for Dataverse apps use the built-in offline feature, not SaveData/LoadData), Learn's
  globe sync icon, an offline banner, **Send reminder** disabled offline (flows aren't supported offline) while **Mark returned**
  keeps working and syncs later.
- **Barcode reader.** Scan the Code 128 asset tag label to open the loan; a text box does the same without a camera. Both validate
  with the library's `deskRules.TagIsValid` (episode 7) and call one behavior UDF, `FindLoan`.

| Path | What it is |
|---|---|
| [`src/app/Src/App.pa.yaml`](src/app/Src/App.pa.yaml) | `SizeBreakpoints`, `MinScreenWidth/Height`, episode 7's `App.Formulas` + `TapTarget` + `FindLoan` |
| [`src/app/Src/LoansScreen.pa.yaml`](src/app/Src/LoansScreen.pa.yaml) | The redesigned screen: orientation formulas, `icoSync`, `lblOffline`, containers `conBody`/`conList`/`conDetail`, `bcrScan`, `txtFindTag`, library instances |
| [`tests/EquipmentDesk.Mobile.Tests`](tests/EquipmentDesk.Mobile.Tests) | 112 xUnit tests on the open-source Power Fx interpreter |
| [`tests/EquipmentDesk.Mobile.Tests/Harness.cs`](tests/EquipmentDesk.Mobile.Tests/Harness.cs) | Episode 7's component host plus `SetDevice(width, height)` (App object, screen Width/Height/Size), `SetConnection`, `SetHost`, `Scan(...)` |
| [`tests/schema/pa.schema.yaml`](tests/schema/pa.schema.yaml) | The official pa.yaml v3.0 schema (MIT, see [NOTICE](tests/schema/NOTICE.md)) |
| `../07-component-libraries/src/library/Src` | The Equipment Desk Kit library, read in place (the app uses the published library; it isn't copied) |

## Run the tests (no tenant needed)

```bash
cd tests
dotnet test EquipmentDesk.Mobile.Tests -m:1
# Passed!  - Failed: 0, Passed: 112, Skipped: 0, Total: 112 (.NET 8, Microsoft.PowerFx.Interpreter 1.8.1)
```
The tests need episode 7's folder next to this one (they read its library source).

What the groups prove:
- **SourceTests**: schema-valid files, unique names, every UDF/output function compiles, every logic formula and instance property
  binds (`OnScan`, `OnChange`, `Icon`, `Live`, `LayoutDirection` included), instances only set what the library declares.
- **ResponsiveTests**: the breakpoints are Learn's phone defaults; **Learn's own landscape example** (designed 640 x 1136, device
  1136 x 640) gives a 1136-high screen with the default formula and 640 with ours; Size for upright/sideways phone, tablet and
  desktop example widths; upright phone shows list then loan (header title becomes the tag); back closes the loan first; rotating
  with a loan open shows both panes; wide screen without a selection says so.
- **TouchTests**: `TapTarget` is 88; every tappable control's Height (row TemplateSize for galleries) is at least 88; the library
  components pass too; **episode 7's 40-high row button and toggle fail the same check**; no interactive controls inside rows;
  interactive icons/inputs have an AccessibleLabel and the decorative chevron doesn't.
- **OfflineTests**: banner only offline (with `Live` polite); the globe follows `Connection.Sync` as in Learn's template, only when
  `Host.OfflineEnabled`, and opens the device status page; Send reminder disabled offline with a reason, "Sending..." while a flow
  runs, only for overdue loans; Mark returned works offline and closes the pane; a failed return keeps the loan on screen; lints:
  the gallery is sorted, no `Relate`/`Unrelate`, every flow call is behind a `Connection.Connected` check, no two-level lookups in filters.
- **ScannerTests**: a scanned tag opens its loan; case and spaces don't matter; a device with no open loan says so; URLs, an
  over-long tag and an EAN product code are refused by the library rule; the first of several codes wins; typing works the same.

We checked the tests bite: the default Height formula, dropping the Connection check from Send reminder and a 40-high toggle
fail 4 tests.

What they **don't** prove: how Studio lays out containers, that it accepts these hand-written control types and property names
(`GroupContainer`, `BarcodeReader`, `LayoutGap`, ...), the real App.Width values on a given phone, the offline sync, conflict
handling, the native scanner or rotation. The harness computes Size as "1 + the number of breakpoints the screen width reaches";
Learn doesn't say which side an exact breakpoint falls on, so no test uses one. That's the lab run in [`demo.md`](demo.md).

## Build it in the lab (needs tenant and a phone)
Tables **Can be taken offline** → Studio **Settings > Display**: Scale to fit, Lock aspect ratio, Lock orientation off → App
properties and `App.Formulas` from `App.pa.yaml` → rebuild LoansScreen from `LoansScreen.pa.yaml` → **Settings > General > Can be
used offline** with a profile → publish profile and app → Power Apps mobile on a real phone. Steps and captures in `demo.md`.
This has **not yet run against the lab tenant**.

## What we learned / gotchas

- **Landscape scrolls unless you change the screen formulas.** Learn's example: a phone app designed at 640 x 1136 turned sideways
  has App 1136 x 640, and `Max(App.Height, App.DesignHeight)` makes the screen 1136 high. Learn's orientation formulas swap
  DesignWidth/DesignHeight. Learn's pages show two different default formulas (`MinScreenHeight` and `DesignHeight`), which is one
  more reason to write the formula yourself.
- **Phone apps use doubled coordinates.** Learn: SizeBreakpoints default to `[600, 900, 1200]` for tablet/web apps and
  `[1200, 1800, 2400]` for phone apps "because such apps use coordinates that are effectively double". Copying breakpoints or pixel
  sizes from a tablet app into a phone app silently halves them.
- **The authoring canvas doesn't respond to sizing formulas** (Learn). Test responsive layouts by publishing and opening the app
  on devices or browser windows; dragging a control afterwards overwrites its X/Y/Width/Height formulas.
- **Flows don't run offline.** Learn (mobile offline limitations): Power Automate flows aren't supported in offline mode. Episode 6's
  Send reminder is disabled offline and says why; a lint makes sure no other flow call sneaks in.
- **Dataverse apps: offline-first, not SaveData/LoadData.** Learn: "For Microsoft Dataverse-based canvas apps, you must use the offline
  capability built-in". The app must be in a solution, tables marked **Can be taken offline**; users with only **Basic User** can't
  open an offline app (they need read on Canvas App, Mobile offline profile and Sync Error). Delta sync runs every 5 minutes online;
  the record limit is 3,000,000 (Learn).
- **No offline in a browser**, even on a phone (Learn). The globe icon uses `Host.OfflineEnabled` so it only shows in a player that
  supports offline.
- **Sort offline galleries** (Learn: rows may come back in a different order without a sort), **no `Relate`/`Unrelate`**, and
  lookup filters at most **one level** deep offline (`Equipment.'Asset tag'` is fine).
- **Barcode reader**: native scanner on Android, iOS and Windows only; not in desktop browsers or Teams mobile (Learn); `Barcodes` is a
  table of Value and Type; it doesn't support `Select()`. Learn's accessibility advice: offer another way to enter the code, hence the
  text box.
- **88 is our rule, not a Power Apps limit.** Microsoft's touch guidance (Windows apps) calls 44 x 44 effective pixels touch-optimized;
  with phone-layout coordinates doubled that's 88. Episode 7's row buttons were 40.
- **Components and screen size:** the DeskHeader from episode 7 needed no change; its `OnBack` event let the app decide that "back"
  closes the loan on a small screen. That's the payoff of "data in, events out".

## References
- [Create responsive layouts in canvas apps (screen formulas, orientation, ScreenSize, SizeBreakpoints)](https://learn.microsoft.com/power-apps/maker/canvas-apps/create-responsive-layout)
- [Building responsive canvas apps (Scale to fit, auto-layout containers, known issues)](https://learn.microsoft.com/power-apps/maker/canvas-apps/build-responsive-apps)
- [Horizontal container control (Direction, Gap, Fill portions, Minimum width)](https://learn.microsoft.com/power-apps/maker/canvas-apps/controls/control-horizontal-container)
- [Develop offline-capable canvas apps (Dataverse: built-in offline; browsers can't run offline)](https://learn.microsoft.com/power-apps/maker/canvas-apps/offline-apps)
- [Mobile offline for canvas apps overview (offline-first vs LoadData/SaveData)](https://learn.microsoft.com/power-apps/mobile/canvas-mobile-offline-overview)
- [Set up mobile offline for canvas apps (roles, tables, profile, Offline template, Connection.Sync icon)](https://learn.microsoft.com/power-apps/mobile/canvas-mobile-offline-setup)
- [Work with canvas apps offline (initial and delta sync, sync status icons)](https://learn.microsoft.com/power-apps/mobile/canvas-mobile-offline-working)
- [Mobile offline limitations for canvas apps (flows, Relate/Unrelate, lookups, sort order, 3,000,000 records)](https://learn.microsoft.com/power-apps/mobile/limitations-canvas-apps)
- [Connection, App, Location signals (Connection.Connected, Metered, Sync)](https://learn.microsoft.com/power-platform/power-fx/reference/signals)
- [Barcode reader control (Barcodes, OnScan, platforms, accessibility, Select)](https://learn.microsoft.com/power-apps/maker/canvas-apps/controls/control-barcodereader)
- [Limitations of controls in canvas apps (barcode reader not in desktop browsers)](https://learn.microsoft.com/power-apps/maker/canvas-apps/control-limitations)
- [Accessibility properties (AccessibleLabel, Live, Role, TabIndex)](https://learn.microsoft.com/power-apps/maker/canvas-apps/controls/properties-accessibility)
- [Touch interactions, hit targets (44 x 44 epx touch-optimized)](https://learn.microsoft.com/windows/apps/develop/input/touch-interactions#hit-targets)
- [View source code files for canvas apps (pa.yaml)](https://learn.microsoft.com/power-apps/maker/canvas-apps/power-apps-yaml)
- Power Fx interpreter: NuGet `Microsoft.PowerFx.Interpreter` 1.8.1 (open source, github.com/microsoft/Power-Fx)
- Blog: [Mobile App Design — Complete Guide](https://www.devladlog.com/articles/powerapps/2026-03-04-mobile-app-design-complete-guide-2026/)
