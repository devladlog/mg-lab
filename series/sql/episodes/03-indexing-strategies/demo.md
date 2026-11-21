# Demo shot list — SQL #3 Indexing Strategies

## Lab environment

Everything runs on the shared lab VM **CON-SQL01** (SQL Server 2022 Developer). No tenant, no Azure, no licence,
cost 0. Episode 4 reuses the same database, so record both episodes in one session if possible.

| Machine | What | Notes |
|---|---|---|
| **CON-SQL01** (existing, `series/LAB.md`) | Windows Server 2025 Datacenter Eval, Server Core, SQL Server 2022 Developer, default instance, TCP 1433, mixed auth, 10.20.0.30, 2 vCPU / 2–6 GB | Database `ContosoBikesPerf`: ~100 MB data (200,000 rows of ~400 bytes) plus indexes, SIMPLE recovery. Give the VM at least 4 GB while recording so the table stays in memory |
| **Recording laptop** (host, 10.20.0.1) | SSMS (any current version), Python 3.10+, a terminal (Windows Terminal, dark theme) | Screens are recorded here. `py -m pip install -r requirements.txt` in this folder |

No extra VM. Nothing destructive: the episode only creates and drops its own database and indexes.

## What was verified where

| Step | Verified in the build container (Linux, no Docker) | Needs CON-SQL01 (the recording) |
|---|---|---|
| Data generator, the three queries, `expected/` | yes: transpiled to DuckDB and executed; compared with an independent Python computation | **first real run**: results must match `expected/` in all 9 steps |
| All `.sql` files parse as T-SQL | yes: sqlglot `tsql` dialect, 14 files (`00` is SQL Server only) | – |
| `GENERATE_SERIES`, compatibility level 160, index DDL (`INCLUDE`, filtered, columnstore) | parse only | **run them** |
| Plan reading (`showplan.py`) and the step checks | yes: against showplan XML built with the official schema's elements, validated against `sql2022/showplanxml.xsd` | **the real plans**: every check must say OK |
| mssql-python connection, `SET STATISTICS XML` capture | driver loads, connection attempted (no server); capture tested with a fake connection | **connect and capture** |

If a check fails on SQL Server, **don't edit the check to make it pass**. Save the plan (`--save-plans`), look at
it in SSMS, and record what SQL Server did and why in README "gotchas"; then fix the index or the narration.

## Setup (once, before recording)

1. Start the lab (`lab/hyperv/Start-MGLab.ps1`) and check CON-SQL01 answers on 10.20.0.30:1433.
2. In SSMS, connect to CON-SQL01 as the lab Administrator and run `src/sql/00-create-database.sql` (against
   `master`). Check: `SELECT compatibility_level FROM sys.databases WHERE name = 'ContosoBikesPerf';` returns 160.
3. Create the login the runner uses (password typed off-screen, never saved in the repo):
   ```sql
   CREATE LOGIN lab_demo WITH PASSWORD = '<password>', CHECK_POLICY = ON;
   GRANT VIEW SERVER PERFORMANCE STATE TO lab_demo;   -- index usage and missing index DMVs (SQL Server 2022)
   USE ContosoBikesPerf;
   CREATE USER lab_demo FOR LOGIN lab_demo;
   ALTER ROLE db_owner ADD MEMBER lab_demo;
   ```
4. Terminal on the laptop, in this folder (PowerShell; the password is typed off-screen):
   ```powershell
   py -m pip install -r requirements.txt
   $env:SQL_CONNECTION_STRING = "Server=10.20.0.30,1433;Database=ContosoBikesPerf;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
   py src/index_lab.py --engine sqlserver --setup --save-plans plans
   ```
   Expected: `setup: Sales.Customers and Sales.Orders loaded`, three step tables with every check `OK`, three
   `identical to expected/ in every step` lines, the two DMV tables and `9/9 steps behaved as expected on sqlserver`.
   Do a full dry run first; then run it again for the recording (re-runnable: every step starts from `ix00`).
5. SSMS: open `src/sql/q01-customer-orders.sql`, `src/sql/q03-revenue-by-year-channel.sql` and the `ix*.sql`
   files; database `ContosoBikesPerf`; turn on **Include Actual Execution Plan** (Ctrl+M).

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `scan-screen` | `screens/q01-plans.jpg` | Run `ix00-drop-lab-indexes.sql`, then q01 → plan 1: **Clustered Index Scan (PK_Orders)** + Sort (keep the green *Missing Index* text if SSMS shows one). Run `ix01-customer.sql`, then q01 again → plan 2: **Index Seek (IX_Orders_CustomerId)** + Nested Loops + **Key Lookup (PK_Orders)** + Sort. Show both (two SSMS windows side by side, or plans stacked). Hover the Key Lookup: Number of Executions **7** |
| `runner-screen` | `screens/runner-customer-orders.jpg` | Terminal, the customer-orders table: 4 steps, columns plan / pages read / index pages / check, all **OK**; the missing index line under it; `results: 7 rows, identical to expected/ in every step` |
| `filtered-screen` | `screens/runner-open-orders.jpg` | Terminal, the open-orders table: no index → `Index Seek(IX_Orders_Status_OrderDate)` → `Index Seek(IX_Orders_Open)`; index pages of `IX_Orders_Open` below 10% of the full-table index; all OK; `49 rows` |
| `columnstore-screen` | `screens/q03-columnstore-plan.jpg` | Run `ix06-columnstore.sql`, then q03 with the actual plan: **Columnstore Index Scan (NCCI_Orders_Reporting)** selected, Properties pane: **Actual Execution Mode = Batch**, Storage = ColumnStore. Optional inset: the runner's revenue-report table |
| `cost-screen` | `screens/runner-final-dmvs.jpg` | End of the runner output: `dmv-index-sizes.sql` table (PK_Orders, IX_Orders_CustomerId_OrderDate, IX_Orders_Open with Filtered 1, NCCI_Orders_Reporting), `dmv-index-usage.sql` table, `9/9 steps behaved as expected on sqlserver` |

After recording, compare the narration with what the screens show: the narration only uses relative claims
(fewer / more pages, smaller index) that the checks enforce. If you want to say the real numbers out loud, take
them from the recorded run and update `script.yaml`.

Also keep `plans/*.sqlplan` from the recorded run (don't commit them if they show the server name; they're
gitignored): they are the real plans the tests only approximate.

## Masking

- Never show the password, the `CREATE LOGIN` line with it, or `$env:SQL_CONNECTION_STRING`.
- SSMS shows the server you typed in the Connect dialog: blur `10.20.0.30` and the login name in the status bar
  and Object Explorer, or connect through a hosts-file alias so it reads `CON-SQL01`.
- All customers, orders and account numbers are generated and fictional; nothing else to mask.

## Tear-down

- Keep `ContosoBikesPerf` for episode 4 (its `02-indexes.sql` removes this episode's indexes).
- Otherwise: run `src/sql/ix00-drop-lab-indexes.sql`, or drop everything with `DROP DATABASE ContosoBikesPerf;`
  (from `master`) and `DROP LOGIN lab_demo;`.
- `Remove-Item Env:SQL_CONNECTION_STRING` in the terminal.
