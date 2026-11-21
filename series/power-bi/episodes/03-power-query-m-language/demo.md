# Demo shot list — Power BI #3 Power Query & M Language

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / tenant / Azure | none. The report is not published, so no workspace and no use of the Fabric/Power BI trial; no sign-in needed |
| Data | The 24 export CSVs + `_README.txt` of `src/data/exports/`, copied to `C:\MGLab\power-bi\exports\` (the semantic model's real data source: Power BI Desktop reads the files itself; no mock involved) |
| Licences / cost | Power BI Desktop is free; cost 0 |
| Recording machine | The Windows lab laptop: current **Power BI Desktop**, signed out (or account masked); terminal B-roll on the same laptop (.NET 8 SDK, Python 3, Node where listed) |

Like episodes 1 and 2, this is **local only**: no tenant, workspace or licence. Power BI Desktop (free) on Windows
runs the M; everything else was built and tested in the Linux container.

## What was verified where

| Step | Verified in the container | Needs Windows + Power BI Desktop |
|---|---|---|
| 9 M queries (`src/queries/*.pq`) | parsed by Microsoft's Power Query parser; `pq-lint --strict`: 0 findings; 12 node tests | **evaluating them** (refresh) |
| TMDL model with the queries as shared expressions + partitions | loaded by TOM (`tmdl-check`: 0 errors, 7 xUnit tests); `sync_tmdl.py --check` | opening the PBIP, refresh |
| Expected results | Python mirror of every step, 40 pytest tests (equals the episode 1 star) | **compare on screen** (table below) |

The M has never been evaluated. If refresh fails, the most likely suspects, in order: `Date.FromText` with the quoted
format `"dd'/'MM'/'yyyy"`; `Currency.Type` with culture `"pt-PT"` on values like `47,40`; `Table.InsertRows` with
the Unknown customer record; `Csv.Document` with `Columns = 19`. Note the exact error, fix the `.pq` file, run
`python3 src/tools/sync_tmdl.py`, and tell the maintainer before publishing.

## Prerequisites
- Windows PC with current Power BI Desktop. Cost: free.
- Auto date/time off (File > Options and settings > Options > Global > Data load), as in episode 1.
- Copy `src/data/exports/` (24 CSV files + `_README.txt`) to `C:\MGLab\power-bi\exports\`. Keep the `_README.txt`:
  it's part of the demo (the extension filter).

## Setup
1. Open `src/ContosoSales.pbip` (this episode's copy). If the project doesn't open, fallback: blank report →
   **TMDL view** → paste `src/ContosoSales.SemanticModel/TMDLScripts/create-model.tmdl` → **Apply**, then set
   `discourageImplicitMeasures` in Model view (same fallback as episode 1).
2. If the folder isn't `C:\MGLab\power-bi\exports\`: Home > Transform data > Edit parameters > `ExportFolder`
   (keep the trailing backslash).
3. **Refresh**. If Desktop asks about privacy levels or shows a Formula.Firewall error, set the folder source to
   *Organizational* (File > Options and settings > Data source settings) and refresh again; note it for the README.
4. Home > **Transform data** to open the Power Query editor. Check that `SalesExport`, `fnReadExport`, `fnDimension`
   and `ExportFolder` appear as queries and that `SalesExport` has **Enable load** unchecked (right-click). If the
   shared expressions don't show load disabled, note what Desktop shows.
5. Report view: on a scratch page add three **Card** visuals (`Sales Amount`, `Orders`, `Units`) and a **Table**
   with `Date[Year]` and `Sales Amount`. Don't save the page into the repo.
6. Optional check for the README gotcha (don't keep it): in the editor, duplicate `fnReadExport` as a scratch query,
   change both formats to `"dd/MM/yyyy"` and invoke it on one file. Note whether the dates load or error. Delete the
   scratch query.

## Expected results (`src/reference/expected/summary.json`)

| Check | Expected |
|---|---|
| Sales rows (Table view status bar) | **4,071** |
| Customer / Product / Store / Date rows | 301 (first row: key -1, *Unknown customer*) / 19 / 5 / 1,096 (2024-01-01 … 2026-12-31) |
| Sales Amount | **1,862,401.98** (2024: 894,929.10 · 2025: 967,472.88) |
| Orders / Units | 2,440 / 7,462 |
| Unknown customer sales | 61,345.69 |

If Sales Amount shows **2,019,894.31**, the de-duplication didn't run; **1,902,513.76** means the older copy of the
re-exported lines survived (the gotcha). Either way: stop and report.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `editor` | `screens/pq-editor-queries.jpg` | Power Query editor. Queries pane: `ExportFolder` (parameter), `fnReadExport`, `fnDimension` (functions), `SalesExport`, `Product`, `Customer`, `Store`, `Date`, `Sales`. `SalesExport` selected with the right-click menu open (Enable load unchecked) and the Applied steps `Files … Result` visible on the right. Highlight *Buffered*. |
| `refresh` | `screens/pq-data-view-rowcounts.jpg` | Table view, `Sales` selected, status bar *Table: Sales (4,071 rows)*. Data pane with the five tables. |
| `totals` | `screens/pq-report-totals.jpg` | Report view scratch page: cards 1,862,401.98 / 2,440 / 7,462 and the Year table (894,929.10 / 967,472.88). |

Optional B-roll: Advanced Editor on `SalesExport`; formula bar on the `Buffered` step; `Customer` in Table view with
the Unknown row at the top; the Folder.Files step showing the `_README.txt` row before `CsvOnly` removes it.

Terminal scenes (`lint`, the gotcha numbers) are rendered from real output already in script.yaml. B-roll commands:

```bash
python3 src/reference/pq_reference.py
cd src/pq-lint && npm ci --no-audit --no-fund && npm test
node dist/src/cli.js ../../tests/fixtures/ui-generated
node dist/src/cli.js ../queries --strict
```

## Masking
- No tenant data on screen. Sign out of Power BI Desktop (top right) or blur the account name.
- Record from `C:\MGLab\` so no Windows user name shows in paths (the `ExportFolder` value is visible in the editor).
- All names are generated (customers "Alex Placeholder 001", stores "Contoso …"). The fixture path
  `C:\Users\AlexDemo\...` is fictional.

## Tear-down
- Close Desktop without saving into the repo (or save into a scratch folder). If Desktop rewrote files under
  `src/ContosoSales.SemanticModel/` (it may add `.pbi/`, `diagramLayout.json`, lineage tags or annotations on the
  expressions), discard those changes with git, or, if they're needed, copy the M back into `src/queries/` and run
  `sync_tmdl.py` so the `.pq` files stay the source of truth.
- Delete `C:\MGLab\power-bi\exports\` when the series no longer needs it. Nothing to remove in any tenant.
