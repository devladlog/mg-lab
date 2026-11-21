# Demo shot list — Power BI #4 Visualization Design & Custom Visuals

**Local only**, like episodes 1–3: no tenant, workspace or licence. Power BI Desktop (free) on Windows for the
report and the custom visual; everything else was built and tested in the Linux container.

## What was verified where

| Step | Verified in the container | Needs Windows + Power BI Desktop |
|---|---|---|
| Theme JSON | Desktop theme schema 2.159; `theme-check`: 0 findings | **importing / applying it** |
| Generated PBIR report (1 page, 7 visuals) | every file against Microsoft's PBIR schemas; `report-lint`: 0 findings; fields exist in the TMDL model | **opening it**, visuals rendering |
| Target bullet (.pbiviz) | 16 unit tests (logic + SVG tree, incl. high contrast); `pbiviz package` + certification audit OK | **importing and rendering it** |
| Expected numbers | `tests/test_expected.py` from the generated data | compare on screen |

If the report doesn't open or a visual shows an error, note the exact message (it names the file) and tell the
maintainer before publishing. Fallback for the whole page: build the same 7 visuals by hand from the table in
`src/tools/build_report.py` (grid positions are in the README).

## Prerequisites
- Windows PC with current Power BI Desktop. Cost: free.
- The star CSVs from episode 1/2 in `C:\MGLab\power-bi\star\` (`src/data/star` of episode 2).
- Node.js 20.19+ on the build machine (container or Windows) to package the visual:
  `cd src/target-bullet && npm ci --no-audit --no-fund && npx pbiviz package` → copy
  `dist/*.pbiviz` to `C:\MGLab\power-bi\`.
- Auto date/time off (as in episode 1).

## Setup
1. Open `src/ContosoSales.pbip` (this episode's copy) and **Refresh**. If the semantic model doesn't open, use
   episode 2's TMDL view fallback (`create-model.tmdl`) into a blank report, then rebuild the page by hand.
2. Page **Sales overview** should show 7 visuals. Set the **Year** slicer to **2025**.
3. Check the theme: the first series of the line chart must be blue `#0B5CAD`, the page background off-white. If
   not: **Design > Import theme** → `src/themes/ContosoBikes.json` (the documented fallback for a hand-registered
   theme; note in the README which path worked).
4. **File > Options and settings > Options > Current file > Report settings > Develop a visual** (on, this session
   only). Then Visualizations pane **…** > **Import a visual from a file** > the `.pbiviz` > Import.
5. Click the **Target Bullet** icon, place it in the free cell at the bottom right (x 648, y 432, 608 x 264 in the
   Selection/Format pane), fields: **Category** = `Product[Category]`, **Actual** = `Sales Amount`,
   **Target** = `Sales PY`. Title *Sales vs prior year by category*, alt text *Bullet per category: 2025 sales
   against the prior year, with marker and percentage.*
6. For the high-contrast shot: Windows **Settings > Accessibility > Contrast themes** → e.g. *Night sky* → Apply.
   Desktop picks it up automatically (Learn). Switch back to *None* afterwards.

## Expected results (Year = 2025)

| Visual | Expected |
|---|---|
| Sales amount / Sales growth vs prior year / Orders | 967,472.88 / 8.1% / 1,268 |
| Bar chart by category | Bikes 780,356.80 > Accessories 130,320.98 > Clothing 56,795.10 |
| Target bullet, tolerance 5 | Accessories ▲ +8.4% · Bikes ▲ +9.0% · Clothing ● -3.0% |
| Target bullet, tolerance 2 | Clothing becomes ▼ -3.0% (colour changes from mustard to burnt orange) |

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `reportscreen` | `screens/viz-report-overview.jpg` | Report view, *Sales overview*, Year = 2025, all 7 visuals, theme applied, bottom-right cell empty. Optional second take with View > Selection > Tab order visible (order: 3 cards, slicer, line, bar, table). |
| `importscreen` | `screens/viz-target-bullet.jpg` | Target Bullet in the bottom-right cell with the values above; Format pane open on **Bands** with *On-target tolerance (%)* = 5. Second take after setting it to 2 (Clothing ▼). |
| `hcscreen` | `screens/viz-high-contrast.jpg` | Same page under a Windows contrast theme: Target Bullet bars outlined in the foreground colour, markers and percentages visible, core visuals also in high contrast. |

Optional B-roll: Design ribbon > Customize theme showing the Contoso Bikes colours; the Format pane > General > Alt
text of a card; VS Code with `visual.json` of `kpiSales` next to Desktop. Terminal scenes (`gotcha`, `lint`,
`package`) are rendered from real output already in script.yaml. B-roll commands:

```bash
python3 src/tools/theme_check.py tests/fixtures/learn-example-theme.json
python3 src/tools/report_lint.py tests/fixtures/messy-report --model src/ContosoSales.SemanticModel/definition --max-visuals 2
cd src/target-bullet && npm test && npx pbiviz package --certification-audit
```

## Masking
- No tenant data on screen. Sign out of Power BI Desktop (top right) or blur the account name.
- Record from `C:\MGLab\` so no Windows user name shows in paths (the import dialog shows the folder).
- `pbiviz.json` author is "MG Lab" / `mglab@example.com`; the visual GUID is generated, not tied to any tenant.
- All data is generated (customers "Alex Placeholder 001", stores "Contoso …").

## Tear-down
- Close Desktop without saving into the repo (or save into a scratch folder). Importing the visual makes Desktop add
  a `CustomVisuals/` folder and `resourcePackages` entries, and it may rewrite the generated report files: discard
  those changes with git, then `python3 src/tools/build_report.py --check` must pass again.
- Switch Windows contrast theme back to *None*. Unpin the visual from the Visualizations pane if you pinned it.
- Delete `C:\MGLab\power-bi\*.pbiviz` when done. Nothing to remove in any tenant.
