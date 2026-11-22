# Demo shot list — Power BI #8 Performance Tuning & Optimization

## Lab environment

No VM, no Azure resource and **no tenant sign-in**: this episode is recorded entirely in Power BI Desktop, DAX Studio and a terminal on
the recording laptop (`series/LAB.md`). The Power BI service is not needed.

| What | Details | Cost |
|---|---|---|
| Recording laptop (Windows) | Power BI Desktop (current release), Python 3.10+ (`py`/`python` on PATH; only the standard library is used), Windows Terminal. At least 16 GB RAM is advisable: two Import models of 2,000,000 lines are open one after the other (not measured) | free |
| Data folder | `C:\ContosoBikesPerf`, written by `gen_sales.py --rows 2000000` (177 MB of fictional CSV, about 25 seconds in the container) | free |
| Project folder | `src/` copied to `C:\MGLab\power-bi\ep08\src` (the two `.pbip` projects, `tools`, `queries`, `results`) | free |
| DAX Studio 3.6.x (free, open source, Ms-RL) | **All Users** install, so Power BI Desktop shows it in the External Tools ribbon: `winget install -e --id DaxStudio.DaxStudio --scope machine` (UAC prompt: the owner approves it). Without it, `prepare` downloads the portable build into `C:\MGLab\tools\DaxStudio` (no admin; no External Tools button, connect through *Power BI / SSDT Model*) | free |
| Lab users / tenant | none | — |

Screens are recorded on the laptop only. Nothing is recorded from the container.

## What was verified where

| Step | Verified in the container | Needs Desktop (recording day) |
|---|---|---|
| Generator, totals, data reduction (distinct values per column, before and after, totals identical, every month and store total identical) | pytest on a 200,000-line and a 20,000-line export; totals for 2,000,000 lines committed in `src/expected/totals-2m.json` | — |
| Model definitions | TMDL loaded by the Tabular Object Model (both models); every partition parsed by Microsoft's Power Query parser (`pq-lint`); column names checked against the CSV header | **the first run of the M** (refresh), and that both `.pbip` projects open in Desktop |
| Lint rules PF001-PF011 | mutation tests: each rule fires when its problem is added to the tuned model, the tuned model is clean | — |
| Reports | PBIR schemas, report lint, layout spec | whether Desktop opens them |
| Performance Analyzer timings, memory sizes, refresh time | — | **all of it: no timing was measured in the container** |
| DAX queries in `src/queries/` | file structure and names only | **run in DAX query view** |

## Setup (off camera, once)

1. Copy `src/` to `C:\MGLab\power-bi\ep08\src`. In a terminal there:
   `python data\gen_sales.py --rows 2000000 --out C:\ContosoBikesPerf` (expect `wrote 2,000,000 order lines + 4 dimensions ... (176.5 MB)`).
2. Check the expected card values once: `python tools\expected_totals.py C:\ContosoBikesPerf` must print the numbers in
   `src\expected\totals-2m.json` (Sales amount 2,846,324,198.90; Orders 799,651; Units 5,999,533; Margin 40.0%;
   Online sales 567,943,508.50; growth 2024 vs 2023 -0.3%).
3. Open `ContosoPerf.Before.pbip` in Desktop. **Transform data > Edit parameters**: `DataFolder` = `C:\ContosoBikesPerf` if
   different. **Refresh** and note the duration (the refresh of the before model is part of the story). Save.
4. Close it, open `ContosoPerf.After.pbip`, same parameter, **Refresh**, note the duration. In **File > Options and settings >
   Options > Current File**, section *Time intelligence*, *Auto date/time* must be **off** (it should be: this file has
   no auto date/time table). Save, and look at the changes Desktop makes to the project files (see "Record").
5. `src\results\performance-analyzer.template.csv` copied to `src\results\performance-analyzer.csv` for the numbers.

## Steps and screens (match the `screen` scenes in script.yaml)

