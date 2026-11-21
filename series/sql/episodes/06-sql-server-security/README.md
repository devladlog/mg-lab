# DEVLADLOG SQL #6 — SQL Server Security

Episode 5 built an order system (`ContosoBikesApp`). This episode locks it down and **proves every rule as the
user it applies to**: three database users without logins, impersonated with `EXECUTE AS USER ... REVERT`, try
things, and every attempt (allowed or denied, with the error number) becomes a row that is compared with
`expected/`.

| Step | What it shows | Expected |
|---|---|---|
| `s01` least privilege | `app_sales` has `EXECUTE` on three procedures and nothing on tables. Ownership chaining lets the procedures read and write the tables | direct `SELECT`: **error 229**; `usp_ListCustomers`: 6 rows; a procedure never granted: **229** |
| `s02` SQL injection | `usp_SearchCustomers_Unsafe` concatenates the input into the SQL text and `EXEC (@sql)`s it | `Alex`: 1 row; `' OR 1 = 1 --`: **all 6** |
| `s03` the gotcha | The fix, `usp_SearchCustomers` (fixed text, `sp_executesql` with a typed parameter, sort column whitelisted and `QUOTENAME`d), called by the app user: dynamic SQL breaks the ownership chain | **error 229** for both calls |
| `s04` module signing | The procedure signed with a certificate; a user created from the certificate has `SELECT` on `Sales.Customers`. The certificate password is random and never stored; the private key is removed after signing | `Alex`: 1 row; the payload: **0 rows** |
| `s05` row-level security | Schema-bound inline predicate + security policy on `Customers` and `Orders`; the region map is a table; `db_owner` members see everything | sales_north 2 (North), sales_south 2 (South), owner 6; the signed search still filtered |
| `s06` RLS in a procedure that writes | sales_north places an order for a North customer; a South customer is invisible, so episode 5's procedure throws 50001; a direct `INSERT` is denied | allowed / `error 50001: Unknown customer.` / **229** |
| `s07` dynamic data masking | `email()` mask; analyst_demo (`SELECT` on schema `Sales`, no `UNMASK`) | `aXXX@XXXX.com` next to the owner's `alex.demo@contoso.com` |
| `s08` the masking gotcha | Masking changes what a query returns, not what `WHERE` tests | `c%` 1, `carla.e%` 1, `carla.x%` 0: the address can be guessed |

| Path | What it is |
|---|---|
| [`src/sql/00…03*.sql`](src/sql) | Episode 5's database, tables, functions and procedures, **unchanged copies** (a test compares them byte for byte) |
| [`src/sql/10-reset-security.sql`](src/sql/10-reset-security.sql) | Removes everything this episode creates, in dependency order (first step of `--setup`, and the tear-down) |
| [`src/sql/11-app-procedures.sql`](src/sql/11-app-procedures.sql) | `usp_ListCustomers` (static), `usp_SearchCustomers_Unsafe`, `usp_SearchCustomers` |
| [`src/sql/12-principals-and-grants.sql`](src/sql/12-principals-and-grants.sql) | Roles `app_sales`, `reporting`; users `sales_north`, `sales_south`, `analyst_demo` (`WITHOUT LOGIN`); grants to roles only |
| [`src/sql/13-dynamic-data-masking.sql`](src/sql/13-dynamic-data-masking.sql) | The `email()` mask (drops and re-creates the `UNIQUE` constraint around it) |
| [`src/sql/14-sign-search-procedure.sql`](src/sql/14-sign-search-procedure.sql) | Certificate, `ADD SIGNATURE`, `REMOVE PRIVATE KEY`, certificate user with `SELECT`. Re-runnable |
| [`src/sql/15-row-level-security.sql`](src/sql/15-row-level-security.sql) | Schema `Security`: region map, two predicate functions, `Security.RegionPolicy` |
| [`src/sql/s01…s08*.sql`](src/sql) | The eight steps; each ends with one result set |
| [`src/security_lab.py`](src/security_lab.py) | The runner: setup order, before-files (14 before s04, 15 before s05), result checks, gets the session back to its own user after every step; local run on DuckDB |
| [`src/labdb.py`](src/labdb.py), [`tools/TsqlParse/`](tools/TsqlParse) | Same files as episode 5: engines, and Microsoft's T-SQL parser (ScriptDom) as a JSON CLI |
| [`expected/`](expected) | Expected result of every step |
| [`tests/`](tests) | 74 pytest tests |

