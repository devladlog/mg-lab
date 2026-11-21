# Power Apps Build Special 11: build a canvas app from start to end

Contoso Inspections: a phone canvas app that field inspectors use to record an inspection, add items with photos, work offline, and
submit. From an empty environment to a published, shared app. Fictional names only (contoso, Alex Demo, Sam Demo).

**Shared schema.** This app and episode 12's model-driven back-office app run on one Dataverse solution, `ContosoInspections`
(prefix `cin`), because episodes 13 and 14 extend both apps in the same environment. The schema is episode 12's file
(`../12-build-a-model-driven-app-from-start-to-end/src/schema/contosoinspections.schema.json`); the copy in this folder is
byte-identical and two tests (xunit and pytest, plus a Pester hash check) fail if the two ever differ. The inspector story:
Draft, In progress, Submitted. Approved and Rejected are the reviewer's, set in episode 12's app.

Nothing in this folder has run against a real tenant. Everything that can be proven locally is tested. The rest is in `demo.md` and
marked **needs tenant**.

## What is built

- **Schema** (`src/schema/contosoinspections.schema.json`, copied from episode 12): solution ContosoInspections (publisher prefix
  `cin`), four tables (Inspector, Site, Inspection, Inspection item), three relationships, an alternate key on the site code, two
  security roles and a field security profile. One file; the script, the tests and the solution check all read it.
- **Provisioning script** (`src/scripts/Provision-ContosoInspections.ps1`): Dataverse Web API, idempotent, never signs in (takes a
  token), `-PlanOnly` prints the requests, `-SeedData` adds the sample sites and inspectors from `src/data/seed.json`. It creates the
  tables, columns, lookups (with their relationships), the site-code key and the **Inspection Field Inspector** role only; the
  back-office role and the field security profile belong to episode 12's solution.
- **Solution shell** (`src/solution/ContosoInspections`): `Solution.xml` and an empty `Customizations.xml`, packed and unpacked by the
  real `pac` offline. Tables and the role come from the script and `pac solution export`, because hand-writing them is unsupported.
- **Canvas app source** (`src/app/Src/*.pa.yaml`, pa.yaml v3): `App` (named formulas, pure and behavior user-defined functions),
  `InspectionsScreen` (delegable gallery, search, chips, sync icon, offline banner), `NewInspectionScreen`, `InspectionScreen`
  (score, follow-up, summary, items, decision banner, one or two panes), `ItemScreen` (camera, validation).
- **Episode files**: `script.yaml` (33 scenes, about 3,100 words, 13 screen scenes, 3 shorts) and `demo.md` (recorder checklist).

## How the canvas story maps onto the shared model

| Canvas idea | Shared schema |
|---|---|
| Inspection with a reference like `CWN-01-...-AD-001` built by the app | `Inspection number`, an auto number `INS-{SEQNUM:5}` assigned by Dataverse; the app builds nothing |
| Status Draft / Submitted / Reviewed / Closed | `Status`: Draft, In progress, Submitted (inspector), Approved, Rejected (reviewer, episode 12) |
| Result Pass / Needs follow-up / Fail, summary | `Score` (0-100), `Requires follow-up`, `Follow-up date`, `Summary`; `SuggestScore` and `SuggestFollowUp` propose them from the failed items |
| Finding (title, severity, category, details, photo, resolved, resolve by) | `Inspection item`: `Item`, `Severity` (Info/Minor/Major/Critical), `Category` (Safety/Electrical/Fire/Structural/Housekeeping), `Passed`, `Notes`, `Photo`, `Resolved on` |
| Overdue finding count | `UnresolvedItemCount`: failed items with no `Resolved on` |
| Role "Contoso Inspector" | `Inspection Field Inspector` (the same Basic/Global privileges, plus the offline read privileges the provisioner adds) |

One column was added to episode 12's schema for this: `cin_photo` (image, 10240 KB) on Inspection item, with image support in
episode 12's generator, a regenerated `Entity.xml` and one line in its test harness. Episode 12's tests were re-run (see below).

## Files

