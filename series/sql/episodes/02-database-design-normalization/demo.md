# Demo shot list — SQL #2 Database Design & Normalization

## Lab environment

| Item | What this episode needs |
|---|---|
| VM | **CON-SQL01** (shared lab VM): Windows Server 2025 Datacenter Eval, Server Core, SQL Server 2022 **Developer**, default instance, TCP **10.20.0.30,1433**, mixed auth. CON-DC01 running (domain/DNS) |
| Database | `ContosoTraining`, created by `src/sql/00-create-database.sql`, dropped in tear-down. Episode 1's `ContosoLab` can stay on the same instance |
| SQL login | `sa` (mixed auth, set by the lab build). The recorder types the lab Administrator password off camera; never in a file or on screen |
| Tenant / Azure | none. No cloud resource, no licence, cost 0 |
| Recording machine | The Windows lab laptop (Hyper-V host, reaches 10.20.0.0/24): VS Code with the **MSSQL** extension (or SSMS) for Object Explorer and grids, PowerShell 7 terminal, Python 3.10+ for Windows |

No Docker container: the screens show the shared SQL Server VM. DuckDB stays the engine of the automated tests only.

## What was verified where

| Step | Verified in the build container (Linux, no SQL Server) | Needs SQL Server 2022 on CON-SQL01 (the recording) |
|---|---|---|
| 1NF split, dependency checks, decisions, lossless join | yes: `normalize.py`, pytest | – |
| `01-schema.sql`, `02-data.sql`, queries, `04-should-fail.sql` parse as T-SQL | yes: sqlglot `tsql` dialect | – |
| Schema loads, view rebuilds the export, `UPDATE` + `ROLLBACK`, six rejections | yes: transpiled to DuckDB and executed (28 tests) | **first real run**: `--engine sqlserver --setup` must print `3/3` and `6/6` |
| `IDENTITY`, `SET IDENTITY_INSERT`, constraint names in error messages | no (DuckDB has no identity columns; its errors don't name constraints) | **check on screen** |
| mssql-python connection | driver installed, connection attempted (no server) | **connect** |

If SQL Server disagrees with `expected/`, don't regenerate it from SQL Server: record the difference in README
"gotchas" and fix the cause.

## Prerequisites
- Lab started, CON-DC01 and CON-SQL01 running; `Test-NetConnection 10.20.0.30 -Port 1433` succeeds from the laptop.
- VS Code with the **MSSQL** extension (or SSMS) on the laptop.
- Python 3.10+ for Windows and `python -m pip install -r requirements.txt` in the episode folder.
- Terminal: dark theme, 18 pt+, 1600x900, prompt `PS> `. VS Code: dark theme, results grid wide enough for 10
  columns (q01).
- Cost: 0.

## Setup
1. VS Code connection `MG Lab SQL` (server `10.20.0.30,1433`, login `sa`, password typed off camera and not saved,
   trust server certificate: lab only). Reuse episode 1's profile if it exists.
2. Run `src/sql/00-create-database.sql` against `master`.
3. Terminal (password typed off camera):
   ```powershell
   $pw = Read-Host -AsSecureString 'sa password'
   $env:SQL_CONNECTION_STRING = "Server=10.20.0.30,1433;Database=ContosoTraining;UID=sa;PWD=$([Net.NetworkCredential]::new('', $pw).Password);Encrypt=yes;TrustServerCertificate=yes"
   python src/normalize.py                              # optional: the design report for the terminal scenes
   python src/tsql_runner.py --engine sqlserver --setup
   ```
   Expected: `loaded: Company 4, Customer 7, Course 5, Booking 16, BookingLine 23`, three `OK`,
   `3/3 queries match expected/ on sqlserver`, six `REJECTED` lines, `6/6 constraint checks behaved on sqlserver`.
4. Refresh Object Explorer in VS Code; open the query files with the connection set to `ContosoTraining`.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `tables-screen` | `screens/object-explorer.jpg` | Object Explorer connected to `10.20.0.30,1433`: `ContosoTraining` > Tables: `Training.Booking`, `Training.BookingLine`, `Training.Company`, `Training.Course`, `Training.Customer`; `Training.BookingLine` expanded (columns, keys `PK_BookingLine`, `FK_BookingLine_Booking`, `FK_BookingLine_Course`); Views: `Training.vBookingLines` |
| `rebuilt-screen` | `screens/q01-rebuilt.jpg` | `q01-bookings-rebuilt.sql` grid, **23 rows**. Row B1008 shows CompanyCity **Porto**; B1011/PBI200 shows **Power BI Data Modeling** (one "l") |
| `update-screen` | `screens/q03-update-once.jpg` | `q03-update-once.sql` grid, 4 rows: **Contoso Ltd / Matosinhos / 5 / 7**, Adventure Works Faro 2/3, Fabrikam Inc Lisbon 5/7, Northwind Traders Braga 4/6. Afterwards `SELECT City FROM Training.Company WHERE CompanyName = N'Contoso Ltd'` returns Porto (rolled back) |
| `constraints-screen` | `screens/should-fail.jpg` | `04-should-fail.sql`: select and run batch 1, then batch 3. Messages tab shows both errors, naming **UQ_Customer_Email** and **FK_BookingLine_Course**. Note the exact message text in README if it differs from what the narration says |
| `runner-screen` | `screens/runner-sqlserver.jpg` | Terminal: `python -m pytest tests -q` → `28 passed`; then the step 3 runner command with its full output (`3/3`, six REJECTED, `6/6`) |

Expected query results: `expected/*.csv`. Expected 3NF table contents: `data/normalized/*.csv`.

## Masking
- Never show the `sa` password, the `Read-Host` input or the value of `$env:SQL_CONNECTION_STRING`.
- Server name on screen: `10.20.0.30,1433` (lab-internal, fine). No laptop machine name or Windows user name in title
  bars (record from a neutral folder).
- All people, emails (`*.example`) and companies in the data are fictional; nothing else to mask.

## Tear-down
```sql
-- from master on 10.20.0.30,1433
ALTER DATABASE ContosoTraining SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
DROP DATABASE ContosoTraining;
```
```powershell
Remove-Item Env:SQL_CONNECTION_STRING; Remove-Variable pw
```
CON-SQL01 stays running for the other SQL episodes.
