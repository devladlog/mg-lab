# Demo shot list — DEVLADLOG Power Apps #7, Component libraries

The component definitions, the app formulas and the Learn rules were tested locally (`dotnet test`: 109 passed). Everything
below **needs the lab tenant** and has not been run there: building the library in Studio, importing it into the app, the
running app, the update prompt.

## Lab environment
No VM and no Azure resource. Everything is recorded in a browser on the **lab Windows host** (the recording laptop).

| What | Notes | Cost |
|---|---|---|
| Lab **DEV** environment with episodes 1-6: solution **Equipment Desk** (Loan/Equipment tables, model-driven app), the canvas app **Equipment Desk (phone)** with the Open loans screen from episode 6 | the app must be in the **Equipment Desk** solution (Learn: library dependencies are tracked for apps in solutions) | existing |
| Recording user `labadmin`: **System Customizer** or **System Administrator** in DEV, Power Apps Premium licence (episode 2: Dataverse makes the app premium) | creating a library and editing the app is maker work; no extra licence for components | existing |
| Test data: an open, overdue loan **CT-0043 Laptop 14** for `alex.demo@contoso.com` (fictional lab user), a second open loan | same rows as episodes 3 and 6 | free |

Nothing else to provision. No premium connector beyond what episode 2 already uses; the library itself has no data source.

