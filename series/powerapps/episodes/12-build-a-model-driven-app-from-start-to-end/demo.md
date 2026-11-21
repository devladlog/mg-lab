# Demo shot list — DEVLADLOG Power Apps #12 (Build Special), Build a model-driven app from start to end

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure | none (no resource group for this episode; the Azure naming `rg-mglab-powerapps-12` is **not** used) |
| Tenant environment | Power Platform environment **`DEV`** (Dataverse). Created here: publisher *Contoso Lab* (`cin`), solution *Contoso Inspections* (`ContosoInspections`), 4 tables, the app *Inspection Back Office*, a business process flow, business rules, a custom page, a command component library, 2 security roles, 1 field security profile. **Shared with episode 11 (the canvas special): do not delete the solution between the two recordings** (see "Reconcile" in README) |
| Lab users | `labadmin` builds everything (System Administrator or System Customizer in `DEV`). `sam.demo` is the back-office user: gets the role *Inspection Back Office* and the field security profile. `alex.demo`, `jordan.demo`, `riley.demo`, `taylor.demo` are the four inspectors named in the seed data (rows only, they do not sign in) |
| Licences / trials | **Power Apps Premium via the self-service trial** for `labadmin` and `sam.demo` (every user who runs a model-driven app needs it). Cost 0. No AI credits, no pay-as-you-go plan and no Copilot Studio are used in this episode |
| Recording machine | Windows lab laptop: maker portal, admin center and the running app in the browser (use `pipeline/mask.js`; Sam Demo in an InPrivate window); WSL (Ubuntu) terminal with Python 3, .NET 10 SDK and the Power Platform CLI (`pac`) for the **offline** steps only |

Everything under `src/` and `tests/` was built and tested locally (`python3 -m pytest -q`: 75 passed;
`dotnet test -m:1`: 46 passed). **Every step below marked "needs tenant" has not been run.** In particular the generated
solution XML has never been imported: the recorder is the first real import, so keep the fallback in step 2 ready.

Do **not** run `pac auth` for this episode: the solution is imported in the browser (Solutions > Import) and exported the
same way. `pac solution pack` and `unpack` are offline.

## Prerequisites

| What | Notes | Cost |
|---|---|---|
| `DEV` environment with Dataverse, *not* an unmanaged developer environment | Learn: those are being retired | existing |
| `labadmin` with System Administrator or System Customizer in `DEV` | to create apps, flows, rules, roles | — |
| `sam.demo` with a Power Apps premium trial and **no** admin role | the whole point of the test | trial |
| Python 3 and `pac` on the recording laptop | offline pack and unpack | — |
| Episode 11 not yet recorded against a different `ContosoInspections` | otherwise stop and reconcile the schemas first | — |

## Setup (off camera)

1. **Local checks.** `cd tests/python && python3 -m pytest -q` (expect `75 passed`, about 70 seconds) and
   `cd tests/ContosoInspections.PowerFx.Tests && dotnet test -m:1` (expect `Passed: 46`). Delete `bin`, `obj` and
   `__pycache__` afterwards.
2. **The data-only starting point (needs tenant).**
   ```bash
   cd src/schema
   python3 build_solution.py --profile data --out /tmp/cin-data-only
   pac solution pack -z /tmp/cin-data.zip -f /tmp/cin-data-only        # offline
   ```
   make.powerapps.com > `DEV` > Solutions > **Import solution** > `cin-data.zip`. Expect the solution *Contoso Inspections*
   with four tables. **If the import fails**, copy the exact message into the README gotchas, then use the fallback: create
   the solution and publisher (`cin`) by hand and build the four tables from `src/schema/contosoinspections.schema.json`
   (columns, the autonumber `INS-{SEQNUM:5}`, the three relationships, the alternate key on Site code). Say on camera that
   the tables were created by hand. Do not present designer work as script output.
3. **Seed data (needs tenant).** Import in this order with Tables > table > Import > Import data from Excel or CSV
   (`src/data/*.csv`): `inspectors.csv` (Full name), `sites.csv` (Site name), `inspections.csv`, `items.csv`. For the
   lookups map **Site** to Site name, **Inspector** to Full name (inspections) and **Inspection** to Inspection number
   (items). The autonumber is assigned on import: the eight inspections must come out as `INS-01000` to `INS-01007`; if the
   seed was already used (an earlier take) set it back with `SetAutoNumberSeed` (value 1000 on `cin_inspection`,
   `cin_name`) before importing, otherwise the Inspection column of `items.csv` will not match. Expected states:
   INS-01002, 01003 and 01004 are **Submitted**; 01000 Approved; 01001 Rejected.
4. **Role and profile users (needs tenant).** Admin center > `DEV` > Settings > Users + permissions > Users > `sam.demo` >
   Manage roles > *Basic User* only for now (the back-office role comes in step 17).

## Build checklist (ordered; each line is a recording beat)

Scene ids in brackets match `script.yaml`. Everything here **needs tenant**.

