# Demo shot list — DEVLADLOG Dynamics 365 #10: Reporting & Analytics

Already run in the build container: `python3 -m pytest -q tests` (23 passed, Web API stubbed) and the offline
`pipeline` / `monthly` / `queries` on the fictional sample. **Nothing has run against Dataverse or Power BI yet: all four
`screen` scenes need the lab tenant**, and three assumptions must be confirmed first (step 3).

## Lab environment

No VMs, no Azure resources: cloud tenant only; Power BI Desktop, terminal and browser run on the recording laptop.

| Item | Notes | Cost |
|---|---|---|
| Dynamics 365 **Sales trial** environment (EMEA, created 21 Nov 2026, 30-day trial, ends ~21 Dec 2026) | **Why this one and not `DEV`:** the demo needs the Sales Hub app and its sample opportunities (Dynamics 365 apps can't be installed in the Dataverse-only `DEV`); the opportunities from episode 7 live here. Record **before the trial ends**. Mask the org URL | none (trial) |
| `labadmin` | Runs the terminal, creates the chart (a user-owned chart belongs to whoever creates it, so the chart is looked at as `labadmin` in Sales Hub) | none |
| Power BI Desktop (free app) on the recording laptop | Learn (*Create a Power BI report using data from Dataverse*): needs read privileges on the table, the TDS endpoint enabled in the environment (on by default), and TCP 1433 (or 5558) open from the laptop; proxies often block TDS. No publishing, so no Power BI licence is needed for the capture | none |
| Recording laptop | Python 3.10+, `pip install --user -r requirements.txt`, dark terminal font 18+, browser with `pipeline/mask.js` | none |

## Setup (before recording)

1. Sales Hub as `labadmin`: check the *Opportunities* list has the sample data and the opportunities from episode 7.
   Optionally add one or two of your own with an estimated close date in the next months, so the monthly report has
   several rows (fictional customers only).
2. `export DATAVERSE_URL=https://<sales trial>.crm4.dynamics.com`, `cd src`, `python3 -m reportkit pipeline`: prints the
   table by forecast category. If the environment has no `msdyn_forecastcategory` (it comes with Sales Premium/Enterprise),
   use `--by statuscode` everywhere and say so in the narration.
3. **Verify and note in README** ("Not verified on Learn"):
   - `python3 -m reportkit reconcile` returns OK for FetchXML and `$apply` (exit 0). If the `$apply` request fails with a
     400 on the two-expression `aggregate(... with sum as total,$count as n)`, split it into the two forms Learn shows
     (one request for the sum, one for `$count`) in `apply_by_column` and the test stub, and re-run the tests
   - the group labels print as names (Pipeline, Best case, Committed); if they print numbers the FetchXML result has no
     `FormattedValue` annotation for the group alias (cosmetic: say so)
   - the monthly report has a row per month and, if any opportunity has no estimated close date, a `(none)` row
4. Chart: `python3 -m reportkit chart pipeline` (dry run, `+ ... (dry run)`), then `--apply`, then again (`=` line).
   In Sales Hub → Opportunities (the **Open Opportunities** view) → show the chart pane → chart selector: the chart
   `[MGL demo] Open pipeline by forecast category` should be listed. If the pane doesn't offer it, note where a user chart does
   show (My charts?) and fix the narration and README. Optional second chart: `chart revenue --apply`.
5. Power BI Desktop: Get data → **Dataverse** → server URL as `<org>.crm4.dynamics.com` (no `https://`, no trailing
   slash: Learn lists that as a cause of the "Unable to connect" error) → sign in as `labadmin` → pick the
   **opportunity** table, *Import*. Add a **card** with the sum of the estimated value column and a **column chart**
   (forecast category on the axis, estimated value summed), with a visual filter on **Status = Open** (statecode 0). The
   card must show the same total as `reportkit pipeline`. If it differs, find out why before recording (filter, nulls,
   currency column choice: the tool sums `estimatedvalue`).

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/reportkit-reconcile.jpg` — "Reconcile" (needs tenant)
```bash
python3 -m reportkit pipeline
python3 -m reportkit reconcile
```
The table by forecast category and the OK lines (FetchXML, `$apply`) with the reference total, then the monthly check.
Keep the real output. For the "MISMATCH" example the narration describes, either capture a real one if it happens, or
temporarily change a value in a throwaway opportunity between the two calls (not recommended) or just show the offline
unit-test output labelled as such. Blur ids.

### 2. `screens/reportkit-chart.jpg` — "Create the chart" (needs tenant)
```bash
python3 -m reportkit chart pipeline            # + ... (dry run)
python3 -m reportkit chart pipeline --apply    # + ... created
python3 -m reportkit chart pipeline --apply    # = ... (already exists)
```

### 3. `screens/saleshub-chart.jpg` — "In Sales Hub" (needs tenant)
Sales Hub as `labadmin`, Opportunities list, chart pane open with the new chart selected (columns per forecast
category, value labels). Mask tenant and avatar.

### 4. `screens/powerbi-pipeline.jpg` — "Power BI, the same total" (needs tenant)
Power BI Desktop: the card and the column chart from step 5, total equal to the one in screen 1. Mask the environment
URL (Data source settings, the Transform data pane) and the account.

## Masking checklist
- Org URL, tenant name, UPNs, avatars, opportunity and chart GUIDs in the terminal.
- Only fictional customers (Contoso Retail, the trial's sample companies) and lab users on screen.

## Tear-down
1. Delete the `[MGL demo]` charts (Sales Hub chart pane → manage, or `DELETE userqueryvisualizations(<id>)`).
2. Delete any opportunities you added for the demo.
3. Close Power BI Desktop without saving the `.pbix` (it holds the environment URL), delete exports (`exports/`, CSVs).
