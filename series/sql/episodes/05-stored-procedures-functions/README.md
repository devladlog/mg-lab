# DEVLADLOG SQL #5 — Stored Procedures & Functions

A small, fictional **Contoso Bikes** order system (`ContosoBikesApp`: 6 customers, 5 products with stock,
8 orders, 13 order lines) and the code that sits on top of it:

| Object | What it shows |
|---|---|
| `Sales.ufn_LineTotal` | A scalar UDF SQL Server **can inline** (one `RETURN`, plain expression): `is_inlineable = 1`, and the actual plan of a query that uses it has no `UserDefinedFunction` node |
| `Sales.ufn_DaysSinceOrder` | The inlining gotcha: it calls `GETDATE()`, a time-dependent built-in, so `is_inlineable = 0`. It works, one call per row |
| `Sales.ufn_CustomerOrderSummary` | An **inline table-valued function** (a view with a parameter), used with `CROSS APPLY` |
| `Sales.OrderLineList` | A user-defined **table type**: the whole order arrives in one call as a table-valued parameter (`READONLY`) |
| `Sales.usp_PlaceOrder` | The safe procedure: `SET XACT_ABORT ON`, `TRY...CATCH`, transaction, `ROLLBACK`, `THROW` (user errors 50001–50003, re-raise with `THROW;`), new order number in an `OUTPUT` parameter, stock guarded by a `CHECK` constraint instead of "check, then update" |
| `Sales.usp_PlaceOrder_Naive` | **The gotcha**: the same statements inside a transaction, without `XACT_ABORT` and `TRY...CATCH`. The out-of-stock `UPDATE` fails, only that statement is rolled back, and `COMMIT` saves an order and its lines that nobody can ship |

`src/proc_lab.py` runs eight steps against SQL Server, the way SSMS runs a script (batch by batch, carrying on
after a failed batch), and checks each one: the rows against `expected/`, the error each batch raised
(`"error: CK_Products_StockQty"`), and for the function queries the **actual plan** (`"plan: inlined"`, `"plan: not inlined"`).

| Path | What it is |
|---|---|
| [`src/sql/00-create-database.sql`](src/sql/00-create-database.sql) | SQL Server only: creates `ContosoBikesApp`, compatibility level 160 (inlining needs 150+) |
| [`src/sql/01-schema-and-data.sql`](src/sql/01-schema-and-data.sql) | Schema `Sales`, 4 tables, constraints, the `Sales.OrderNumbers` sequence (new orders from 2001), seed data. Re-runnable |
| [`src/sql/02-functions.sql`](src/sql/02-functions.sql) | The three functions |
| [`src/sql/03-procedures.sql`](src/sql/03-procedures.sql) | The table type and both procedures. Re-runnable (drops the procedures before the type) |
| [`src/sql/r01…r03*.sql`](src/sql) | `is_inlineable` from `sys.sql_modules`; order totals through the UDF, with and without `USE HINT('DISABLE_TSQL_SCALAR_UDF_INLINING')`; the TVF with `CROSS APPLY` |
| [`src/sql/d01…d04*.sql`](src/sql) | Place a good order; unknown customer (`THROW 50001`, caught); out of stock through the naive procedure; the same through the safe one |
| [`src/proc_lab.py`](src/proc_lab.py) | The runner: steps and checks, local run (DuckDB) and SQL Server run |
| [`src/labdb.py`](src/labdb.py) | Engines: mssql-python (batch by batch, errors recorded, `SET STATISTICS XML` plans) and DuckDB (T-SQL transpiled by sqlglot) |
| [`tools/TsqlParse/`](tools/TsqlParse) | A small .NET console (one file) around **Microsoft's T-SQL parser** (`Microsoft.SqlServer.TransactSql.ScriptDom`, `TSql160Parser`): prints every file's statements, modules, parameters, `SET` options, function calls as JSON |
| [`expected/`](expected) | Expected result of every step |
| [`tests/`](tests) | 57 pytest tests: ScriptDom structure checks, results vs an independent Python model, the runner against a fake connection, `script.yaml` |

