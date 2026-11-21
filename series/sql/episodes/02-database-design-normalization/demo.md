# Demo shot list — SQL #2 Database Design & Normalization

No tenant, no cloud resource, no licence: **SQL Server 2022 Developer edition in a container** (free, development
and test only) on the homelab or a workstation, plus VS Code. Nothing is created in Azure. The same container as
episode 1 can be reused (different database: `ContosoTraining`).

## What was verified where

| Step | Verified in the build container (Linux, no Docker) | Needs SQL Server 2022 (the recording) |
|---|---|---|
| 1NF split, dependency checks, decisions, lossless join | yes: `normalize.py`, pytest | – |
| `01-schema.sql`, `02-data.sql`, queries, `04-should-fail.sql` parse as T-SQL | yes: sqlglot `tsql` dialect | – |
| Schema loads, view rebuilds the export, `UPDATE` + `ROLLBACK`, six rejections | yes: transpiled to DuckDB and executed (28 tests) | **first real run**: `--engine sqlserver --setup` must print `3/3` and `6/6` |
| `IDENTITY`, `SET IDENTITY_INSERT`, constraint names in error messages | no (DuckDB has no identity columns; its errors don't name constraints) | **check on screen** |
| mssql-python connection | driver installed, connection attempted (no server) | **connect** |

If SQL Server disagrees with `expected/`, don't regenerate it from SQL Server: record the difference in README
"gotchas" and fix the cause.

## Prerequisites
- Docker (homelab VM or workstation) with enough free memory for SQL Server on Linux.
- VS Code with the **MSSQL** extension (or SSMS on Windows).
- Python 3.10+ and `pip install -r requirements.txt` (mssql-python needs `libltdl7 libkrb5-3 libgssapi-krb5-2` on
  Debian/Ubuntu, per the Learn quickstart).
- Terminal: dark theme, 18 pt+, 1600x900. VS Code: dark theme, results grid wide enough for 10 columns (q01).
- Cost: 0.

## Setup
1. If the episode 1 container isn't running:
   ```bash
   docker run -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=<strong password>" -p 1433:1433 --name sql1 -d \
       mcr.microsoft.com/mssql/server:2022-latest
   ```
2. VS Code connection `MG Lab SQL` (server `localhost,1433`, login `sa`, trust server certificate: lab only).
3. Run `src/sql/00-create-database.sql` against `master`.
4. Terminal (password set off-screen):
   ```bash
   export SQL_CONNECTION_STRING="Server=localhost,1433;Database=ContosoTraining;UID=sa;PWD=<strong password>;Encrypt=yes;TrustServerCertificate=yes"
   python3 src/normalize.py                              # optional: the design report for the terminal scenes
   python3 src/tsql_runner.py --engine sqlserver --setup
   ```
   Expected: `loaded: Company 4, Customer 7, Course 5, Booking 16, BookingLine 23`, three `OK`,
   `3/3 queries match expected/ on sqlserver`, six `REJECTED` lines, `6/6 constraint checks behaved on sqlserver`.
5. Refresh Object Explorer in VS Code; open the query files with the connection set to `ContosoTraining`.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `tables-screen` | `screens/object-explorer.jpg` | Object Explorer: `ContosoTraining` > Tables: `Training.Booking`, `Training.BookingLine`, `Training.Company`, `Training.Course`, `Training.Customer`; `Training.BookingLine` expanded (columns, keys `PK_BookingLine`, `FK_BookingLine_Booking`, `FK_BookingLine_Course`); Views: `Training.vBookingLines` |
| `rebuilt-screen` | `screens/q01-rebuilt.jpg` | `q01-bookings-rebuilt.sql` grid, **23 rows**. Row B1008 shows CompanyCity **Porto**; B1011/PBI200 shows **Power BI Data Modeling** (one "l") |
| `update-screen` | `screens/q03-update-once.jpg` | `q03-update-once.sql` grid, 4 rows: **Contoso Ltd / Matosinhos / 5 / 7**, Adventure Works Faro 2/3, Fabrikam Inc Lisbon 5/7, Northwind Traders Braga 4/6. Afterwards `SELECT City FROM Training.Company WHERE CompanyName = N'Contoso Ltd'` returns Porto (rolled back) |
| `constraints-screen` | `screens/should-fail.jpg` | `04-should-fail.sql`: select and run batch 1, then batch 3. Messages tab shows both errors, naming **UQ_Customer_Email** and **FK_BookingLine_Course**. Note the exact message text in README if it differs from what the narration says |
| `runner-screen` | `screens/runner-sqlserver.jpg` | Terminal: `python3 -m pytest tests -q` → `28 passed`; then the step 4 command with its full output (`3/3`, six REJECTED, `6/6`) |

Expected query results: `expected/*.csv`. Expected 3NF table contents: `data/normalized/*.csv`.

## Masking
- Never show the `sa` password, the `docker run` line with it, or the value of `SQL_CONNECTION_STRING`.
- Server name on screen: `localhost` only; no homelab host names, IPs or machine names in title bars.
- All people, emails (`*.example`) and companies in the data are fictional; nothing else to mask.

## Tear-down
```bash
# keep the container for episode 3, or:
docker stop sql1 && docker rm sql1
unset SQL_CONNECTION_STRING
```
To drop only this episode's data: `DROP DATABASE ContosoTraining;` (from `master`).
