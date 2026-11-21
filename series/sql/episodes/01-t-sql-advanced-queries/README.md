# DEVLADLOG SQL #1 — T-SQL Advanced Queries

Ten T-SQL queries on a small, fictional **Contoso Bikes** database, each one answering a question that is painful
with plain `GROUP BY` and joins:

| Query | Technique | Question |
|---|---|---|
| `q01` | `SUM() OVER`, `LAG`, `WINDOW` clause, `DATETRUNC` | Monthly revenue per region, running total, change vs previous month |
| `q02a` / `q02b` | `ROW_NUMBER()` vs `CROSS APPLY` + `TOP` | The two biggest orders per customer (same answer, two ways) |
| `q03` | `OUTER APPLY` | Latest order per customer, **including** customers with no orders |
| `q04` | Gaps and islands | Streaks of consecutive login days per user |
| `q05` | Recursive CTE, `MAXRECURSION` | The whole org chart, level and path, from one self-referencing table |
| `q06a` / `q06b` | `PIVOT` vs conditional aggregation | Revenue per region per month as a cross-tab |
| `q07` | `GROUPING SETS`, `GROUPING()` | Detail, region subtotals and grand total in one pass |
| `q08` | **The gotcha**: default window frame | Why `SUM() OVER (ORDER BY OrderDate)` is not a running total when dates repeat |

The same `.sql` files run in two places:

- **SQL Server 2022 / Azure SQL** (the demo): unchanged, batch by batch, through Microsoft's `mssql-python` driver.
- **Locally, no server** (tests and CI): every batch is parsed with [sqlglot](https://github.com/tobymao/sqlglot)'s
  T-SQL dialect and transpiled to **DuckDB**, an in-process engine. Docker isn't available in the build container, so
  this is how every query was executed here. The results are written to `expected/*.csv`, and the demo checks that
  SQL Server returns exactly the same rows.

| Path | What it is |
|---|---|
| [`src/sql/00-create-database.sql`](src/sql/00-create-database.sql) | SQL Server only: creates `ContosoLab`, sets compatibility level 160 (needed by the `WINDOW` clause) |
| [`src/sql/01-schema-and-data.sql`](src/sql/01-schema-and-data.sql) | Schemas `Sales`, `HR`, `App`; 6 customers, 21 orders, 9 employees, 14 logins. Re-runnable |
| [`src/sql/q01…q08*.sql`](src/sql) | The ten queries, one file each, commented |
| [`src/tsql_runner.py`](src/tsql_runner.py) | Runs the files on `duckdb` (default) or `sqlserver`, compares with `expected/`, `--show` prints a result |
| [`expected/`](expected) | The expected result of every query (CSV, normalised: 2 decimals, ISO dates, `NULL`) |
| [`tests/test_queries.py`](tests/test_queries.py) | 31 pytest tests: every query vs an **independent Python computation**, plus the runner itself |
| [`requirements.txt`](requirements.txt) | `sqlglot`, `duckdb`, `pytest`; `mssql-python` for the SQL Server engine |

## Run it locally (no SQL Server needed)

```bash
pip install -r requirements.txt
python3 src/tsql_runner.py                 # 10/10 queries match expected/ on duckdb
python3 src/tsql_runner.py --show q04      # print one result as a table
python3 -m pytest tests -q                 # 31 passed
```

## Run it on SQL Server 2022

The recording uses the shared lab VM **CON-SQL01** (SQL Server 2022 Developer, `10.50.0.30,1433`, see
`series/LAB.md`); see demo.md for the full recording steps.

```powershell
# 1. run src/sql/00-create-database.sql against master on 10.50.0.30,1433 (VS Code MSSQL extension, SSMS or sqlcmd)
# 2. then, from this folder (password typed, never stored):
$pw = Read-Host -AsSecureString 'sa password'
$env:SQL_CONNECTION_STRING = "Server=10.50.0.30,1433;Database=ContosoLab;UID=sa;PWD=$([Net.NetworkCredential]::new('', $pw).Password);Encrypt=yes;TrustServerCertificate=yes"
python src/tsql_runner.py --engine sqlserver --setup     # expect: 10/10 queries match expected/ on sqlserver
```

`TrustServerCertificate=yes` and the `sa` login are for the isolated lab VM only (Learn says the same in the
mssql-python quickstart). The SQL Server path was exercised here up to the network: the driver loads and fails with
`TCP Provider: Error code 0x2749` because there is no server. **The first real run on SQL Server is part of the
demo** (see [demo.md](demo.md)).

## What we learned / gotchas

- **The default window frame (q08).** With `ORDER BY` and no `ROWS`/`RANGE`, aggregate window functions use
  `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, and `RANGE` includes every row with the same `ORDER BY` value.
  Orders 2 and 3 are both on 15 January, so both show 4,030.50 as their "running total". Write
  `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` and add a unique tie-breaker (`OrderId`). The test checks both
  behaviours.
- **Top-N needs a tie-breaker (q02).** Customer 1 has two orders of 1,250.00. Without `OrderId` in the `ORDER BY`,
  which one is "second" is up to the engine.
- **`LAG` looks at the previous row, not the previous month (q01).** Centre has no April orders, so its May row
  compares with March. If you need calendar months, build the month list first.
- **Gaps and islands needs distinct days (q04).** Without `DISTINCT`, alex.demo's two logins on 1 March shift the row
  numbers, and the query invents a "streak" from 1 to 6 March (4 March was never logged). There's a test for it.
- **Recursive CTEs: same types in both members (q05).** The anchor and the recursive member must return the same data
  types, hence `CAST(... AS nvarchar(400))` on `Path` in both. `MAXRECURSION` defaults to 100; we set 10 so a
  `ManagerId` cycle fails fast.
- **PIVOT returns `NULL` for an empty cell, not 0** (Centre, April). Conditional aggregation behaves the same way
  unless you add `ELSE 0`.
- **Engine differences we had to handle in the local harness** (never in the `.sql` files' logic):
  - DuckDB checks a self-referencing foreign key row by row; SQL Server checks it per statement. The seed script inserts
    employees one level per `INSERT`, which works on both.
  - sqlglot can't type-check `+`, so `'a' + 'b'` would reach DuckDB as numeric addition. The queries use `CONCAT()`,
    which is plain T-SQL anyway.
  - The harness drops `OPTION (...)` hints, adds `RECURSIVE` to self-referencing CTEs, and rewrites `CROSS APPLY` /
    `OUTER APPLY` as DuckDB `LATERAL` joins. All three are in `transpile()` and covered by tests.
  - Collation: SQL Server's default collations are case-insensitive, DuckDB compares binary. The data only uses
    values whose order is the same either way; keep that in mind before adding rows.

## References

- [SELECT - OVER clause (default frame, ROWS vs RANGE)](https://learn.microsoft.com/sql/t-sql/queries/select-over-clause-transact-sql)
- [SELECT - WINDOW clause (SQL Server 2022, compatibility level 160)](https://learn.microsoft.com/sql/t-sql/queries/select-window-transact-sql)
- [DATETRUNC](https://learn.microsoft.com/sql/t-sql/functions/datetrunc-transact-sql)
- [FROM clause plus JOIN, APPLY, PIVOT](https://learn.microsoft.com/sql/t-sql/queries/from-transact-sql)
- [Using PIVOT and UNPIVOT](https://learn.microsoft.com/sql/t-sql/queries/from-using-pivot-and-unpivot)
- [WITH common_table_expression (recursive CTE rules)](https://learn.microsoft.com/sql/t-sql/queries/with-common-table-expression-transact-sql)
- [Query hints: MAXRECURSION](https://learn.microsoft.com/sql/t-sql/queries/hints-transact-sql-query)
- [GROUP BY: ROLLUP, CUBE, GROUPING SETS](https://learn.microsoft.com/sql/t-sql/queries/select-group-by-transact-sql) and [GROUPING](https://learn.microsoft.com/sql/t-sql/functions/grouping-transact-sql)
- [ALTER DATABASE compatibility level](https://learn.microsoft.com/sql/t-sql/statements/alter-database-transact-sql-compatibility-level)
- [mssql-python driver](https://learn.microsoft.com/sql/connect/python/mssql-python/python-sql-driver-mssql-python) and [quickstart](https://learn.microsoft.com/sql/connect/python/mssql-python/python-sql-driver-mssql-python-quickstart)
- [Run SQL Server Linux container images with Docker](https://learn.microsoft.com/sql/linux/install-upgrade/quickstart-install-docker)
- Blog: [T-SQL Advanced Queries — Complete Guide](https://www.devladlog.com/articles/sql/2025-07-17-t-sql-advanced-queries-complete-guide-2025/)