## Run it locally (no SQL Server needed)

```bash
pip install -r requirements.txt
python3 src/proc_lab.py              # 3/3 local steps match expected/ on duckdb (the procedure steps are SQL Server only)
python3 -m pytest tests -q           # 57 passed
```

What the local run and the tests really prove, and what they don't (Docker isn't available in the build
container, so there is no SQL Server here):

- **Executed locally:** the schema and seed data (DuckDB, T-SQL transpiled by sqlglot) and the three function
  queries. DuckDB has no T-SQL functions, so the runner does by hand what scalar UDF inlining does: it replaces
  each call with the function's own `RETURN` expression or `SELECT` from `02-functions.sql`. A test checks that the
  bodies it extracts are exactly the ones Microsoft's parser finds. Results are compared with `expected/` and with
  an independent Python computation from the seed data.
- **Parsed by Microsoft's parser:** every `.sql` file (ScriptDom, SQL Server 2022 grammar): 0 syntax errors, and
  the structure the episode claims (the safe procedure has `XACT_ABORT ON`, `TRY...CATCH`, `THROW`, `ROLLBACK`; the
  naive one has the same `INSERT`/`UPDATE` text and none of those; `@Lines` is `READONLY`; `ufn_DaysSinceOrder` calls
  `GETDATE`; user error numbers are in the range `THROW` accepts). The tests build the tool into the temp folder
  (`dotnet build --artifacts-path`), never into the repo.
- **Modelled, not executed:** the expected results of the procedure steps (`d01`–`d04`) are checked against a Python
  model of the documented behaviour (all-or-nothing with `XACT_ABORT ON` + `ROLLBACK`, statement-level rollback
  without). The runner's SQL Server path is tested against a fake connection.
- **Needs SQL Server:** procedures, error behaviour, `is_inlineable`, actual plans. That is the recording on
  CON-SQL01 ([demo.md](demo.md)). The mssql-python path was exercised up to the network
  (`TCP Provider: Error code 0x2749`, no server).

## Run it on SQL Server 2022 (CON-SQL01)

```powershell
# 1. as the lab Administrator, against master: src/sql/00-create-database.sql
# 2. from this folder (password typed off-screen, never stored):
$env:SQL_CONNECTION_STRING = "Server=10.20.0.30,1433;Database=ContosoBikesApp;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
py src/proc_lab.py --engine sqlserver --setup
# expect: every check OK and "8/8 steps behaved as expected on sqlserver"
```

`--setup` recreates the tables, data, functions and procedures, so the run is repeatable. The `d*` steps depend on
each other's data (stock after `d01`), so run them in order after `--setup`.

## What we learned / gotchas

- **A transaction is not all-or-nothing by itself.** With `SET XACT_ABORT OFF` (the default outside triggers), a
  run-time error such as a `CHECK` or foreign key violation can roll back only the statement that raised it; the
  next statement runs, and that can be `COMMIT`. Learn's `SET XACT_ABORT` page shows exactly this with a foreign key.
  `usp_PlaceOrder_Naive` reproduces it: one order, two lines, stock unchanged.
- **The pattern:** `SET XACT_ABORT ON`, writes inside `BEGIN TRY` + `BEGIN TRANSACTION`, and in `BEGIN CATCH`
  `IF @@TRANCOUNT > 0 ROLLBACK;` then `THROW;`. `THROW` honours `XACT_ABORT`, `RAISERROR` doesn't (Learn recommends
  `THROW` for new code); `THROW` without parameters must be inside a `CATCH` block, and the statement before a
  `THROW` must end with a semicolon. User error numbers must be 50000 or higher.
- **Signal failure with errors, not return codes.** Learn's "Return data from a stored procedure" says procedures
  should indicate failure with an error and not rely on the return code. The new order number comes back in an
  `OUTPUT` parameter.
- **Don't check stock and then update it.** Two sessions can both pass the check. The single `UPDATE` with the
  `CHECK (StockQty >= 0)` constraint is the check, inside the transaction.