**Data**
1. `[data]` Solutions > Contoso Inspections > Objects: four tables. Open Inspections > Data: eight rows, numbers
   `INS-01000` to `INS-01007`. Mention the autonumber seed (1000) and that it does not travel with the solution.

**App, site map, forms, views**
2. `[designer]` Solutions > Contoso Inspections > **New > App > Model-driven app**, name *Inspection Back Office*,
   unique name `cin_InspectionBackOffice`. In the modern app designer add pages **Dashboard** (after step 9, or add it now
   and fill it later), **Inspections**, **Findings** (inspection items), **Sites**, **Inspectors**. Navigation: one area,
   groups *Overview*, *Review* (Inspections, Findings) and *Reference* (Sites, Inspectors). Save, publish, play.
3. `[forms]` Inspection table > Forms > main form. Header: Status, Score, Inspection date, Owner. Tabs **General** (sections
   *Visit*: Inspection number (read only), Site, Inspector, Inspection date, Status; *Result*: Score, Requires follow-up,
   Follow-up date, Summary), **Findings** (sub grid *Inspection items*, view *Items of an inspection*), **Review** (Reviewer
   notes). Save and publish.
4. `[quickcreate]` Inspection table > Forms > **Quick create** form with Site, Inspector, Inspection date. In the app: + New >
   Inspection > create one for Harbor Warehouse and Alex Demo; expect the next autonumber (`INS-01008`).
5. `[views]` Check or create the views, then show them in the app: *Active Inspections* (default, newest first), *Inspections
   to review* (Status = Submitted: three rows), *Needs follow-up* (Requires follow-up = Yes), and on Inspection items
   *Open critical findings* (Severity = Critical and Resolved on empty). Add all views to the app in the designer.

**Business rules**
6. `[rules]` `[ruleyaml]` Open `src/logic/business-rules.yaml` on screen (it is the plan). Table > **Business rules** > Add
   business rule. Build the five rules with the scope in the plan: (1) *Follow-up date is required when follow-up is needed*,
   scope All Forms; (2) *Approved inspections are locked*, All Forms; (3) *A submitted inspection needs a score*, **Table**;
   (4) *A critical finding cannot be marked as passed* on Inspection item, **Table**; (5) *New findings start as not passed
   when the severity is Major or Critical*, All Forms. Activate all five.
7. `[ruledesigner]` Show rule (3) in the designer. In the app set INS-01006 (Draft) to Submitted with an empty score and save:
   expect the error on Score and no save. Then try rule (4) on a Critical item: tick Passed and save, expect the error.
   Rule (1): tick Requires follow-up, the date appears and is required.

**Business process flow**
8. `[bpf]` `[bpfyaml]` `[bpfscreen]` Solutions > New > Automation > Process > **Business process flow**: name *Inspection
   review*, table Inspection. Stages and steps from `src/logic/inspection-review.bpf.yaml`: **Capture** (Site, Inspector,
   Inspection date, all required), **Findings** (Score, Summary, required), **Review** (Requires follow-up, Follow-up date),
   **Decision** (Status, required). Save, validate, activate. In the app open INS-01003 and show the process bar and the
   stage flyout.

**Dashboard and charts**
9. `[dashboard]` Inspection table > Charts > New: *Inspections by status* (column, count by Status). Inspection item >
   Charts > New: *Open findings by severity* (bar, count by Severity, view *Open critical findings* or a filter on
   Resolved on empty). Solutions > New > Dashboard > 2-column overview (four components): chart + view *Inspections to
   review*, chart + view *Open critical findings*. Name **Inspection overview**, publish, add it as the app's Dashboard
   page.

**Command bar and custom page**
10. `[cmdintro]` App designer > Inspections page > **...** > **Edit command bar** > choose **Power Fx** when asked (this
    creates the command component library).
11. `[approve]` `[cmdscreen]` Main form > New > Command. Labels, icons, **Visible** and **Action** formulas come from
    `src/logic/commands.yaml`: *Approve* and *Reject* on the main form and the main grid, *Flag for follow-up* on the main
    grid, *Review board* on the main form. Paste each formula exactly as in the file. Save and publish. **If a formula is
    rejected** (the designer has its own list of unsupported functions) note the message and adjust: that is a gotcha for the
    README. `Self.Selected.State <> FormMode.New` may need `Self.Selected.State = FormMode.View` or `Edit`.
12. `[reject]` In the app on INS-01003: **Reject** with empty Reviewer notes shows the warning; with notes "Re-check the
    exits." it asks for confirmation and sets Rejected. (Use INS-01004 for Approve so that INS-01003 stays usable; reset
    the status afterwards.)
13. `[flag]` Inspections grid: select two submitted rows > **Flag for follow-up**: both get Requires follow-up = Yes and a
    date two weeks from today. Select none: the button is hidden.
14. `[custompage]` `[namedformulas]` App designer > **Add page** > Custom page > Create new: name **Inspection review
    board**. In Power Apps Studio add the data sources Inspections and Inspection items, then rebuild
    `src/custom-page/Src/App.pa.yaml` and `ReviewBoard.pa.yaml` (named formulas in App > Formulas, then the controls). The
    source files are in the Power Apps source format v3.0: if Studio can import them directly, say so; otherwise it is by
    hand and the formulas are pasted. Save, publish, then back in the app: INS-01002 > **Review board**.
