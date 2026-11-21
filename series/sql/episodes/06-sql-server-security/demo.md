# Demo shot list — SQL #6 SQL Server Security

## Lab environment

Everything runs on the shared lab VM **CON-SQL01** (SQL Server 2022 Developer), in episode 5's database
`ContosoBikesApp`. No tenant, no Azure, no licence, no AD changes, cost 0. Record right after episode 5.

| Machine | What | Notes |
|---|---|---|
| **CON-SQL01** (existing, `series/LAB.md`) | Windows Server 2025 Datacenter Eval, Server Core, SQL Server 2022 Developer, default instance, TCP 1433, mixed auth, 10.20.0.30, 2 vCPU / 2–6 GB | Database `ContosoBikesApp` from episode 5 (`00-create-database.sql`). 2 GB RAM is enough |
| **Recording laptop** (host, 10.20.0.1) | SSMS (any current version), Python 3.10+, Windows Terminal (dark theme) | `py -m pip install -r requirements.txt` in this folder |

Login: `lab_demo` with `db_owner` in `ContosoBikesApp` (episode 5's demo.md, setup step 2). `db_owner` covers
everything this episode does: create users, roles, certificate, security policy and mask, grant, and impersonate
database users (`EXECUTE AS USER`). The three test users (`sales_north`, `sales_south`, `analyst_demo`) are
database users **without logins**: nothing is created at server level, no passwords.

## What was verified where

| Step | Verified in the build container (Linux, no Docker) | Needs CON-SQL01 (the recording) |
|---|---|---|
| Every `.sql` file | parsed with Microsoft's ScriptDom (`TSql160Parser`): 0 errors; structure checks (concatenation vs `sp_executesql`, schema-bound predicates, grants to roles, no literal passwords, `EXECUTE AS`/`REVERT` pairs) | **run them** |
| Injection (`s02`, `s04` row counts), masking inference (`s08` counts) | yes: the procedures' SQL text evaluated and executed on DuckDB with the seed data | the same counts from SQL Server |
| Permissions, ownership chaining, signing, RLS, masking (`s01`, `s03`, `s05`–`s07`) | expected rows checked against an independent model of the data and of Learn's documented behaviour; runner tested with a fake connection | **first real run**: every step must say OK |
| mssql-python connection | driver loads, connection attempted (no server) | **connect** |

If SQL Server disagrees with an expected row, **don't edit `expected/` to make it pass**: find out why (run the step
in SSMS, read the Messages tab), write it in README "gotchas", and adjust the narration in `script.yaml`.

## Setup (once, before recording)

1. Episode 5's setup done (database, `lab_demo` in `db_owner`). Its runner doesn't need to have run: this
   episode's `--setup` reloads episode 5's tables, functions and procedures itself.
2. Terminal on the laptop, in this folder (password typed off-screen):
   ```powershell
   py -m pip install -r requirements.txt
   $env:SQL_CONNECTION_STRING = "Server=10.20.0.30,1433;Database=ContosoBikesApp;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
   py src/security_lab.py --engine sqlserver --setup
   ```
   Expected: the setup line, `ran 14-sign-search-procedure.sql` before s04, `ran 15-row-level-security.sql` before
   s05, eight steps ending `=> OK`, and `8/8 steps behaved as expected on sqlserver`. Dry-run it; it's repeatable
   (`--setup` starts with `10-reset-security.sql`).
3. SSMS: connect to CON-SQL01 as `lab_demo`, database `ContosoBikesApp`; open the `s0*.sql` files.

## Screens to capture (match the `screen` scenes in script.yaml)

The steps build on each other (signing before s04, RLS before s05), so capture in this order:

1. Reset to the state before signing and RLS: `py src/security_lab.py --engine sqlserver --setup --step s01-least-privilege`.
2. SSMS: run `s01`, then `s02` (screens 1 and 2).
3. Apply signing and RLS through the runner: `py src/security_lab.py --engine sqlserver --step s03-dynamic-sql-breaks-chain --step s04-signed-search --step s05-row-level-security --step s06-rls-place-order` (all OK).
4. SSMS: run `s05`, then `s07` and `s08` (screens 3 and 4). These three are read-only and can be re-run.

| Scene id | File | What must be on screen |
|---|---|---|
| `chain-screen` | `screens/s01-least-privilege.jpg` | `s01-least-privilege.sql` with the `EXECUTE AS USER = N'sales_north'` line visible; grid: `SELECT FROM Sales.Customers / denied / error 229`, `EXEC Sales.usp_ListCustomers / allowed / 6 rows`, `EXEC Sales.usp_SearchCustomers_Unsafe / denied / error 229` |
| `injection-screen` | `screens/s02-injection.jpg` | `s02-injection-unsafe.sql` grid: `Alex / 1`, `' OR 1 = 1 -- / 6`. Second shot: select only `EXEC Sales.usp_SearchCustomers_Unsafe @NamePrefix = N''' OR 1 = 1 --';` (without the `INSERT INTO @found`) and run it: all six customers in the grid |
| `rls-screen` | `screens/s05-row-level-security.jpg` | `s05-row-level-security.sql` grid: `sales_north / usp_ListCustomers / 2 / North`, `sales_south / ... / 2 / South`, `db_owner member / ... / 6 / Centre, North, South`, `sales_north / usp_SearchCustomers 'Bruno' / 0 / NULL`. Optional inset: `s06` grid row 2 `error 50001: Unknown customer.` |
| `masking-screen` | `screens/s07-s08-masking.jpg` | Two windows side by side or two shots. `s07`: `Alex Demo / aXXX@XXXX.com / alex.demo@contoso.com`, `Rita Sample / rXXX@XXXX.com / ...`, `Bruno Test / bXXX@XXXX.com / ...`. `s08`: `c% / 1`, `carla.e% / 1`, `carla.x% / 0` |

Optional extra take (not in the script): `s03` in SSMS between steps 2 and 3 above, showing `denied / 229` for the
parameterized search before signing (then let the runner sign it in step 3).

## Masking

- Never show the password or `$env:SQL_CONNECTION_STRING`. The certificate password never exists outside the
  server session (generated with `NEWID()` and discarded), so there's nothing else to hide.
- Blur `10.20.0.30` and the login name in SSMS (title bar, status bar, Object Explorer), or connect through a
  hosts-file alias so it reads `CON-SQL01`.
- All names and emails (`@contoso.com`) are fictional. The "OwnerSees" column shows them in clear on purpose.

## Tear-down

1. `py src/security_lab.py --engine sqlserver --reset-only` (runs `10-reset-security.sql`: policy, predicate
   functions, region map, the three app procedures, certificate and its user, the three test users, both roles,
   the mask). Check in SSMS: `SELECT name FROM sys.database_principals WHERE name IN (N'sales_north', N'sales_south', N'analyst_demo', N'search_signer', N'app_sales', N'reporting');` returns nothing.
2. If no later episode needs it: from `master`, `DROP DATABASE ContosoBikesApp;` and, when the SQL series
   recordings are done, `DROP LOGIN lab_demo;`.
3. `Remove-Item Env:SQL_CONNECTION_STRING` in the terminal.
