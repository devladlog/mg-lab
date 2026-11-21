# Demo shot list — Power BI #11 Composite Models & DirectQuery

## Lab environment

This episode runs on the lab network, not in the cloud (`series/LAB.md`). **CON-SQL01** is SQL Server 2022 Developer at
10.50.0.30 (default instance, TCP 1433, mixed authentication) on the Hyper-V network 10.50.0.0/24. The recording laptop
runs Power BI Desktop and reaches that VM. Part B needs the workspace `Contoso Sales (Lab)` on the Fabric trial, with the
semantic model `ContosoSales` of episode 1 published. No Azure resource is created, so there is no resource group to tear down.

| What | Details | Cost |
|---|---|---|
| SQL Server | CON-SQL01, a new database `ContosoBikesDW` created by `src/sql/01-create-database.sql` | free |
| SQL login | a SQL login with `db_owner` on `ContosoBikesDW`, typed in Desktop's credential dialog. The password is never in a file | free |
| Desktop | current release; the preview feature **Power BI Project (.pbip) save option** is on | free |
| Power BI service | workspace `Contoso Sales (Lab)` (Fabric trial), user `alex.demo` with Build permission on `ContosoSales` (Part B only) | free (trial) |
| Tools | SSMS or `sqlcmd` on the laptop, Python 3.10+ for `tools/make_budget.py` | free |

## What was verified where

| Step | Verified in the container | Needs the lab VM / Desktop / tenant (recording day) |
|---|---|---|
| Data and view logic | the same tables, view and scale-up generated for SQLite: 4,071 lines, 1,862,401.98, 3,947 aggregation rows, 2,035,500 lines after scale-up | the T-SQL on SQL Server 2022 (needs the lab VM): only parsed by sqlglot here |
| TMDL model, `alternateOf`, modes | loaded by the Tabular Object Model; composite-lint rules CM001-CM006 and mutated copies | whether Desktop opens the PBIP, maps `decimal(18,2)` as expected, and accepts the aggregations (needs Desktop) |
| Hit and miss | a prediction from Learn's rules (`--explain`) | **the real behaviour**: which query reaches SQL Server (needs the lab VM and Desktop) |
| DAX queries | none: no engine here | all six files in `src/queries` (needs Desktop) |
| Part B composite on a published model | the budget CSV is generated and checked | the whole flow (needs tenant) |

## Setup (off camera, once)

1. On CON-SQL01 (SSMS, as a sysadmin): run `src/sql/01-create-database.sql`, `02-load-data.sql`, `03-agg-view.sql`, then
   `05-checks.sql`. Expected: 4,071 order lines, Sales Amount 1,862,401.98, Units 7,462, 3,947 aggregation rows.
   `python3 src/tools/expected.py` prints the same numbers.
2. Run `04-scale-up.sql` (it adds 499 copies of the lines, 2,035,500 in all; allow a few minutes) and `05-checks.sql` again:
   Sales Amount 931,200,990.00, aggregation rows still 3,947. The Sales table is now big enough to matter.
3. Open `src\ContosoSalesComposite.pbip` in Desktop. If `SqlServer` or `SqlDatabase` need changing: **Transform data >
   Edit parameters**. Sign in with the SQL login. Check the storage modes in Model view before recording. (Needs Desktop:
   if Desktop refuses a file, write down the message and fix the TMDL before the recording.)
4. Optional rehearsal of the prediction: `dotnet src/CompositeLint/bin/Debug/net10.0/composite-lint.dll
   src/ContosoSalesComposite.SemanticModel/definition --explain` after `dotnet build -m:1 src/CompositeLint`.

## Steps and screens (match the `screen` scenes in script.yaml)

| Scene id | File | Steps and what must be on screen |
|---|---|---|
| `model` | `screens/model-view.jpg` | Desktop, **Model view**: Sales = DirectQuery, Sales Agg = Import (hidden), Date, Product, Customer, Store = Dual (needs Desktop). Open **Manage aggregations** on Sales Agg: the mapping of the five columns. Relationships drawn as regular (solid) lines |
| `observe` | `screens/sql-observe.jpg` | SSMS on CON-SQL01. Run `07-clear-plan-cache.sql`. In Desktop, DAX query view, run `queries/01-hit-sales-by-year-category.dax`. Run `06-observe-directquery.sql`: no row for it. Run `queries/02-miss-sales-by-customer-country.dax`, then `06` again: one statement over FactSales and DimCustomer. Write down whether the hit really leaves nothing (needs the lab VM and Desktop) |
| `budget` | `screens/budget-composite.jpg` | Part B (needs tenant): new report with a live connection to `ContosoSales`, **Make changes to this model**, add `src/data/budget/budget.csv` (Import), relate Budget to Store (store name) and Date. Matrix by store for 2025 with Sales Amount, Budget Amount and `queries/06-sales-vs-budget.dax` as the measure. Show that the new relationships are drawn as limited |

## Not a screen scene, but record it

- `queries/03` and `queries/05`: the distinct count and the mixed visual. Say what SQL Server saw, as it is, even if it
  differs from the prediction of composite-lint.
- Performance analyzer in Desktop on the same visuals: note the DirectQuery duration, and the aggregation hit if it shows.
- The date relationship from Sales to Date is on `Order Date` (date to date). If the Budget table joins by `Year Month` text,
  say that it is a many to many relationship only if Desktop makes it one.

## Masking

- Mask the SQL login name, the password dialog and any e-mail address except `alex.demo`.
- Mask the Fabric tenant name, the capacity name and any workspace or dataset id in the address bar.
- The SQL Server address 10.50.0.30 is a lab address and may stay; no real server name.

## Tear-down

1. On CON-SQL01: `DROP DATABASE ContosoBikesDW;` (SSMS or `sqlcmd`). Remove the SQL login.
2. In Desktop: close the PBIP without publishing it. Delete the Part B report and its local model if it was published to
   `Contoso Sales (Lab)`.
3. Nothing to delete in Azure for this episode.