| Path | What it is |
|---|---|
| `src/schema/contosoinspections.schema.json` | Exact copy of episode 12's schema: tables, columns, choices, relationships, roles |
| `src/data/seed.json` | Sample sites (same codes as episode 12's CSV) and inspectors for `-SeedData` |
| `src/scripts/Provision-ContosoInspections.ps1` | Creates the schema in an environment through the Web API |
| `src/solution/ContosoInspections/Other/*.xml` | Solution shell for `pac solution pack` |
| `src/app/Src/App.pa.yaml` | Named formulas and user-defined functions |
| `src/app/Src/InspectionsScreen.pa.yaml` | List screen |
| `src/app/Src/NewInspectionScreen.pa.yaml` | Pick a site and start |
| `src/app/Src/InspectionScreen.pa.yaml` | Details, items, submit, the back office's decision |
| `src/app/Src/ItemScreen.pa.yaml` | Item form with camera |
| `tests/ContosoInspections.Canvas.Tests/` | xunit on the open-source Power Fx interpreter, with in-memory Dataverse tables |
| `tests/python/` | pytest: schema (and its byte-for-byte match with episode 12), solution pack/unpack with real `pac`, provisioning plan, `script.yaml` shape and real code excerpts |
| `tests/pester/Provision.Tests.ps1` | Pester: the script against a mocked Dataverse |
| `tests/schema/pa.schema.yaml` | Microsoft's pa.yaml v3 schema (see `NOTICE.md`) |
| `script.yaml`, `demo.md` | Video script and recorder guide |

## Run the tests

One at a time. From this folder:

```
cd tests/ContosoInspections.Canvas.Tests && dotnet test -m:1 --nologo     # Passed: 126
cd tests/python && python3 -m pytest -q                                   # 37 passed
cd tests/pester && pwsh -NoProfile -Command "Invoke-Pester -Path ./Provision.Tests.ps1"   # 19 passed
```

Needs the .NET 10 SDK, Python 3 with pytest and PyYAML, PowerShell 7 with Pester 5 or later, and the Power Platform CLI (`pac`, tested
with 2.16.1) on the path. `pac` is only used for `solution pack` and `unpack`. The NuGet packages restore on the first run
(Microsoft.PowerFx.Interpreter 1.8.1, xunit 2.9.2, YamlDotNet 16.3.0, JsonSchema.Net 7.3.4). Delete `bin`, `obj`, `.pytest_cache` and
`__pycache__` afterwards. The tests that compare against episode 12 expect its folder next to this one.

What the 126 canvas tests cover: every pa.yaml file validates against Microsoft's schema; the named formulas and UDFs evaluate
correctly (validation, suggested score and follow-up, follow-up dates, counts) against in-memory tables built from the schema; each
button flow (start, add item, resolve, submit) writes the right rows and returns the right Boolean, and a Draft becomes In progress
with its first item; the app writes only Draft, In progress and Submitted, never Approved or Rejected, and shows the back office's
decision read-only; offline and responsive formulas (sync icon, banner, size breakpoints, pane direction); the schema copy equals
episode 12's; and lints (delegable function lists, AccessibleLabel on interactive controls, 88-unit touch targets, no TabIndex above
0, live regions, 4.5:1 contrast, no `#` comments, UDFs never name a screen). The Python tests also check that every line of every
code excerpt in `script.yaml` (9 lines or fewer) is a real line of `src` or `tests`, and that the plan excerpt is real `-PlanOnly`
output.

## Gotchas

- **Delegation**: the lint only reads formulas against the functions Learn lists as delegable. Studio's blue underline is the real
  answer. Unconfirmed in Studio: the filter on a lookup GUID, the Boolean `Passed = false` with `IsBlank`, `CountRows`.
- **Camera control** takes photos up to 640 by 480 pixels (Learn). Use Add picture for full size.
- **Image column** in Dataverse takes `{ Full: uri, Value: uri }` in a Patch or Collect (Learn, take and upload photos).
- **Offline**: Dataverse offline-first only. No SaveData or LoadData, no flows, no non-Dataverse connectors. Sort every gallery.
  Publish the offline profile before the app, and the app again after editing the profile. The role needs read on Canvas App, Mobile
  offline profile and Sync Error.
- **TabIndex**: only 0 or -1 (Learn says not to set it above 0), so the tab order is the container order.
- **Two columns are called Status.** The custom `cin_status` and the system `statecode` both display as "Status". The app therefore
  addresses the column by its logical name (`cin_status`) and the choice as `'Status (Inspections)'`. The test engine has no system
  column, so this is **unverified in Studio**: check IntelliSense on the first formula, and if the choice is named differently, fix the
  one pattern `'Status (Inspections)'` (it is only in `App.pa.yaml` and `InspectionsScreen.pa.yaml`).
- **`Set` swallowed an error** in the open-source engine: `IfError(Set(v, Collect(...)), ...)` returned success after a failed
  `Collect`, and so did `Set(...); true`. `StartInspection` therefore takes the new record into `With` and tests it with
  `IfError(created, ...)`. Whether Power Apps behaves the same is unverified.
- **Auto number offline.** The inspection number is assigned by Dataverse, so a row created offline has none until it syncs; the screens
  show "New inspection" until then. Not checked on a phone.
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

## Shared schema: what changed and what to watch

Reconciled on 21 Nov 2026 (decision: episode 12's schema is canonical). Everything that used the old episode 11 model was rewritten:
provisioner payloads, solution shell (option value prefix 45532), all `pa.yaml` formulas and controls, seed data, the .NET, Python and
Pester tests, this README, `demo.md` and `script.yaml`. Things the next person should know:

- **Episode 12 now has a Photo column** (`cin_photo`, image) on Inspection item, with `image` support in its `build_solution.py`
  (a new branch in `attribute_xml`), a regenerated `Entity.xml` for that table, and one added line in its test harness. Its README
  section "Reconcile with episode 11" is out of date and was not edited from here.
- **The generated image-column XML has never been imported.** Dataverse also adds hidden `cin_photo_url`, `cin_photoid` and
  `cin_photo_timestamp` columns for an image column; the generator does not write them.
- **Offline.** The provisioner sets `IsAvailableOffline` on all four tables. Episode 12's `Entity.xml` says
  `IsOfflineInMobileClient` 0, so importing episode 12's solution over an environment provisioned by this one may switch offline back
  off; check Mobile offline after any import.
- **Roles.** This provisioner creates only `Inspection Field Inspector` (plus Read on Canvas App, Mobile Offline Profile and Sync Error
  for offline). If episode 12's solution is imported later, its roles are added by its own import; role privilege names use the table's
  logical name (`prvCreatecin_inspection`), as episode 12's generator does, and were not checked against a tenant.
- **Secured column.** `cin_reviewernotes` is created secured; no field security profile is created here, so an inspector never sees it.

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
