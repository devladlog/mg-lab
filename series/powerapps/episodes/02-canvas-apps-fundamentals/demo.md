# Demo shot list — DEVLADLOG Power Apps #2, Canvas apps fundamentals

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure | none |
| Tenant environment | Power Platform environment **`DEV`** with episode 1's tables, model-driven app and test data. Created here: canvas app *Equipment Desk (phone)* in the *Equipment Desk* solution |
| Lab users | `labadmin` (the recording account): maker, runs the app. For the optional warning cutaway: **`riley.demo` (Riley Demo)** with a custom role that can create Loans but has **no Write on Equipment** (role created and removed in this episode). Borrower in the app: `alex.demo@contoso.com` |
| Licences / trials | **Power Apps Premium** (in the lab) for `labadmin` and any lab user who runs the app; cost 0 |
| Recording machine | The Windows lab laptop: maker portal / Power Apps Studio / the running app in the browser with `pipeline/mask.js`; Power Apps mobile or the browser's phone preview for the phone shots; `pac` CLI (signed in to `DEV` off camera) and .NET 8 SDK for `pac canvas download` and the tests |

The formulas were tested locally (`dotnet test`: 52 passed) on the open-source Power Fx interpreter. Everything below
**needs the lab tenant** and has not been run there: the control type names in the `.pa.yaml` files and the delegation
behaviour are only confirmed once the app runs in Studio.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Episode 1 provisioned in the lab **DEV** environment | tables Equipment and Loan, the model-driven app, test data (CT-0042 Laptop 14, CT-0043, CT-0107 Monitor 27, CT-0108 Monitor 24, CT-0311 Phone in repair, CT-0400 Dock retired) | existing |
| Power Apps **premium** licence (or trial) for the recording user | Dataverse makes the app premium (Learn: licensing FAQ); building needs none | existing / trial |
| **Riley Demo** (`riley.demo`) with a role that can **create Loans** but has **no Write on Equipment** | only for the optional warning cutaway | — |
| Power Apps mobile app or the browser's phone preview | for the phone shots | free |
| `pac` CLI signed in to DEV (device code, off camera) | only for `pac canvas download` at the end | — |

## Build (off camera, ~30 min)
1. make.powerapps.com → Solutions → **Equipment Desk** → New → App → **Canvas app**, phone layout, name
   **Equipment Desk (phone)**. Keep it in the solution.
2. Data → add **Equipment** and **Loans** (Dataverse).
3. App → **Formulas**: paste the two named formulas from `src/app/Src/App.pa.yaml`; **StartScreen** = `BrowseScreen`.
4. Rename Screen1 to `BrowseScreen`, add `LendScreen`. For each control in the `.pa.yaml` files, either right-click →
   **Paste code** with that control's YAML block (Learn: code view validates the YAML before creating the control), or add
   the control by hand with the **same name** and paste the formulas. If Studio rejects a control type name
   (`Label`, `Classic/TextInput`, `Classic/Toggle`, `Gallery`, `Classic/DatePicker`, `Classic/Button`), build that control
   by hand and note the correct type in the README.
5. **Settings → General → Data row limit = 1.** Check the gallery for a yellow delegation triangle. If there is one on the
   `!tglAvailableOnly.Value || Status = ...` part, switch to `If(tglAvailableOnly.Value, Filter(..., Status = ...), Filter(...))`,
   update `BrowseScreen.pa.yaml` and the tests, and report it as a gotcha.
6. Save, publish. `pac canvas download --name "Equipment Desk (phone)" -d ./export` → copy `export/Src/*.pa.yaml` over
   `src/app/Src/` and run `dotnet test EquipmentDesk.Canvas.Tests -m:1` again. Commit the Studio-generated files (the
   tests find controls by name, so renamed controls are the only thing that breaks them).
7. Reset test data before recording: CT-0042 status **Available**, no open loan for it.

## Screens to capture (match `screen` scenes in script.yaml)
| Scene | File | What must be on screen |
|---|---|---|
| `rowlimit` | `screens/data-row-limit.jpg` | Settings → General, **Data row limit = 1**; then Browse in preview with `CT-01` typed: CT-0107 **and** CT-0108 listed, no delegation warning on the gallery |
| `lend` | `screens/lend-validation.jpg` | Lend screen for CT-0042, email `alex.demo@contoso.com`, due date one day before loan date → red label "The due date can't be before the loan date.", **Lend** greyed out |
| `saved` | `screens/saved.jpg` | After Lend: green "Loan saved: CT-0042", back on Browse, CT-0042 gone from the available list |
| `saved` (optional) | `screens/warning.jpg` | Same flow signed in as Riley Demo (limited role): yellow "Loan saved, but the device status wasn't updated: …" |
| `same-data` | `screens/model-driven-loan.jpg` | Episode 1 model-driven app: the new loan in the Loans view, CT-0042 with Status **On loan** |

Optional terminal capture: `dotnet test` summary (52 passed) for the `tests` scene.

## Masking
- Environment name, tenant name, user names/avatars (use the fictional `alex.demo@contoso.com` as the borrower).
- If the warning cutaway shows the real privilege error text, it contains the table logical name only — fine; mask any
  user or org identifiers in it.
- `pipeline/mask.js` in the browser; `series_label: "POWER APPS"` is set in `script.yaml`.

## Tear-down
1. Set the Data row limit back to 500 (or leave the app unpublished).
2. Delete the test loans created while recording; set CT-0042 back to Available.
3. Remove Riley Demo's limited role assignment and delete the role.
4. The app can stay in the Equipment Desk solution for later episodes; delete it from the solution otherwise.