## Run it locally (no SQL Server needed)

```bash
pip install -r requirements.txt
python3 src/security_lab.py          # injection and inference counts match expected/ on duckdb
python3 -m pytest tests -q           # 74 passed
```

What runs where (Docker isn't available in the build container, so there is no SQL Server here):

- **Executed locally (DuckDB):** the injection mechanics. The runner takes the expression that builds `@sql` in
  each search procedure (a test checks it is exactly the text Microsoft's parser finds), evaluates it the way
  T-SQL does (literals, `+`, `QUOTENAME`), and runs the resulting query on the seed data: the unsafe text returns
  1 row for `Alex` and 6 for the payload; the safe text, with the payload bound as a parameter, returns 1 and 0.
  It also runs the analyst's `LIKE` guesses from `s08` on the real values: 1, 1, 0.
- **Parsed by Microsoft's parser (ScriptDom, SQL Server 2022 grammar):** every file, 0 errors; plus the claims:
  the unsafe procedure concatenates `@NamePrefix` and runs `EXEC (@sql)`, the safe one keeps it out of the text and
  calls `sp_executesql`; predicates are schema-bound inline functions using `USER_NAME()` and `IS_MEMBER`; all 6
  `GRANT`s go to `app_sales`, `reporting` or the certificate user, never to a table for the app; no literal
  password anywhere; every `EXECUTE AS` in a step has its `REVERT`.
- **Checked against an independent model:** every `expected/` file (row counts from the seed data and the region
  map, the `email()` format Learn documents, error 229 for permission denials).
- **Needs SQL Server:** permissions, ownership chaining, signing, RLS and masking themselves. That is the
  recording on CON-SQL01 ([demo.md](demo.md)). The runner's SQL Server path is tested against a fake connection;
  the mssql-python path was exercised up to the network (`TCP Provider: Error code 0x2749`, no server).

## Run it on SQL Server 2022 (CON-SQL01)

```powershell
# episode 5's setup first (database ContosoBikesApp, lab_demo as db_owner); then from this folder:
$env:SQL_CONNECTION_STRING = "Server=10.50.0.30,1433;Database=ContosoBikesApp;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
py src/security_lab.py --engine sqlserver --setup
# expect: every step "=> OK" and "8/8 steps behaved as expected on sqlserver"
py src/security_lab.py --engine sqlserver --reset-only     # tear-down: removes this episode's objects
```

## What we learned / gotchas

- **Dynamic SQL breaks the ownership chain.** Static SQL in a procedure only needs `EXECUTE` on the procedure (same
  owner, so the table permission isn't checked). `EXEC (@sql)` and `sp_executesql` run their text as a separate
  batch, and SQL Server checks the *caller's* permissions on what it touches: `s03` gets error 229 from the
  injection-proof procedure. Learn lists two fixes: `EXECUTE AS` in the module, or signing it with a certificate.
- **Signing vs `EXECUTE AS`.** With a signed procedure, the certificate user's permissions are added to the caller's
  and the execution context stays the caller's; `EXECUTE AS` replaces the caller, which Learn warns can break
  applications that rely on row-level security or auditing. `s05` shows the signed search still filtered by RLS.
  Learn also notes the signature is dropped whenever the module changes (re-sign after every `ALTER`), and that
  `REMOVE PRIVATE KEY` is fine when the certificate only verifies signatures (back up the key first if you'll
  ever need to sign again; this lab just re-runs `14-sign-search-procedure.sql`).
- **No secrets in the repo.** `CREATE CERTIFICATE ... ENCRYPTION BY PASSWORD` and `ADD SIGNATURE ... WITH PASSWORD`
  take literals, so the script builds both statements in dynamic SQL with a password made from `NEWID()` that is
  never stored or printed. A test fails if any file contains a literal password.
- **Table-valued parameters need two permissions:** `EXECUTE` and `REFERENCES` on the table type (Learn, "Use
  table-valued parameters"). Granting `EXECUTE` on the procedure alone isn't enough.
- **Security policies apply to `dbo` and `db_owner` too.** If admins must see all rows, the predicate has to say so
  (here `IS_MEMBER(N'db_owner') = 1`). With `SCHEMABINDING = ON` (the default) users need no permission on the
  predicate function or the region table. A filter predicate doesn't stop an `INSERT` (Learn), which is why `s06`'s
  order for a North customer works through the procedure while the South customer is invisible to its check.
- **Masking is not access control.** Learn: users with ad hoc query rights can infer masked values with `WHERE`
  predicates (`s08`), so use masking with least privilege and auditing. Owners (`CONTROL` on the database) always
  see real values; from SQL Server 2022 `UNMASK` can be granted per database, schema, table or column. Copies made
  by a user without `UNMASK` (`INSERT ... SELECT`) contain masked values, which is how `s07` shows both views.
- **Adding a mask is a schema change.** Learn: it fails on a column other objects depend on, such as an index; the
  fix is drop the dependency, add the mask, re-create it. `Email` has a `UNIQUE` constraint, so
  `13-dynamic-data-masking.sql` does exactly that (and runs before the schema-bound security policy exists).
- **A failed step must not leave the session impersonating.** If a batch dies between `EXECUTE AS` and `REVERT`, the
  next one would still run as `sales_north`. The runner checks `USER_NAME()` after every step and `REVERT`s until
  it's back to its own user.
- **Local harness:** sqlglot passes T-SQL's string `+` through unchanged, which DuckDB rejects, so the local run
  rewrites the one `@prefix + N'%'` in the safe query to DuckDB's `||` with a bound `$prefix` parameter.

## References

- [Tutorial: Ownership chains and context switching (error 229, EXECUTE AS, REVERT)](https://learn.microsoft.com/sql/relational-databases/tutorial-ownership-chains-and-context-switching)
- [Writing secure dynamic SQL (dynamic SQL breaks ownership chains; EXECUTE AS vs certificate signing)](https://learn.microsoft.com/sql/connect/ado-net/sql/writing-secure-dynamic-sql)
- [Tutorial: Signing stored procedures with a certificate](https://learn.microsoft.com/sql/relational-databases/tutorial-signing-stored-procedures-with-a-certificate), [ADD SIGNATURE](https://learn.microsoft.com/sql/t-sql/statements/add-signature-transact-sql), [ALTER CERTIFICATE (REMOVE PRIVATE KEY)](https://learn.microsoft.com/sql/t-sql/statements/alter-certificate-transact-sql)
- [EXECUTE (permissions, context switching)](https://learn.microsoft.com/sql/t-sql/language-elements/execute-transact-sql#permissions)
- [Permissions (Database Engine): the permission check algorithm](https://learn.microsoft.com/sql/relational-databases/security/permissions-database-engine)
- [SQL injection](https://learn.microsoft.com/sql/relational-databases/security/sql-injection), [SQL Server security best practices](https://learn.microsoft.com/sql/relational-databases/security/sql-server-security-best-practices), [QUOTENAME](https://learn.microsoft.com/sql/t-sql/functions/quotename-transact-sql), [sp_executesql](https://learn.microsoft.com/sql/relational-databases/system-stored-procedures/sp-executesql-transact-sql)
- [Row-level security (predicates, permissions, dbo, best practices, side channels)](https://learn.microsoft.com/sql/relational-databases/security/row-level-security), [CREATE SECURITY POLICY](https://learn.microsoft.com/sql/t-sql/statements/create-security-policy-transact-sql)
- [Dynamic data masking (functions, UNMASK, granular permissions in SQL Server 2022, inference, column dependencies)](https://learn.microsoft.com/sql/relational-databases/security/dynamic-data-masking)
- [Use table-valued parameters (EXECUTE and REFERENCES on the type)](https://learn.microsoft.com/sql/relational-databases/tables/use-table-valued-parameters-database-engine)
- [CREATE USER (WITHOUT LOGIN, FROM CERTIFICATE)](https://learn.microsoft.com/sql/t-sql/statements/create-user-transact-sql)
- Blog: [SQL Server Security — Complete Guide](https://www.devladlog.com/articles/sql/2025-08-04-sql-server-security-complete-guide-2025/)
