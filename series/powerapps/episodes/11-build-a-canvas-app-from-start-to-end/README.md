# Power Apps Build Special 11: build a canvas app from start to end

Contoso Inspections: a phone canvas app that field inspectors use to record an inspection, add findings with photos, work offline, and
submit. From an empty environment to a published, shared app. Fictional names only (contoso, Alex Demo, Sam Demo).

Nothing in this folder has run against a real tenant. Everything that can be proven locally is tested. The rest is in `demo.md` and
marked **needs tenant**.

## What is built

- **Schema** (`src/schema/contosoinspections.schema.json`): solution ContosoInspections (publisher prefix `cin`), four tables
  (Site, Inspector, Inspection, Finding), three relationships, and the Contoso Inspector security role. One file; the script, the
  tests and the solution check all read it.
- **Provisioning script** (`src/scripts/Provision-ContosoInspections.ps1`): Dataverse Web API, idempotent, never signs in (takes a
  token), `-PlanOnly` prints the requests, `-SeedData` adds sample rows.
- **Solution shell** (`src/solution/ContosoInspections`): `Solution.xml` and an empty `Customizations.xml`, packed and unpacked by the
  real `pac` offline. Tables and the role come from the script and `pac solution export`, because hand-writing them is unsupported.
- **Canvas app source** (`src/app/Src/*.pa.yaml`, pa.yaml v3): `App` (named formulas, pure and behavior user-defined functions),
  `InspectionsScreen` (delegable gallery, search, chips, sync icon, offline banner), `NewInspectionScreen`, `InspectionScreen`
  (details and findings, one or two panes), `FindingScreen` (camera, validation).
- **Episode files**: `script.yaml` (32 scenes, about 2,770 words, 13 screen scenes, 3 shorts) and `demo.md` (recorder checklist).

## Files

| Path | What it is |
|---|---|
| `src/schema/contosoinspections.schema.json` | Tables, columns, choices, relationships, role, sample data |
| `src/scripts/Provision-ContosoInspections.ps1` | Creates the schema in an environment through the Web API |
| `src/solution/ContosoInspections/Other/*.xml` | Solution shell for `pac solution pack` |
| `src/app/Src/App.pa.yaml` | Named formulas and user-defined functions |
| `src/app/Src/InspectionsScreen.pa.yaml` | List screen |
| `src/app/Src/NewInspectionScreen.pa.yaml` | Pick a site and start |
| `src/app/Src/InspectionScreen.pa.yaml` | Details, findings, submit |
| `src/app/Src/FindingScreen.pa.yaml` | Finding form with camera |
| `tests/ContosoInspections.Canvas.Tests/` | xunit on the open-source Power Fx interpreter, with in-memory Dataverse tables |
| `tests/python/` | pytest: schema, solution pack/unpack with real `pac`, provisioning plan, `script.yaml` shape |
| `tests/pester/Provision.Tests.ps1` | Pester: the script against a mocked Dataverse |
| `tests/schema/pa.schema.yaml` | Microsoft's pa.yaml v3 schema (see `NOTICE.md`) |
| `script.yaml`, `demo.md` | Video script and recorder guide |

## Run the tests

One at a time. From this folder:

```
cd tests/ContosoInspections.Canvas.Tests && dotnet test -m:1 --nologo     # Passed: 104
cd tests/python && python3 -m pytest -q                                   # 28 passed
cd tests/pester && pwsh -NoProfile -Command "Import-Module /root/.local/share/powershell/Modules/Pester; Invoke-Pester -Path ./Provision.Tests.ps1"   # 15 passed
```

Needs the .NET 8 SDK, Python 3 with pytest and PyYAML, PowerShell 7 with Pester 5 or later, and the Power Platform CLI (`pac`, tested
with 2.16.1) on the path. `pac` is only used for `solution pack` and `unpack`. The NuGet packages restore on the first run
(Microsoft.PowerFx.Interpreter 1.8.1, xunit 2.9.2, YamlDotNet 16.3.0, JsonSchema.Net 7.3.4). Delete `bin`, `obj`, `.pytest_cache` and
`__pycache__` afterwards.

What the 104 canvas tests cover: every pa.yaml file validates against Microsoft's schema; the named formulas and UDFs evaluate
correctly (validation, result suggestion, reference numbers, resolve-by dates, counts) against in-memory tables built from the schema;
each button flow (start, add finding, resolve, submit) writes the right rows and returns the right Boolean; offline and responsive
formulas (sync icon, banner, size breakpoints, pane direction); and lints (delegable function lists, AccessibleLabel on interactive
controls, 88-unit touch targets, no TabIndex above 0, live regions, 4.5:1 contrast, no `#` comments, UDFs never name a screen).

## Gotchas

- **Delegation**: the lint only reads formulas against the functions Learn lists as delegable. Studio's blue underline is the real
  answer. Unconfirmed in Studio: the filter on a lookup GUID, the Boolean `Resolved = false`, `CountRows`.
