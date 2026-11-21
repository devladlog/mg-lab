# Demo shot list — Power BI #1 Data Modeling & Star Schema

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / tenant / Azure | none. The report is not published, so no workspace and no use of the Fabric/Power BI trial; no sign-in needed |
| Data | The committed star CSVs `src/data/star/*.csv`, copied to `C:\MGLab\power-bi\star\` on the laptop (the semantic model's real data source: Power BI Desktop reads the files itself; no mock involved) |
| Licences / cost | Power BI Desktop is free; cost 0 |
| Recording machine | The Windows lab laptop: current **Power BI Desktop**, signed out (or account masked); terminal B-roll on the same laptop (.NET 8 SDK, Python 3, Node where listed) |

Everything in this episode is local: **no tenant, no workspace, no licence** is needed. Power BI Desktop (free) on a
Windows machine is the only requirement for the screen scenes. Nothing is published to the Power BI service.

## What was verified where

| Step | Verified in the container (Linux) | Needs Windows + Power BI Desktop |
|---|---|---|
| Data generation + star split | yes: pytest, 20 tests | – |
| PBIP / PBIR / PBISM JSON | yes: validated against Microsoft's JSON schemas | **opening the project** (the PBIR report is hand-written) |
| TMDL model | yes: loaded by TOM (`Microsoft.AnalysisServices` 19.120.1), 17 xUnit tests | **refresh** (the M partitions only run in Desktop) |
| Numbers in the visuals | expected values computed from the CSVs (below) | **check them on screen** |

## Prerequisites
- Windows 10/11 PC with the current **Power BI Desktop** (Microsoft Store or download). Cost: free.
- This repo cloned. .NET 8 SDK + Python 3 on the same PC if you also want to record the terminal scenes there
  (they can also be recorded on Linux/macOS, the tools are cross-platform).
- Power BI Desktop option: **File > Options and settings > Options > Global > Data load > Time intelligence**:
  untick *Auto date/time for new files* (we have our own date table; Learn's auto date/time guidance).
- Terminal: dark theme, font 18 pt+, window 1600×900.

## Setup
1. Copy `src/data/star/*.csv` to `C:\MGLab\power-bi\star\` (this is the default value of the `DataFolder` parameter
   in `expressions.tmdl`). Any other folder works: change the parameter in **Transform data > Edit parameters**;
   keep the trailing backslash.
2. Double-click `src/ContosoSales.pbip`. Power BI Desktop opens the report and the semantic model (no data yet: there
   is no `cache.abf`). Select **Refresh**.
   - **If Desktop refuses to open the project** (the report folder is hand-written): open a **blank report**, go to
     **TMDL view**, paste the whole of `src/ContosoSales.SemanticModel/TMDLScripts/create-model.tmdl`, **Apply**,
     then **Refresh**. In **Model view > Model explorer**, select the semantic model and turn on **Discourage implicit
     measures** (the script doesn't carry model-level properties). Then
     **File > Save as > Power BI Project** into a scratch folder. Note what failed in README "gotchas".
3. If Desktop asks for privacy levels / credentials for the CSV files, choose *Organizational* / *Windows*.
4. Check the decimals: in **Table view**, Sales is hidden, so use **Transform data** > Sales query preview:
   the first row (`SO000001`) must show Unit Price **40.41**, not 4041. (Matters on a PC with a decimal comma.)
5. Build the report page **Overview** (the screen scenes below). Save.

## Expected numbers (computed from the committed CSVs)

| Check | Value |
|---|---|
| Sales Amount, total | 1,862,401.98 |
| Sales Amount 2024 / 2025 | 894,929.10 / 967,472.88 |
| Bikes 2024 / Accessories 2024 / Clothing 2024 | 716,095.45 / 120,256.62 / 58,577.03 |
| Bikes 2025 / Accessories 2025 / Clothing 2025 | 780,356.80 / 130,320.98 / 56,795.10 |
| Margin % 2024 and 2025 | 43.7 % |
| Orders | 2,440 (2024: 1,172 · 2025: 1,268) |
| Units | 7,462 |
| Unknown customer (Country = Unknown) | 61,345.69 (133 lines) |

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `modelview` | `screens/model-view.jpg` | **Model view** after refresh. Arrange: Sales centre, Date top, Customer left, Product right, Store bottom. Four solid one-to-many lines with single arrowheads, one **dashed** line Sales[Ship Date] → Date[Date]. Hover the dashed line so both columns highlight. |
| `datapane` | `screens/data-pane.jpg` | **Report view**, Data pane expanded: Sales shows only `Order Number` and the display folders **Margin** (Margin, Margin %) and **Sales** (Orders, Sales Amount, Total Cost, Units). Product expanded with **Product Hierarchy** (Category > Subcategory > Product). Date with **Calendar** hierarchy. No key columns visible. |
| `report` | `screens/report.jpg` | Matrix: rows Product[Category], columns Date[Year], values Sales Amount and Margin %. Values as in the table above (2026 column absent: no orders). Card visual: Orders = 2,440. |
| `gotcha` | `screens/unknown-customer.jpg` | Table visual: Customer[Country], Sales Amount, sorted by Sales Amount descending. Row **Unknown = 61,345.69** visible, no "(Blank)" row. |

Terminal scenes (`pytest`, `lint`, `snowflake`) are code slides rendered from the real output already in
script.yaml; record a terminal clip only if you want B-roll:

```bash
python3 -m pytest tests -v
dotnet run --project src/StarSchemaLinter -- src/ContosoSales.SemanticModel/definition --data src/data/star
dotnet run --project src/StarSchemaLinter -- tests/fixtures/snowflake-model/definition --data tests/fixtures/data; echo "exit $?"
```

Optional B-roll: **TMDL view** with the Date table scripted (drag Date from the Data pane onto the editor).

## Masking
- Nothing tenant-related is on screen (no sign-in needed). If Power BI Desktop shows a signed-in account in the top
  right corner, sign out before recording or mask it with `pipeline/mask.js` / a blur box.
- Mask the Windows user name if it appears in the title bar path (`C:\Users\<name>\...`): record from `C:\MGLab\`.
- All customer names are generated ("Alex Placeholder 001", ...), stores are "Contoso ...". Nothing else to mask.

## Tear-down
- Close Power BI Desktop without saving changes to the repo copy (or save the project into a scratch folder).
- Delete `C:\MGLab\power-bi\star\` if you don't need it for episode 2 (episode 2 uses the same CSVs).
- Nothing to remove in any tenant.