## Things to confirm in the lab (fix code/tests/README if they differ)
- The **Component libraries** entry (left nav or More > Discover all > App enhancements) and, inside the solution,
  **New > App > Component library** (Learn says a library can be created inside a solution; the exact menu label wasn't checked).
- **Enhanced component properties** is On in the library and in the app (Learn: on by default for new apps; existing apps:
  Settings > Updates > New). Without it there are no Event or output Function properties.
- Calling an output function through the **instance name** (`deskRules.StateColor(...)`) works, and works while the
  instance's `Visible` is `false`. Learn's example says `Component1.MyFunction(...)` without saying instance or definition.
  If a hidden instance doesn't work, keep it visible with Width/Height 0 and update `LoansScreen.pa.yaml`.
- The `ComponentLibraryUniqueName` Studio writes for the library (we assumed `contoso_equipmentdeskkit`; Learn: a library
  saved outside a solution gets the default publisher prefix). Replace it in the source if different.
- `ReturnType: None` for events, `Role` on labels and `TabIndex` on the classic icon are what Studio writes.
- After the lab build: download both and copy the real source back (see Steps 9), then re-run the tests.

## Steps
1. make.powerapps.com, DEV → **Solutions → Equipment Desk → New → App → Component library**, name **Equipment Desk Kit**.
   (If the menu differs, create it from **Component libraries → New component library** and add it to the solution with
   **Add existing**.)
2. For each component in `src/library/Src/Components/` (DeskHeader, ConfirmDialog, DeskRules): **New component**, rename,
   set Width/Height from the file, then **New custom property** for each entry under `CustomProperties`:

   | Component | Property | Property type / definition | Data / return type | Default or formula |
   |---|---|---|---|---|
   | DeskHeader | Title | Data, Input | Text | `"Equipment Desk"` |
   | DeskHeader | ShowBack | Data, Input | Boolean | `false` |
   | DeskHeader | Accent | Data, Input | Color | `RGBA(0, 90, 158, 1)` |
   | DeskHeader | OnBack | Event | (none) | |
   | ConfirmDialog | Title, Message, ConfirmText | Data, Input | Text | `"Are you sure?"`, `""`, `"Confirm"` |
   | ConfirmDialog | Destructive | Data, Input | Boolean | `false` |
   | ConfirmDialog | OnConfirm, OnCancel | Event | (none) | |
   | DeskRules | StateColor | Function, Output | Color, parameter `state` Text | the `Switch` from the file |
   | DeskRules | TagIsValid | Function, Output | Boolean, parameter `tag` Text | `IsMatch(Upper(Trim(tag)), "^CT-\d{4}$")` |

   Turn **Allow customization** Off on each component. Add the child controls with the names and formulas in the files
   (Learn: right-click → **Paste code** pastes control YAML; or set them by hand).
3. Add `LibraryTestScreen` from `LibraryTestScreen.pa.yaml`. Press **Play**: back arrow → "OnBack"; Open dialog → Cancel → "OnCancel".
   Capture `library-screen` here.
4. **Save with version notes** "1.0 first version", then **Publish**. Close Studio.
5. Open **Equipment Desk (phone)**. **Settings → Updates → New → Enhanced component properties** On if it isn't.
   **Insert → Get more components → Equipment Desk Kit → Select all → Import** (capture `import-screen`).
6. On **LoansScreen**: delete `lblLoansTitle`; insert DeskHeader as `hdrLoans`, DeskRules as `deskRules`, ConfirmDialog as
   `dlgReturn` (last in the tree, so it's on top); set their properties from `src/app/Src/LoansScreen.pa.yaml`; change the two
   colour formulas to `deskRules.StateColor(...)`; add `btnReturn` to the gallery template. In **App → Formulas** delete the
   `StateColor` definition. App checker must show no errors. Save and publish.
7. Play the published app (browser, phone layout): `app-screen` — Returned on CT-0043 → dialog → Cancel → Returned → Mark
   returned → green banner, row gone, summary green. Open the model-driven **Equipment Desk** app: CT-0043 status Available.
8. Update flow (`update-screen`): in the library change DeskHeader **Accent** default to `RGBA(0, 59, 112, 1)`, **Save with
   version notes** "1.1 darker header", **Publish**, wait up to 5 minutes (Learn). Open the app for editing → **Review** →
   **Update**; show **Insert → Library components → Check for updates** as the second way. Save and publish the app.
9. Source back into the repo: `pac canvas download --name "Equipment Desk (phone)" -d <dir>` and copy `Src/LoansScreen.pa.yaml`
   and `Src/App.pa.yaml` over `src/app/Src`. For the library use **Download a copy** in Studio (Learn) if `pac canvas download`
   doesn't list it, unzip the `.msapp` and copy its `Src` component files over `src/library/Src`. Re-run `dotnet test`;
   update the tests where Studio wrote something different, and note it in the README.
10. Optional terminal capture for `tests`: `dotnet test EquipmentDesk.Components.Tests -m:1` (109 passed).

## Screens to capture (match `screen` scenes in script.yaml)
| Scene | File | What must be on screen |
|---|---|---|
| `library-screen` | `screens/library-studio.jpg` | Library in Studio, Components tab with the three components; DeskHeader custom properties (Title, ShowBack, Accent, OnBack as Event); test screen in Play showing "OnBack" then "OnCancel"; Save with version notes + Publish |
| `import-screen` | `screens/import-components.jpg` | App in Studio: Get more components panel with Equipment Desk Kit; Library components category; Enhanced component properties On; hdrLoans properties; gallery label Color with `deskRules.StateColor(...)` |
| `app-screen` | `screens/app-return.jpg` | Running app: header with back arrow; dialog "Mark as returned?" for CT-0043; banner "CT-0043 is back and available"; row gone; model-driven app shows CT-0043 Available |
| `update-screen` | `screens/library-update.jpg` | Library version note "1.1 darker header" + Publish; app "Updates available" → Review (with the note) → Update; darker header; Check for updates icon |

## Masking
- Environment name and URL, tenant name, real user names and avatars, the maker portal account menu.
- Borrower on screen is the fictional `alex.demo@contoso.com`; if the lab mailbox domain shows anywhere, mask it.
- `pipeline/mask.js` in the browser; `series_label: "POWER APPS"` is set in `script.yaml`.

## Tear-down
1. Keep the library and the app changes for episode 8 (it builds on this screen). To remove instead: in the app delete the
   three instances, then **Insert → Library components → ... → Remove from app** for each component (Learn: unused imported
   components still create a dependency), restore `lblLoansTitle` and the `StateColor` UDF, publish.
2. Only then delete the library (Learn: a library referenced by an app can't be deleted).
3. Reset the test loan CT-0043 (clear Returned on, status On loan) if later episodes need it overdue.
