# Demo shot list — SQL #1 T-SQL Advanced Queries

No tenant, no cloud resource, no licence: the demo runs on **SQL Server 2022 Developer edition in a container**
(free, for development and test only) on the homelab or a workstation. Nothing is created in Azure.

## What was verified where

| Step | Verified in the build container (Linux, no Docker) | Needs SQL Server 2022 (the recording) |
|---|---|---|
| Every `.sql` file parses as T-SQL | yes: sqlglot `tsql` dialect, all 12 files | – |
| Query results | yes: transpiled to DuckDB and executed; 31 pytest tests compare with independent Python computations | **first real run**: `--engine sqlserver` must print `10/10 queries match` |
| `00-create-database.sql` (CREATE DATABASE, compatibility level 160) | parse only | **run it** |
| `WINDOW` clause, `DATETRUNC`, `PIVOT`, `APPLY`, `OPTION (MAXRECURSION)` | logic only (DuckDB equivalents) | **run them** (they are SQL Server syntax) |
| mssql-python connection | driver installed, connection attempted (fails: no server) | **connect** |

If SQL Server returns something different from `expected/`, the runner prints the first differing rows. **Do not
regenerate `expected/` from SQL Server** without understanding why: note the difference in README "gotchas" and fix
the query or the test.

## Prerequisites
- Docker Desktop or Docker Engine (homelab VM or workstation) with enough free memory for SQL Server on Linux (see the system requirements on Learn).
- VS Code with the **MSSQL** extension (or SSMS on Windows) for the result-grid screens.
- Python 3.10+ and `pip install -r requirements.txt` (mssql-python needs `libltdl7 libkrb5-3 libgssapi-krb5-2` on
  Debian/Ubuntu, per the Learn quickstart).
- Terminal: dark theme, font 18 pt+, window 1600x900. VS Code: dark theme, zoom so 15 grid rows fit.
- Cost: 0.

## Setup
1. Start SQL Server 2022 Developer (pick your own strong password; never on screen):
   ```bash
   docker run -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=<strong password>" -p 1433:1433 --name sql1 -d \
       mcr.microsoft.com/mssql/server:2022-latest
   ```
2. In VS Code, add a connection: server `localhost,1433`, SQL login `sa`, trust server certificate (lab only).
   Profile name: `MG Lab SQL`.
3. Open `src/sql/00-create-database.sql`, run it against `master`. Check: `SELECT name, compatibility_level FROM
   sys.databases WHERE name = 'ContosoLab';` returns 160.
4. In the terminal (password in an environment variable, typed off-screen):
   ```bash
   export SQL_CONNECTION_STRING="Server=localhost,1433;Database=ContosoLab;UID=sa;PWD=<strong password>;Encrypt=yes;TrustServerCertificate=yes"
   python3 src/tsql_runner.py --engine sqlserver --setup
   ```
   Expected: ten `OK` lines and `10/10 queries match expected/ on sqlserver`. (This also loads the data, so the
   VS Code screens below work.)
5. Open each query file in VS Code with the connection set to `ContosoLab` and run it (Execute Query) for the screens.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `window-screen` | `screens/q01-results.jpg` | `q01-monthly-running-total.sql` and its grid, 15 rows. North 2025-06-01 RunningRevenue **10330.00**; Centre rows Jan, Feb, Mar, **May**, Jun (no April), Centre May ChangeVsPrev **2564.75** |
| `outer-apply` | `screens/q03-outer-apply.jpg` | `q03-latest-order-outer-apply.sql` grid, 6 rows; **Eva Newcustomer / South / NULL / NULL / NULL** visible. Optional second take: change `OUTER` to `CROSS`, 5 rows |
| `islands-screen` | `screens/q04-streaks.jpg` | `q04-login-streaks.sql` grid, 6 rows: alex.demo 03-01..03-03 (3), 03-05..03-06 (2), 03-09 (1); rita.sample 03-02..03-05 (**4**), 03-08 (1), 03-10..03-11 (2) |
| `gotcha-screen` | `screens/q08-gotcha.jpg` | `q08-gotcha-default-frame.sql` grid, 8 rows. OrderId 2 and 3: DefaultFrame **4030.50** on both, RowsFrame 1730.50 then 4030.50. OrderId 6 and 7: DefaultFrame **7320.40** on both |
| `runner` | `screens/runner-sqlserver.jpg` | Terminal: `python3 -m pytest tests -q` → `31 passed`, then `python3 src/tsql_runner.py --engine sqlserver --setup` → ten OK lines, `10/10 queries match expected/ on sqlserver` |

Expected values for every query are in `expected/*.csv` (same rows the grid must show).

## Masking
- Never show the `sa` password, the `docker run` line with the password, or `echo $SQL_CONNECTION_STRING`.
- The VS Code connection panel shows `localhost,1433` only; hide the account/profile picture in the activity bar.
- No real host names or IPs from the homelab on screen (use `localhost`).
- `pipeline/mask.js` isn't needed (no browser), but check the window title bar for machine names.

## Tear-down
```bash
docker stop sql1 && docker rm sql1        # removes the container and the ContosoLab database
unset SQL_CONNECTION_STRING
```
Remove the `MG Lab SQL` connection profile from VS Code if it saved the password.
