# Demo shot list — SQL #1 T-SQL Advanced Queries

## Lab environment

| Item | What this episode needs |
|---|---|
| VM | **CON-SQL01** (shared lab VM): Windows Server 2025 Datacenter Eval, Server Core, SQL Server 2022 **Developer**, default instance, TCP **10.20.0.30,1433**, mixed auth. Nothing else; CON-DC01 must be running (domain/DNS for the VM) |
| Database | `ContosoLab`, created by `src/sql/00-create-database.sql` (compatibility level 160), dropped in tear-down |
| SQL login | `sa` (mixed auth, set by the lab build). The recorder types the lab Administrator password off camera; it is never written in a file or on screen |
| Tenant / Azure | none. No cloud resource, no licence, cost 0 |
| Recording machine | The Windows lab laptop (Hyper-V host, reaches 10.20.0.0/24): VS Code with the **MSSQL** extension (or SSMS) for the grids, PowerShell 7 terminal for pytest and the runner, Python 3.10+ for Windows |

No Docker container: the screens show the shared SQL Server VM. DuckDB stays the engine of the automated tests only.

## What was verified where

| Step | Verified in the build container (Linux, no SQL Server) | Needs SQL Server 2022 on CON-SQL01 (the recording) |
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
- Lab started (`lab/hyperv/Start-MGLab.ps1`), CON-DC01 and CON-SQL01 running. From the laptop:
  `Test-NetConnection 10.20.0.30 -Port 1433` → `TcpTestSucceeded : True`.
- VS Code with the **MSSQL** extension (or SSMS) on the laptop.
- Python 3.10+ for Windows and, in the episode folder, `python -m pip install -r requirements.txt` (on Windows the
  mssql-python wheel needs no extra system packages).
- Terminal: dark theme, font 18 pt+, window 1600x900, short prompt (`function prompt { 'PS> ' }`). VS Code: dark
  theme, zoom so 15 grid rows fit.
- Cost: 0.

## Setup
1. In VS Code, add a connection: server `10.20.0.30,1433`, SQL login `sa`, password typed off camera (don't save it),
   trust server certificate (lab only: the instance uses its self-signed certificate). Profile name: `MG Lab SQL`.
2. Open `src/sql/00-create-database.sql`, run it against `master`. Check: `SELECT name, compatibility_level FROM
   sys.databases WHERE name = 'ContosoLab';` returns 160.
3. In the terminal (password typed off camera, never echoed):
   ```powershell
   $pw = Read-Host -AsSecureString 'sa password'
   $env:SQL_CONNECTION_STRING = "Server=10.20.0.30,1433;Database=ContosoLab;UID=sa;PWD=$([Net.NetworkCredential]::new('', $pw).Password);Encrypt=yes;TrustServerCertificate=yes"
   python src/tsql_runner.py --engine sqlserver --setup
   ```
   Expected: ten `OK` lines and `10/10 queries match expected/ on sqlserver`. (This also loads the data, so the
   VS Code screens below work.)
4. Open each query file in VS Code with the connection set to `ContosoLab` and run it (Execute Query) for the screens.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `window-screen` | `screens/q01-results.jpg` | `q01-monthly-running-total.sql` and its grid, 15 rows. North 2025-06-01 RunningRevenue **10330.00**; Centre rows Jan, Feb, Mar, **May**, Jun (no April), Centre May ChangeVsPrev **2564.75** |
| `outer-apply` | `screens/q03-outer-apply.jpg` | `q03-latest-order-outer-apply.sql` grid, 6 rows; **Eva Newcustomer / South / NULL / NULL / NULL** visible. Optional second take: change `OUTER` to `CROSS`, 5 rows |
| `islands-screen` | `screens/q04-streaks.jpg` | `q04-login-streaks.sql` grid, 6 rows: alex.demo 03-01..03-03 (3), 03-05..03-06 (2), 03-09 (1); rita.sample 03-02..03-05 (**4**), 03-08 (1), 03-10..03-11 (2) |
| `gotcha-screen` | `screens/q08-gotcha.jpg` | `q08-gotcha-default-frame.sql` grid, 8 rows. OrderId 2 and 3: DefaultFrame **4030.50** on both, RowsFrame 1730.50 then 4030.50. OrderId 6 and 7: DefaultFrame **7320.40** on both |
| `runner` | `screens/runner-sqlserver.jpg` | Terminal: `python -m pytest tests -q` → `31 passed`, then `python src/tsql_runner.py --engine sqlserver --setup` → ten OK lines, `10/10 queries match expected/ on sqlserver` |

Expected values for every query are in `expected/*.csv` (same rows the grid must show).

## Masking
- Never show the `sa` password, the `Read-Host` input or `$env:SQL_CONNECTION_STRING`.
- The VS Code connection panel shows `10.20.0.30,1433` (lab-internal address, fine to show); hide the account/profile
  picture in the activity bar.
- Check terminal and VS Code title bars for the laptop's machine name or Windows user name (record from a neutral
  folder such as `C:\MGLab\repo`). `pipeline/mask.js` isn't needed (no browser).

## Tear-down
```sql
-- from master, in VS Code / SSMS connected to 10.20.0.30,1433
ALTER DATABASE ContosoLab SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
DROP DATABASE ContosoLab;
```
```powershell
Remove-Item Env:SQL_CONNECTION_STRING; Remove-Variable pw
```
Remove the `MG Lab SQL` connection profile from VS Code if it saved the password. CON-SQL01 stays running for the
other SQL episodes.