| Scene id | File | Steps and what must be on screen |
|---|---|---|
| `pabefore` | `screens/perf-before.jpg` | `ContosoPerf.Before.pbip`, page *Executive*. **Optimize** ribbon > **Performance Analyzer** > **Start recording** > **Refresh visuals**. Expand the visuals: each duration split into categories (Learn: for example the time the DAX query took to run; record the category names you see). Keep the slowest visual in view with its duration. Do the run twice and record the second (warm) one; type all durations into `performance-analyzer.csv` (column `before_ms`, one row per visual, the visual names are the ones in the Selection pane / template). |
| `sizescreen` | `screens/perf-sizes.jpg` | Same file, **DAX query view**: open `queries/01-column-sizes.dax` (paste it), **Run**. Result grid sorted by `DICTIONARY_SIZE` descending: the Sales columns on top (recorded 21 Nov 2026, 2M lines: *Line Ref* 62.3 MB, *Order Timestamp* 40.1 MB, *Order Number* 26.8 MB, *Note* 10.3 MB; the narration names them in that order). |
| `afterscreen` | `screens/perf-after.jpg` | `ContosoPerf.After.pbip`, page *Executive* (7 visuals). Same recording (cleared pane, same year selection, second run). Then DAX query view with the same query: the big dictionaries are gone (no LineRef, Note, OrderTimestamp). Type the durations into the csv (`after_ms`; for `tableLines` leave the cell empty: that visual moved to the page *Order lines*). |
| `servertimings` | `screens/perf-server-timings.jpg` | Recorded **after** `afterscreen` (the After model must be open), shown after `daxfix` in the video. **External Tools** ribbon > **DAX Studio** (opens connected). Home: **Server Timings** on, **Clear on Run** on. Open `queries/04-server-timings-yoy-twice.dax` > Run > *Server Timings* tab (Total, FE, SE, SE queries, SE cache, xmSQL). Same for `queries/05-server-timings-yoy-var.dax`. Then **Advanced > Run Benchmark** (5 cold, 5 warm) on each: *Summary* tab. **Record the real numbers**: the narration is number-free; if the variable version is not faster, add a sentence (the engine can reuse a storage engine result, so the gap may be small). |
| `vertipaq` | `screens/perf-vertipaq.jpg` | Off camera, while the Before model is open: DAX Studio > **Advanced > Export Metrics** > `C:\MGLab\power-bi\ep08\src\results\ContosoPerf.Before.vpax`. On camera, on the After model: **Advanced > View Metrics** (defaults) > *Summary* (total size) and *Columns* sorted by total size; then **Advanced > Import Metrics** > the Before `.vpax`: Line Ref, Order Timestamp, Order Number, Note on top. **Record both totals and the top five columns.** |
| `comparescreen` | `screens/perf-compare.jpg` | Terminal in `C:\MGLab\power-bi\ep08\src`: `python tools\perf_compare.py results\performance-analyzer.csv`. Then both reports' cards side by side (Sales amount, Margin percent, Growth vs prior year): identical in both (expected values above). Optional: **View > Performance Analyzer** on the page *Order lines* with the store slicer set to *Contoso Madrid*. |

Optional scenes, if time allows (code scenes already cover them, no extra screen scene in the script):

- DAX query view, `queries/02-online-sales-before-after.dax` on the after model: the store rows show the gotcha
  (expected: the FILTER version shows the online shop's sales on **every** store row; the KEEPFILTERS version only on
  *Contoso Online*; the grand total is the same). **Record what it really returns**: the `gotcha` narration assumes this
  (it follows from Learn's "replaces any filters applied to the table"), and must be corrected if the grid differs.
- `queries/03-yoy-before-after.dax`: both columns equal; compare the run times.

Terminal B-roll (no Desktop needed), from `src`:

```
python tools\perf_lint.py --model ContosoPerf.Before.SemanticModel\definition --report ContosoPerf.Before.Report --profile expected\reduction-200k.json --profile-side before --brief
python tools\reduce_demo.py C:\ContosoBikesPerf200k      # 200,000 lines: python data\gen_sales.py --rows 200000 --out C:\ContosoBikesPerf200k
python tools\perf_lint.py --model ContosoPerf.After.SemanticModel\definition --report ContosoPerf.After.Report --strict
```

## Things to record and report (the README and the narration depend on them)

- Do both `.pbip` projects open in Desktop and refresh as they are? (Never opened in Desktop; the M never ran.) Does the
  Power Query partition of *Sales* with `Table.TransformColumns` over 2,000,000 lines finish in reasonable time?
- Refresh duration of both models, and the memory Desktop uses (Task Manager, `msmdsrv`) after refresh.
- The real top 5 columns by `DICTIONARY_SIZE` before and after, with the sizes. Does `INFO.STORAGETABLECOLUMNS()` run in
  DAX query view of a PBIP Desktop file (the Learn page says it needs write permission and not a live connection)? Does
  the `ORDER BY [DICTIONARY_SIZE] DESC` in `01-column-sizes.dax` work as written?
- Performance Analyzer: the slowest visual before and after, and whether the *Order lines* table is the slowest.
  Is the improvement mostly the visual count, the DAX or the smaller model? (Revert one change at a time if there is time:
  the lint output says where to look, not what pays.)
- Does Desktop add its own `LocalDateTable_*` tables to the before project when *Auto date/time* is on for the file (the
  table in the before model is a hand-made stand-in for it), and which annotation or property in the TMDL records the option?
  (Send the diff.)
- The two DAX queries above: what they return.
- DAX Studio: Server Timings of `04`/`05` (Total, FE, SE, SE queries) and the benchmark summary; View Metrics totals before/after and the top five columns. Does the External Tools button open DAX Studio already connected to the PBIP model?

## Masking
- DAX Studio: don't open the File > Recent list, don't sign in (account area top right stays empty), type `C:\MGLab` paths in the Open/Export dialogs instead of browsing.
- Nothing from the tenant is on screen. Blur the Windows user name in paths (`C:\Users\...`) if the file dialog shows it.
- All data is generated and fictional (Contoso stores, `Customer 00042`).

## Tear-down
- The `.vpax` export lives in the working copy (`C:\MGLab\power-bi\ep08\src\results`) and goes with it. DAX Studio can stay installed.
- Delete `C:\ContosoBikesPerf` (177 MB) and the 200,000-line folder; close Desktop without saving the refreshed data into the repo.
- Don't commit `.pbi` cache files or the CSVs: the repository holds the generator, not the data. No Azure cost, nothing to unpublish.
