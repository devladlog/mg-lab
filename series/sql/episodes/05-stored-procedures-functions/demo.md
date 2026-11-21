# Demo shot list — SQL #5 Stored Procedures & Functions

## Lab environment

Everything runs on the shared lab VM **CON-SQL01** (SQL Server 2022 Developer), in a new, small database
`ContosoBikesApp` (a few KB of data). No tenant, no Azure, no licence, cost 0. Episode 6 reuses this database:
record both episodes in one session if possible.

| Machine | What | Notes |
|---|---|---|
| **CON-SQL01** (existing, `series/LAB.md`) | Windows Server 2025 Datacenter Eval, Server Core, SQL Server 2022 Developer, default instance, TCP 1433, mixed auth, 10.50.0.30, 2 vCPU / 2–6 GB | Database `ContosoBikesApp`, compatibility level 160 (`00-create-database.sql`). 2 GB RAM is enough for this episode |
| **Recording laptop** (host, 10.50.0.1) | SSMS (any current version), Python 3.10+, Windows Terminal (dark theme) | `py -m pip install -r requirements.txt` in this folder. The .NET SDK is only needed for the tests, not for the demo |

Login: `lab_demo` (SQL login created in episode 3's demo.md; create it as described there if it doesn't exist).
In this database it needs `db_owner`: the runner creates tables, a type, functions and procedures, and asks for
actual plans (`SET STATISTICS XML` needs `SHOWPLAN`, which `db_owner` has).

No extra VM, nothing destructive outside the new database.

## What was verified where

| Step | Verified in the build container (Linux, no Docker) | Needs CON-SQL01 (the recording) |
|---|---|---|
| Schema, seed data, the three function queries (`r02a`, `r02b`, `r03`) | yes: DuckDB (T-SQL transpiled by sqlglot), functions inlined by hand from `02-functions.sql`; compared with `expected/` and an independent Python computation | **result checks** on the real functions |
| Every `.sql` file | parsed with Microsoft's ScriptDom (`TSql160Parser`): 0 errors; structure checked (XACT_ABORT, TRY/CATCH, THROW, READONLY, GETDATE) | **run them** |
| `is_inlineable` (r01), inlined vs not inlined plans (r02a/r02b) | expectations from Learn's inlining rules; the plan check tested on showplan XML samples | **checks must say OK** |
| Procedures d01–d04: rows, error 547 on the out-of-stock batch, naive vs safe | expected rows checked against a Python model of the documented behaviour; runner tested with a fake connection | **first real run** |
| mssql-python connection | driver loads, connection attempted (no server) | **connect** |

If SQL Server disagrees with a check, **don't edit the check to make it pass**: look at what happened (SSMS, the
actual plan), write it in README "gotchas", and adjust the narration in `script.yaml`.

## Setup (once, before recording)

1. Start the lab (`lab/hyperv/Start-MGLab.ps1`); check CON-SQL01 answers on 10.50.0.30:1433.
2. SSMS as the lab Administrator, against `master`: run `src/sql/00-create-database.sql`. Then:
   ```sql
   USE ContosoBikesApp;
   CREATE USER lab_demo FOR LOGIN lab_demo;
   ALTER ROLE db_owner ADD MEMBER lab_demo;
   ```
3. Terminal on the laptop, in this folder (password typed off-screen):
   ```powershell
   py -m pip install -r requirements.txt
   $env:SQL_CONNECTION_STRING = "Server=10.50.0.30,1433;Database=ContosoBikesApp;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
   py src/proc_lab.py --engine sqlserver --setup
   ```
   Expected: `setup: tables, data, functions and procedures (re)created`, eight steps each ending `=> OK`,
   two `error raised: ... CK_Products_StockQty` lines (d03, d04), and `8/8 steps behaved as expected on sqlserver`.
   Dry-run it; it's repeatable (`--setup` recreates everything).
4. SSMS: connect to CON-SQL01 as `lab_demo`, database `ContosoBikesApp`. Open `r01-inlining-catalog.sql`,
   `d01-place-order.sql`, `d02-unknown-customer.sql`, `d03-naive-out-of-stock.sql`.

## Screens to capture (match the `screen` scenes in script.yaml)

Before the SSMS captures, reset the data: `py src/proc_lab.py --engine sqlserver --setup --step r01-inlining-catalog`
(recreates everything, runs only r01). Then run the SSMS files **in this order**: r01, d01, d02, d03.

| Scene id | File | What must be on screen |
|---|---|---|
| `inlining-screen` | `screens/r01-is-inlineable.jpg` | SSMS, `r01-inlining-catalog.sql` run: query text and a 3-row grid: `ufn_CustomerOrderSummary / SQL_INLINE_TABLE_VALUED_FUNCTION / 1`, `ufn_DaysSinceOrder / SQL_SCALAR_FUNCTION / 0`, `ufn_LineTotal / SQL_SCALAR_FUNCTION / 1` |
| `place-order-screen` | `screens/d01-place-order.jpg` | SSMS, `d01-place-order.sql` run: the `DECLARE @lines Sales.OrderLineList`, the two-line `INSERT`, the `EXEC ... OUTPUT`; grid: `yes / 2 / 201.85 / 38 / 119` |
| `gotcha-screen` | `screens/d03-naive-out-of-stock.jpg` | Run `d02` (grid `50001 / Unknown customer. / 0`, not captured), then `d03-naive-out-of-stock.sql`. Capture the **Messages** tab (Msg 547, `CK_Products_StockQty`) and the **Results** tab (`1 / 2 / 2 / 119 / 0`): two shots or a split image |
| `runner-screen` | `screens/runner-summary.jpg` | Terminal (dark, 18 pt): `py src/proc_lab.py --engine sqlserver --setup`, scrolled to d03 and d04 (each: `error raised: ... CK_Products_StockQty`, `check error: CK_Products_StockQty OK`, its one-row table) and the last line `8/8 steps behaved as expected on sqlserver` |

Optional extra take (not in the script): SSMS, Include Actual Execution Plan (Ctrl+M), run `r02b`, right-click the
plan > Show Execution Plan XML, Ctrl+F `UserDefinedFunction`; then the same for `r02a` (not found).

## Masking

- Never show the password or `$env:SQL_CONNECTION_STRING`.
- Blur `10.50.0.30` and the login name in SSMS (title bar, status bar, Object Explorer), or connect through a
  hosts-file alias so it reads `CON-SQL01`.
- All customers, emails (`@contoso.com`) and orders are fictional; nothing else to mask.

## Tear-down

- Keep `ContosoBikesApp` for episode 6 (it starts from this episode's `--setup`).
- Otherwise, from `master`: `DROP DATABASE ContosoBikesApp;` (keep `lab_demo` if episode 6 is still to record).
- `Remove-Item Env:SQL_CONNECTION_STRING` in the terminal.