- **Camera control** takes photos up to 640 by 480 pixels (Learn). Use Add picture for full size.
- **Image column** in Dataverse takes `{ Full: uri, Value: uri }` in a Patch or Collect (Learn, take and upload photos).
- **Offline**: Dataverse offline-first only. No SaveData or LoadData, no flows, no non-Dataverse connectors. Sort every gallery.
  Publish the offline profile before the app, and the app again after editing the profile. The role needs read on Canvas App, Mobile
  offline profile and Sync Error.
- **TabIndex**: only 0 or -1 (Learn says not to set it above 0), so the tab order is the container order.
- **Classic Dropdown** shows the first column: set Value to Site name in the property pane.
- **Open-source Power Fx** engine does not know `Parent` and `Self`, so the test harness rewrites them. Studio does know them.
- **The msapp**: pa.yaml in `src/app` cannot be turned into an `.msapp` offline with a result proven here. Create the app in Studio
  (or via coauthoring) and export it.
- **Sharing** a canvas app with a role needs a system administrator, goes to Entra users and groups (not Microsoft 365 groups), and the
  app must be saved and published first.
- **Dev plan**: Learn says that after November 15, 2026 signing up for the Developer Plan no longer creates a developer environment.
  Use a trial environment for premium features.

## What the tests do not prove

- That Dataverse accepts the metadata and role payloads, and the names of the privileges for the system tables (canvas app, mobile
  offline profile, sync error). The solution component type 20 for the role is from memory, not checked on Learn here.
- That Power Apps Studio loads these pa.yaml files and knows every control type name (`Camera`, `Classic/Dropdown`, `Classic/Icon`,
  `GroupContainer` with `Variant: AutoLayout`), and that user-defined functions can read global variables there.
- Delegation as Studio and Dataverse see it, and behavior above 500 rows.
- The camera, the image column, offline sync and the airplane-mode behavior on a real phone.
- That the role gives Sam Demo none of Alex Demo's rows (Basic scope is documented behavior, but not run here).
- Screen reader behavior. The lint checks labels, size and contrast numbers, not how TalkBack or VoiceOver read the screen.
- Anything about licensing for the lab users.

## Open item: shared schema

All build specials share one `ContosoInspections` solution. Episode 12 (model-driven app) created its own
`contosoinspections.schema.json` at 07:21, after this one (07:09). The two differ in tables, option value prefix, columns and
Inspection status options. This folder did not edit episode 12. The two files must be reconciled into one before either is imported
into the same environment.

## References

- Create and update table definitions by using the Web API: https://learn.microsoft.com/power-apps/developer/data-platform/webapi/create-update-entity-definitions-using-web-api
- Web API table schema operations sample: https://learn.microsoft.com/power-apps/developer/data-platform/webapi/web-api-metadata-operations-sample
- App object, Formulas property, user-defined functions: https://learn.microsoft.com/power-platform/power-fx/reference/object-app
- Delegation overview: https://learn.microsoft.com/power-apps/maker/canvas-apps/delegation-overview
- Camera control: https://learn.microsoft.com/power-apps/maker/canvas-apps/controls/control-camera
- Build responsive apps: https://learn.microsoft.com/power-apps/maker/canvas-apps/build-responsive-apps
- Create accessible canvas apps: https://learn.microsoft.com/power-apps/maker/canvas-apps/accessible-apps
- Accessible colors: https://learn.microsoft.com/power-apps/maker/canvas-apps/accessible-apps-color
- Accessibility checker: https://learn.microsoft.com/power-apps/maker/canvas-apps/accessibility-checker
- Mobile offline for canvas apps, overview: https://learn.microsoft.com/power-apps/mobile/canvas-mobile-offline-overview
- Set up mobile offline for canvas apps: https://learn.microsoft.com/power-apps/mobile/canvas-mobile-offline-setup
- Mobile offline limitations for canvas apps: https://learn.microsoft.com/power-apps/mobile/limitations-canvas-apps
- Monitor for canvas apps: https://learn.microsoft.com/power-apps/maker/monitor-canvasapps
- Share a canvas app: https://learn.microsoft.com/power-apps/maker/canvas-apps/share-app
- Add a canvas app to a solution: https://learn.microsoft.com/power-apps/maker/canvas-apps/add-app-solution
- View source code files for canvas apps (pa.yaml): https://learn.microsoft.com/power-apps/maker/canvas-apps/power-apps-yaml
- Create and edit canvas apps with AI code generation tools: https://learn.microsoft.com/power-apps/maker/canvas-apps/create-canvas-external-tools
- pac canvas: https://learn.microsoft.com/power-platform/developer/cli/reference/canvas
- Explore Power Apps for free for 30 days: https://learn.microsoft.com/power-apps/maker/signup-for-powerapps
- Power Apps Developer Plan: https://learn.microsoft.com/power-platform/developer/plan
- Blog, Complete Guide (canvas apps; no episode-specific guide exists yet): https://www.devladlog.com/articles/powerapps/2026-02-06-canvas-apps-fundamentals-complete-guide-2026/