15. `[custompagescreen]` Expect "1 open critical" for INS-01002 (red badge, score 64), pass rate 33%, decision "Reject: open
    critical findings", gallery of two findings. **Open inspection** returns to the form.

**Security**
16. `[security]` Admin center > `DEV` > Settings > Users + permissions > Security roles > **New role** *Inspection Back
    Office*: Create, Read, Write, Delete, Append, Append to, Assign and Share at **Organization** on Inspection and
    Inspection item; Create, Read, Write, Delete, Append, Append to at Organization on Site and Inspector (Custom tables
    tab). Second role *Inspection Field Inspector* as in `src/schema/contosoinspections.schema.json`, `security.roles`.
17. `[securityscreen]` Table Inspection > Reviewer notes > Advanced options > **Enable column security**. Admin center >
    Settings > Users + permissions > **Field security profiles** > New *Inspection reviewer notes*: Reviewer notes with
    Read, Create, Update = Allowed; add `sam.demo`. Assign `sam.demo` the role *Inspection Back Office* (keep Basic User
    if the portal needs it). App designer > Settings/Share: give the app to the role.

**Test as Sam Demo**
18. `[sam]` InPrivate window, sign in as `sam.demo`. Expect: the app is in the list; Overview dashboard loads; INS-01004
    opens; the Review tab shows Reviewer notes and Sam can type in it. Then Admin center > Field security profiles >
    remove `sam.demo` > reload the form: Reviewer notes shows the lock icon, no value. Add Sam back afterwards. As
    `labadmin` the column is always visible: say so, it is the reason for testing as Sam.

**Package**
19. `[pack]` Solutions > Contoso Inspections: check every object is in the solution (add missing ones: Add existing > ...).
    **Export** > Managed (and Unmanaged for the repo). Terminal (offline): `pac solution unpack -z <downloaded>.zip -f
    /tmp/exported` and `ls` the folder. Compare against `src/solution` with `diff -r` and put the real differences in the
    README: this is the first real evidence of what the generator got right.

## Screens to capture (match `screen` scenes in script.yaml)

| Scene | File | What must be on screen |
|---|---|---|
| `data` | `screens/tables.jpg` | Solution objects (four tables) then Inspections data with `INS-01000`... |
| `designer` | `screens/app-designer.jpg` | Modern app designer: area, groups Overview / Review / Reference, preview |
| `quickcreate` | `screens/quick-create.jpg` | Quick create panel with Site, Inspector, Inspection date |
| `forms` | `screens/forms.jpg` | Inspection main form designer: header, tabs General / Findings / Review |
| `views` | `screens/views.jpg` | Inspections grid with the view picker open; Inspections to review (3 rows) |
| `ruledesigner` | `screens/business-rule.jpg` | Rule "A submitted inspection needs a score" in the designer; the error in the running form |
| `bpfscreen` | `screens/bpf.jpg` | BPF designer, then the process bar on INS-01003 with the stage flyout |
| `dashboard` | `screens/dashboard.jpg` | Overview dashboard with both charts and both lists |
| `cmdscreen` | `screens/command-bar.jpg` | Command designer on Approve (Action and Visible formulas), then the confirm dialog and notification |
| `custompagescreen` | `screens/review-board.jpg` | Review board page for INS-01002 |
| `securityscreen` | `screens/security.jpg` | Role privileges grid; field security profile with Reviewer notes and Sam Demo |
| `sam` | `screens/sam-demo.jpg` | Sam's window: app list, dashboard, Review tab; then the lock icon |
| `pack` | `screens/export.jpg` | Export > Managed, object list; terminal `pac solution unpack` listing |

Optional terminal captures for the `suites` code scene: both test commands with their pass counts.

## Masking
- Environment name and org URL (browser address bar, admin center, the Import dialog), tenant name in headers.
- User names and avatars: show `labadmin` and `sam.demo` as the demo identity only; mask the avatar and the account
  menu. Use `pipeline/mask.js`. `series_label: "POWER APPS"` is set in `script.yaml`.
- Never show the real tenant name or any real URL; the seed data is fictional (`@contoso.com`, example addresses).
- Terminal: no `pac auth`, no tokens; `pac solution pack/unpack` only (offline).

## Tear-down
1. Reset any test edits (INS-01003 / 01004 status, follow-up flags) or re-import the seed into a clean copy.
2. Admin center: remove the roles and the field security profile from `sam.demo` unless episode 11 still needs them.
3. Keep the solution *Contoso Inspections* if episode 11 is recorded after this; otherwise Solutions > Contoso Inspections >
   **Delete** (this removes the solution and, for unmanaged, only the container: delete the app, the BPF (deactivate
   first), the custom page, the tables (Inspection item before Inspection before Site and Inspector) and the roles by hand).
4. Delete `/tmp/cin-data-only`, `/tmp/cin-data.zip` and `/tmp/exported`. Close the InPrivate window.
