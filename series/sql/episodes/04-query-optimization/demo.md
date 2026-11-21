# Demo shot list — SQL #4 Query Optimization

## Lab environment

Everything runs on the shared lab VM **CON-SQL01** (SQL Server 2022 Developer), in the `ContosoBikesPerf` database
from episode 3. No tenant, no Azure, no licence, cost 0. Best recorded right after episode 3.

| Machine | What | Notes |
|---|---|---|
| **CON-SQL01** (existing, `series/LAB.md`) | Windows Server 2025 Datacenter Eval, Server Core, SQL Server 2022 Developer, default instance, TCP 1433, mixed auth, 10.20.0.30, 2 vCPU / 2–6 GB | Database `ContosoBikesPerf` (compatibility level 160, Query Store on, capture mode ALL) from episode 3's `00-create-database.sql`. At least 4 GB for the VM while recording |
| **Recording laptop** (host, 10.20.0.1) | SSMS (any current version, Query Store reports), Python 3.10+, Windows Terminal (dark theme) | `py -m pip install -r requirements.txt` in this folder |

Login: `lab_demo` from episode 3's demo.md (db_owner on `ContosoBikesPerf`, `VIEW SERVER PERFORMANCE STATE`).
db_owner covers what this episode needs: `ALTER DATABASE SCOPED CONFIGURATION`, `sp_recompile`,
`sp_query_store_force_plan`, and reading the Query Store views.

## What was verified where

| Step | Verified in the build container (Linux, no Docker) | Needs CON-SQL01 (the recording) |
|---|---|---|
| Data, both rewrites return identical results, the procedure's query (60,000 and 7 rows) | yes: DuckDB (T-SQL transpiled by sqlglot), compared with an independent Python computation | **result checks** in all 12 runs |
| `02-indexes.sql`, queries, Query Store queries parse as T-SQL | yes: sqlglot `tsql`, 8 files | – |
| `03-procedures.sql`, `psp-off.sql`, `psp-on.sql`, `00-create-database.sql` | procedure `SELECT` extracted and executed; the rest is SQL Server only | **run them** |
| Plans: scan vs seek, conversion warning, compiled vs runtime values, Query Store forcing | checks tested on showplan XML built from the official schema; orchestration tested against a fake plan cache | **every check must say OK** |
| mssql-python connection | driver loads, connection attempted (no server) | **connect** |

If SQL Server disagrees with a check (for example the conversion warning has another `ConvertIssue`, or the
optimizer picks a different plan for the Megastore), **don't change the check to make it pass**: save the plans
(`--save-plans`), look at them in SSMS, record what happened in README "gotchas", and adjust the narration.

## Setup (once, before recording)

1. Episode 3's setup done (database, `lab_demo` login). If not: run episode 3's `00-create-database.sql` as the lab
   Administrator and create the login as described there.
2. Terminal on the laptop, in this folder (password typed off-screen):
   ```powershell
   py -m pip install -r requirements.txt
   $env:SQL_CONNECTION_STRING = "Server=10.20.0.30,1433;Database=ContosoBikesPerf;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
   py src/tune_lab.py --engine sqlserver --setup --save-plans plans
   ```
   `--setup` reloads the data and runs `02-indexes.sql` and `03-procedures.sql`. Expected: four tables, every
   check `OK`, a `warning (int literal): PlanAffectingConvert ...` line, the Query Store tables before and after
   forcing, `ForceFailureCount` 0, and `12/12 runs behaved as expected on sqlserver`. Do a dry run first; the run
   is repeatable (it unforces a leftover forced plan before the sniffing scenario).
3. SSMS: connect to CON-SQL01 as `lab_demo`, database `ContosoBikesPerf`, open `q01a`, `q01b`, `q02a`, `q02b`;
   **Include Actual Execution Plan** on (Ctrl+M).

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `sargable-screen` | `screens/q01-plans.jpg` | Paste q01a and q01b into one query window and run both: Results show **4856 / 1238862.24** twice; Execution plan tab: query 1 **Index Scan (IX_Orders_OrderDate)**, query 2 **Index Seek (IX_Orders_OrderDate)**, relative cost per query visible |
| `conversion-screen` | `screens/q02-convert-warning.jpg` | q02a actual plan: yellow warning on the **SELECT** operator, tooltip open showing the type conversion warning with `CONVERT_IMPLICIT(int, ...AccountNumber...)` (capture the wording SSMS uses; the narration says "a type conversion that affects the plan"); a scan, no seek. Optional: q02b below with **Index Seek (UX_Customers_AccountNumber)** and no warning |
| `sniffing-screen` | `screens/runner-sniffing.jpg` | Terminal, the sniffing table: 6 runs, columns plan / compiled/runtime / pages read / rows / check, all **OK**. Rows 1–2 Clustered Index Scan with `1/1` and `1/4242`; rows 3–4 Index Seek + Key Lookup with `4242/4242` and `4242/1` (row 4: 60000 rows, the biggest pages read); rows 5–6 the RECOMPILE procedure |
| `forced-screen` | `screens/query-store-forced.jpg` | Right after the run (the scan plan is still forced): SSMS Object Explorer > ContosoBikesPerf > **Query Store** > **Queries With Forced Plans**: the GetCustomerOrders query, its plans, the scan plan forced. Second take or inset: the terminal's query-store section (both forced runs Clustered Index Scan, OK; `qs-forced-plans.sql` with ForceFailureCount **0**) |

The narration uses relative claims the checks enforce (fewer / more pages, which operator, which compiled value).
To say real numbers out loud, take them from the recorded run and update `script.yaml`.

Optional extra take (not in the script), in SSMS with the actual plan on: run `src/sql/psp-on.sql`, then
`EXEC sp_recompile N'Sales.GetCustomerOrders';`, `EXEC Sales.GetCustomerOrders @CustomerId = 4242;` and
`EXEC Sales.GetCustomerOrders @CustomerId = 1;`. If PSP optimization kicks in, the Megastore gets its own plan and
the plan XML shows a `QueryVariantID`. (Don't use the runner for this: its sniffing scenario turns PSP off first.)

## Masking

- Never show the password or `$env:SQL_CONNECTION_STRING`.
- Blur `10.20.0.30` and the login name in SSMS (title bar, status bar, Object Explorer), or connect through a
  hosts-file alias so it reads `CON-SQL01`.
- All data is generated and fictional.

## Tear-down

Run in SSMS (database `ContosoBikesPerf`), in this order:
1. Unforce the plan: the runner prints the exact `EXEC sp_query_store_unforce_plan @query_id = ..., @plan_id = ...;`
   at the end of the query-store section.
2. `src/sql/psp-on.sql` (puts PSP optimization back to the default).
3. Keep the database for later episodes, or `DROP DATABASE ContosoBikesPerf;` from `master` and `DROP LOGIN lab_demo;`.
4. `Remove-Item Env:SQL_CONNECTION_STRING`.
