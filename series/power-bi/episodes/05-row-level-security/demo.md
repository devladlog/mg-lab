# Demo shot list — Power BI #5 Row-Level Security

## Lab environment

No VM and no Azure resource. Everything runs on the **Windows recording laptop** and in the **lab tenant**.

| What | Details | Cost |
|---|---|---|
| Recording laptop (Windows) | Power BI Desktop (current), PowerShell 7, Windows Terminal, a browser with an InPrivate window | free |
| PowerShell module | `MicrosoftPowerBIMgmt` (`Install-Module MicrosoftPowerBIMgmt -Scope CurrentUser`) | free |
| Lab tenant: capacity | Fabric + Power BI 60-day trial (West Europe) from `series/LAB.md` | trial, €0 |
| Lab tenant: workspace | New workspace **Contoso Sales (Lab)**, assigned to the trial capacity, admin `labadmin` (kept for episode 6) | €0 |
| Lab tenant: users | `labadmin` (records, workspace Admin), `alex.demo`, `sam.demo`, `riley.demo`, `taylor.demo`, `jordan.demo` (E5 = Power BI Pro included) | trial |
| Tenant setting | Admin portal > Tenant settings > Integration settings > **Dataset Execute Queries REST API** enabled (check only; enable for the lab if it's off) | €0 |

Screens are recorded in Power BI Desktop and in the browser on the laptop (lab tenant), plus Windows Terminal.

## What was verified where

| Step | Verified in the container | Needs Windows / the tenant |
|---|---|---|
| Roles, mapping table, relationship flags (TMDL) | parsed by TOM 19.120.1; `rls-lint`: 0 errors, 1 warning (RLS009) | **Desktop opening the PBIP, View as** |
| Expected numbers per user | Python reference + 42 pytest | compare on screen |
| Report (2 pages, 14 visuals) | Microsoft's PBIR schemas, `report-lint` 0 findings | **rendering in Desktop / service** |
| `Test-RlsMatrix.ps1` | 11 Pester tests with the REST cmdlet mocked; script parses | **real run against the service** (needs tenant) |

## Prerequisites (on the laptop)
1. `C:\MGLab\power-bi\star\` holds the episode 2 star CSVs (`src/data/star` of episode 2) **plus**
   `src/data/store_access.csv` of this episode.
2. Episode folder copied to `C:\MGLab\power-bi\ep05\` (so no Windows user name shows in paths).
3. Signed in to Power BI Desktop as `labadmin` (needed to publish).

## Setup
1. Open `C:\MGLab\power-bi\ep05\src\ContosoSales.pbip`. **Transform data > Edit parameters > UpnDomain** = the lab
   tenant's sign-in domain (the part after `@` in `alex.demo@...`). Close & Apply, then **Refresh**.
   Fallback if the semantic model doesn't open: blank report > TMDL view > run episode 2's `create-model.tmdl`,
   then this episode's `TMDLScripts/add-rls.tmdl` (Preview, Apply), Refresh; rebuild the *Store security* page by
   hand from `src/tools/build_report.py` (`SECURITY` list).
2. Without View as, page **Store security** must show Visible stores **5**, Visible customers **301**, Sales amount
   **1,862,401.98** (you're the author, no role applied).
3. **Modeling > Manage roles**: check that *Store Managers* (DAX editor shows the two filters) and *Head Office*
   exist. Close without changes.
4. Publish: **Home > Publish** > workspace **Contoso Sales (Lab)** (create it first in the service on the trial
   capacity if it doesn't exist).
5. In the service, workspace **Manage access**: add `alex.demo`, `sam.demo`, `riley.demo`, `taylor.demo`,
   `jordan.demo` as **Viewer**.
6. Semantic model **ContosoSales > More options > Security**: *Store Managers* = Alex, Sam, Riley, Taylor;
   *Head Office* = Jordan (as in `src/data/role_members.csv`). Save.
7. Note the workspace ID and semantic model ID (from the URL `.../groups/<workspace>/datasets/<model>/...`); never
   on screen.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `desktopscreen` | `screens/rls-desktop-view-as.jpg` | Short cut of **Modeling > Manage roles** with *Store Managers* open in the DAX editor. Then **Modeling > View as > Other user** = `alex.demo@<domain>`, check **Store Managers**, OK. Page *Store security*: banner "Now viewing report as", Signed in as `alex.demo@<domain>` (blur the domain), Visible stores **1**, Visible customers **247**, Sales amount **389,707.34**; table: Contoso Lisboa, Portugal, Store, 389,707.34, 483; customer slicer shows a shorter list. Second take: Other user `nobody.demo@<domain>` + Store Managers: Visible stores **0**/blank, Sales amount blank, empty table and slicer. |
| `securityscreen` | `screens/rls-service-security.jpg` | Service, semantic model **Security** page: *Store Managers (4)* with Alex Demo, Sam Demo, Riley Demo, Taylor Demo; *Head Office (1)* with Jordan Demo. Then **…** next to Store Managers > **Test as role** > **Now viewing as** > Riley Demo: *Store security* page with Visible stores **3** (Lisboa, Online, Porto), Sales amount **1,111,159.04**, customers **300**. Check what the *Signed in as* card shows (Riley's UPN or labadmin's) and tell the maintainer, so the narration can be adjusted. |
| `runscreen` | `screens/rls-matrix-pass.jpg` | Windows Terminal, PowerShell 7, in `C:\MGLab\power-bi\ep05`. Sign in **before** recording: `Connect-PowerBIServiceAccount` (as labadmin). Recorded command: `./src/service/Test-RlsMatrix.ps1 -WorkspaceId $ws -DatasetId $ds -UpnDomain $domain` with the three variables set off camera. Expected table: alex.demo 1 / 247 / 389,707.34 PASS · sam.demo 1 / 243 / 366,058.87 PASS · riley.demo 3 / 300 / 1,111,159.04 PASS · taylor.demo 1 / 242 / 385,184.07 PASS · jordan.demo 5 / 301 / 1,862,401.98 PASS, last line `5 user(s), 5 passed, 0 failed`. |
| `gotcha` | `screens/rls-gotcha-contributor.jpg` | Workspace **Manage access**: change Sam Demo from Viewer to **Contributor**. Rerun the command: expected `sam.demo ... FAIL stores 5, expected 1; customers 301, expected 243; ...` and `5 user(s), 4 passed, 1 failed`. **If Sam's row still passes** (impersonation may not reflect the workspace role, undocumented), capture instead an InPrivate window signed in as `sam.demo` opening the report: *Store security* with Visible stores **5**. Compose: Manage access panel left, terminal or Sam's window right. |

Also check (no capture needed): while viewing as Alex, add a temporary card with **Sales by Ship Date** on the
Store security page. It must show **389,707.34** and no error (that's the measure `rls-lint` warns about, RLS009).
Delete the card afterwards. Report the result to the maintainer either way.

Terminal scenes (`leak`, `lint`, `matrix`, `testcode`) are rendered from real output already in script.yaml.
B-roll commands (container or laptop):

```bash
dotnet run --project src/RlsLint -- src/ContosoSales.SemanticModel/definition --sensitive Customer
python3 src/reference/rls_reference.py
pwsh -NoProfile -Command "Invoke-Pester ./tests/RlsMatrix.Tests.ps1 -Output Detailed"
```

## Masking
- The **tenant domain** appears in the *Signed in as* card, the View as banner and dialog, Test as role and the
  workspace member list (as e-mail addresses): blur it in every capture (`pipeline/mask.js` in the browser).
  `Test-RlsMatrix.ps1` prints aliases only; error messages could contain the UPN, so check the FAIL details.
- Workspace and semantic model IDs: never typed on screen (variables set before recording); blur the browser URL.
- Account picture / name in Desktop and the service: blur or show *Lab Admin* only.
- All data is generated (customers "Alex Placeholder 001", stores "Contoso …").

## Tear-down
- Set Sam Demo back to **Viewer** right after the gotcha shot.
- If episode 6 is recorded next, **keep** workspace *Contoso Sales (Lab)*, its access list and the role members
  (episode 6 publishes the app to the same users). Otherwise: remove the five users from the workspace, clear the
  role members, delete the workspace.
- In Desktop, close without saving into the repo (or discard the changes with git): the `UpnDomain` value must never
  be committed. `python3 -m pytest tests -q` must still pass (one test checks the default is `contoso.com`).
- Nothing to remove in Azure; no cost beyond the existing trials.
