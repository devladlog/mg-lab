# Demo shot list — DEVLADLOG Power Apps #3, Power Fx formulas and tips

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure | none |
| Tenant environment | Power Platform environment **`DEV`** with episodes 1–2 (tables Equipment and Loan, canvas app *Equipment Desk (phone)*). Created here: `LoansScreen`, the five test loans |
| Lab users | `labadmin` (the recording account): maker, runs the app. Borrowers in the test loans are the lab users `alex.demo`, `jordan.demo`, `sam.demo` (addresses as plain text). Optional: Teams with the app as a tab (cutaway) |
| Licences / trials | **Power Apps Premium** (in the lab) for `labadmin` and any lab user who runs the app; cost 0 |
| Recording machine | The Windows lab laptop: maker portal / Power Apps Studio / the running app in the browser with `pipeline/mask.js`; an Outlook on the web draft window (never sent) or a text editor for the pasted reminder; `pac` CLI and .NET 8 SDK for the download and the tests |

The formulas were tested locally (`dotnet test`: 208 passed, 39 test methods) on the open-source Power Fx interpreter
with a fixed clock. Everything below **needs the lab tenant** and has not been run there. In particular, Studio must accept
the UDF block exactly as written in `App.pa.yaml` (typed parameters, `Color` return type, the behavior UDF with `Void`),
and the delegation claims are only confirmed when Studio shows no warning with the data row limit at 1.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Episodes 1 and 2 in the lab **DEV** environment | tables Equipment and Loan, the canvas app **Equipment Desk (phone)** | existing |
| Power Apps **premium** licence (or trial) for the recording user | Dataverse makes the app premium (Learn: licensing FAQ) | existing / trial |
| Test data (below) | created in the model-driven app from episode 1 | — |
| A text editor or an Outlook draft window | to paste the copied reminder; **do not send** | — |
| Optional: Teams with the app added as a tab | only for the Copy failure cutaway | — |

## Test data (relative to the recording day R)
Create these Loans (Returned on empty unless stated). Pick R as a weekday that is **not** 1 or 8 December, or the numbers
on screen differ from the narration's examples (that's fine, but check them against `WorkingDaysBetween`).

| Device | Borrower | Due date | Notes | Expected on screen |
|---|---|---|---|---|
| CT-0043 Laptop 14 | alex.demo@contoso.com | R minus 14 days | Charger missing | red, "… working days late", Copy reminder button |
| CT-0107 Monitor 27 | jordan.demo@contoso.com | previous working day before R | — | red, "1 working day late" |
| CT-0108 Monitor 24 | sam.demo@contoso.com | next working day after R | (empty) | amber, "due … (soon)", "No notes" |
| CT-0311 Phone | alex.demo@contoso.com | R plus 18 days | — | grey, "due …" |
| CT-0042 Laptop 14 | jordan.demo@contoso.com | R minus 14 days, **Returned on** R minus 10 | Returned with dock | not listed |

## Build (off camera, ~30 min)
1. Open **Equipment Desk (phone)** in Studio. **App → Formulas**: replace the content with the `Formulas` block from
   `src/app/Src/App.pa.yaml` (everything after `=`, keep the episode 2 named formulas). Check there are no red errors.
   If Studio rejects a UDF, note the exact error and fix it in `App.pa.yaml` and the tests (report it as a gotcha).
2. **New screen → Blank**, name it `LoansScreen`. Add the controls from `src/app/Src/LoansScreen.pa.yaml`, either with
   right-click → **Paste code** (that control's YAML block) or by hand with the **same names** and formulas. If Studio
   rejects a control type name (`Label`, `Classic/Toggle`, `Gallery`, `Classic/Button`), build it by hand.
3. On `BrowseScreen` add a button "Open loans" with `OnSelect = Navigate(LoansScreen)` (not part of the tested source).
4. **Settings → General → Data row limit = 1** for the `rowlimit` shots, then back to 500.
5. Save, publish. `pac canvas download --name "Equipment Desk (phone)" -d ./export` (pac signed in off camera), copy
   `export/Src/App.pa.yaml` and `export/Src/LoansScreen.pa.yaml` over `src/app/Src/` and run
   `dotnet test EquipmentDesk.Formulas.Tests -m:1` again. Controls are found by name, so only renames break the tests.

## Screens to capture (match `screen` scenes in script.yaml)
| Scene | File | What must be on screen |
|---|---|---|
| `formulas-studio` | `screens/app-formulas.jpg` | App → Formulas expanded (or pop-out formula editor) with `IsWorkingDay`, `WorkingDaysBetween`, `LoanState` visible, no errors; then a label typing `WorkingDaysBetween(Date(2026,11,27), Date(2026,12,9))` with IntelliSense showing `(start: Date, finish: Date)` and the label showing **6** |
| `rowlimit` | `screens/row-limit-overdue.jpg` | Settings → General, **Data row limit = 1**; then LoansScreen preview, **Overdue only** on, **both** CT-0043 and CT-0107 listed, no delegation warning on `galLoans`. Optional: paste the `With` version (from the `gotcha` scene) into `galLoans.Items` → only one row, still no warning; undo |
| `loans-screen` | `screens/open-loans.jpg` | LoansScreen, toggle off: red "2 loans are overdue", four rows in due-date order with the colours in the table above, "Charger missing" and "No notes" |
| `copied` | `screens/reminder-copied.jpg` | Tap **Copy reminder** on CT-0043 → green "Reminder for alex.demo@contoso.com copied"; cut to the pasted text in an editor or an unsent Outlook draft. Optional: same app in Teams → red "Couldn't copy the reminder: …" |

Optional terminal capture for the `tests` scene: `dotnet test` summary (208 passed).

## Masking
- Environment name, tenant name, user names/avatars, the Outlook account if a draft window is used.
- Borrowers are fictional (`alex.demo@contoso.com`, `jordan.demo@contoso.com`, `sam.demo@contoso.com`).
- `pipeline/mask.js` in the browser; `series_label: "POWER APPS"` is set in `script.yaml`.

## Tear-down
1. Data row limit back to 500; remove the temporary label used for the IntelliSense shot; undo the `With` experiment.
2. Delete the five test loans (or keep them for episode 4, which reuses the same tables).
3. Close any Outlook draft without sending; remove the Teams tab if it was added only for the cutaway.