- **Scalar UDF inlining has a long list of conditions.** Compatibility level 150+, one `RETURN`, no time-dependent
  built-ins like `GETDATE()`, `EXECUTE AS CALLER`, no table variables or TVPs, not used in `ORDER BY` or `GROUP BY` of
  the calling query, and more. `sys.sql_modules.is_inlineable` only says the definition qualifies; SQL Server still
  decides per query. The plan tells you: no `UserDefinedFunction` node means it was inlined. Learn also lists
  behaviour changes (different query hash, `@@ROWCOUNT` and similar change meaning).
- **Inline vs multi-statement TVFs.** A multi-statement TVF has a fixed cardinality guess (100 rows since SQL Server
  2014, 1 before). Interleaved execution (compatibility level 140+) uses the actual row count on first compilation.
  An inline TVF is expanded into the calling query, so it gets real estimates.
- **Table-valued parameters** must be declared `READONLY`, SQL Server keeps no statistics on them, and the caller
  needs `EXECUTE` *and* `REFERENCES` on the table type (that matters in episode 6, where the app user only gets
  `EXECUTE`).
- **`LINENO` is a reserved word** (Learn's reserved keyword list), so the order line column is `LineNumber`.
  Microsoft's parser rejects `LineNo` as an unquoted column name (`Incorrect syntax near 'LineNo'`); a test keeps
  that check.
- **Local harness notes:** sqlglot gives a composite `PRIMARY KEY (a, b)` sort options that DuckDB rejects (dropped
  in `labdb.transpile`), renders `CROSS APPLY` in a form DuckDB doesn't parse (rewritten as `CROSS JOIN LATERAL`), and
  can't parse `OPTION (USE HINT(...))` (stripped before the local run; a hint changes the plan, not the rows).
  mssql-python rejects the ADO.NET keyword `Connection Timeout` in a connection string.

## References

- [Scalar UDF inlining (requirements, is_inlineable, how to see it in the plan, USE HINT, INLINE = OFF)](https://learn.microsoft.com/sql/relational-databases/user-defined-functions/scalar-udf-inlining)
- [Intelligent query processing: interleaved execution for multi-statement TVFs (fixed guess of 100 rows)](https://learn.microsoft.com/sql/relational-databases/performance/intelligent-query-processing-details#interleaved-execution-for-mstvfs)
- [Create user-defined functions](https://learn.microsoft.com/sql/relational-databases/user-defined-functions/create-user-defined-functions-database-engine)
- [SET XACT_ABORT](https://learn.microsoft.com/sql/t-sql/statements/set-xact-abort-transact-sql)
- [THROW (error number range, semicolon rule, differences from RAISERROR)](https://learn.microsoft.com/sql/t-sql/language-elements/throw-transact-sql)
- [TRY...CATCH](https://learn.microsoft.com/sql/t-sql/language-elements/try-catch-transact-sql)
- [Return data from a stored procedure (output parameters, return codes)](https://learn.microsoft.com/sql/relational-databases/stored-procedures/return-data-from-a-stored-procedure)
- [Use table-valued parameters (READONLY, permissions, limitations)](https://learn.microsoft.com/sql/relational-databases/tables/use-table-valued-parameters-database-engine)
- [CREATE SEQUENCE](https://learn.microsoft.com/sql/t-sql/statements/create-sequence-transact-sql)
- [sys.sql_modules](https://learn.microsoft.com/sql/relational-databases/system-catalog-views/sys-sql-modules-transact-sql)
- [ScriptDom (Microsoft.SqlServer.TransactSql.ScriptDom)](https://learn.microsoft.com/dotnet/api/microsoft.sqlserver.transactsql.scriptdom)
- [mssql-python driver](https://learn.microsoft.com/sql/connect/python/mssql-python/python-sql-driver-mssql-python)
- Blog: [Stored Procedures & Functions — Complete Guide](https://www.devladlog.com/articles/sql/2025-07-31-stored-procedures-functions-complete-guide-2025/)
