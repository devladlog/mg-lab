# DEVLADLOG SQL #4 — Query Optimization

Episode 3 designed the indexes. This episode is about the queries that **have the right index and still don't
use it well**. Same database (`ContosoBikesPerf`: 20,000 customers, 200,000 orders, customer 1 *Contoso Megastore*
owns 60,000 of them), three problems, each one proven from SQL Server's **actual execution plan**:

| Scenario | The problem | The fix we prove |
|---|---|---|
| `sargable` | `WHERE YEAR(OrderDate) = 2025 AND MONTH(OrderDate) = 3`: a function on the column, so the index on `OrderDate` can only be scanned | A half-open range on the bare column: index seek, same result |
| `conversion` | `WHERE AccountNumber = 104242` on a `varchar` column: `int` wins data type precedence, the **column** gets converted, plan warning, no seek | Compare with a value of the column's type (`'104242'`): seek, no warning |
| `sniffing` | A stored procedure compiled for whichever customer calls first; the Megastore (60,000 orders) and a typical customer (7) need opposite plans | Both orders of arrival measured, then `OPTION (RECOMPILE)` (one plan per call) |
| `query-store` | Plans come and go with the cache | Query Store lists every plan the procedure has had; we force the one that is good enough for both |

Every run has checks (`"has: Index Seek @ IX_Orders_OrderDate"`, `"warning: PlanAffectingConvert"`,
`"compiled: 4242"`, `"runtime: 1"`, `"more pages than: Megastore first"`) and a result check: a rewrite must return
exactly what the original returned.

| Path | What it is |
|---|---|
| [`src/sql/00-create-database.sql`](src/sql/00-create-database.sql), [`01-schema-and-data.sql`](src/sql/01-schema-and-data.sql) | Same files as episode 3 (database, Query Store `ALL`, generated data) |
| [`src/sql/02-indexes.sql`](src/sql/02-indexes.sql) | The starting indexes: `IX_Orders_CustomerId`, `IX_Orders_OrderDate`, `UX_Customers_AccountNumber`; removes episode 3's |
| [`src/sql/03-procedures.sql`](src/sql/03-procedures.sql) | `Sales.GetCustomerOrders` and `Sales.GetCustomerOrders_Recompile` (same query + `OPTION (RECOMPILE)`) |
| [`src/sql/q01a…q02b*.sql`](src/sql) | The two rewrites, before and after |
| [`src/sql/psp-off.sql`](src/sql/psp-off.sql), [`psp-on.sql`](src/sql/psp-on.sql) | Parameter Sensitive Plan optimization off (to reproduce the problem) and back to the default |
| [`src/sql/qs-*.sql`](src/sql) | Query Store: plans per procedure (shape, executions, average logical reads), forced plans and forcing failures |
| [`src/tune_lab.py`](src/tune_lab.py) | The runner: scenarios, checks, local run (DuckDB), SQL Server run (`--save-plans`) |
| [`src/showplan.py`](src/showplan.py), [`src/labdb.py`](src/labdb.py) | Same files as episode 3: showplan reader (operators, pages read, warnings, compiled vs runtime parameter values) and the engines |
| [`expected/`](expected) | Expected results; `proc-customer-orders.csv` holds row count, revenue, first and last `OrderId` per customer |
| [`tests/`](tests) | 50 pytest tests (data, rewrites, checks, runner, plan reader, script.yaml); `plan_builder.py` builds showplan XML for them |

## Run it locally (no SQL Server needed)

```bash
pip install -r requirements.txt
python3 src/tune_lab.py               # rewrites return identical results, procedure query 60000 and 7 rows, 8/8 files parse
python3 -m pytest tests -q            # 50 passed (38 passed, 12 skipped without the schema file)
```

As in episode 3: the data, the rewrites and the procedure's query are **executed** on DuckDB (T-SQL transpiled by
sqlglot; Docker isn't available here) and compared with an independent Python computation. The plans are **not**:
the checks and the plan reader are tested on showplan XML built from the official schema's elements (validated
against it when `tests/.xsd/showplanxml.xsd` is present:
`mkdir -p tests/.xsd && curl -o tests/.xsd/showplanxml.xsd https://schemas.microsoft.com/sqlserver/2004/07/showplan/sql2022/showplanxml.xsd`), and the SQL
Server run (plan cache, `sp_recompile`, Query Store forcing) is tested against a fake connection that behaves like
a plan cache. SQL Server's real choices come from the recording on CON-SQL01 ([demo.md](demo.md)). The mssql-python
path was exercised up to the network (`TCP Provider: Error code 0x2749`, no server).

`00-create-database.sql`, `03-procedures.sql` and the two `psp-*.sql` files are SQL Server only: sqlglot doesn't
parse database options or procedure bodies meaningfully. The procedure's `SELECT` is extracted and executed
locally, and a test checks that both procedures contain the same query.

## Run it on SQL Server 2022 (CON-SQL01)

```bash
# database from episode 3, or run src/sql/00-create-database.sql against master first
export SQL_CONNECTION_STRING="Server=10.20.0.30,1433;Database=ContosoBikesPerf;UID=<lab login>;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
python3 src/tune_lab.py --engine sqlserver --setup --save-plans plans
# expect: four tables, every check OK, "12/12 runs behaved as expected on sqlserver";
# one plan stays forced in Query Store (the runner prints the unforce command)
```

## What we learned / gotchas

- **Whoever runs first decides.** With one cached plan per procedure, the Megastore calling first gives everyone a
  clustered index scan (a typical customer reads the whole table for 7 rows); a typical customer calling first gives
  the Megastore an index seek with one key lookup per row, 60,000 times. The plan XML shows both values:
  `ParameterCompiledValue` and `ParameterRuntimeValue`. The runner prints them as `compiled/runtime`.
- **SQL Server 2022 may fix this for you, sometimes.** At compatibility level 160, Parameter Sensitive Plan (PSP)
  optimization can cache several plans for one parameterized query, one per selectivity range (look for
  `QueryVariantID` in the plan). Learn doesn't publish the skewness thresholds, so the lab turns it off
  (`psp-off.sql`) to make the classic problem reproducible. Turn it back on with `psp-on.sql`.
- **`OPTION (RECOMPILE)` isn't free.** It compiles the statement on every execution; Learn warns to assess the
  impact on the whole workload. Other documented options: `OPTIMIZE FOR` a typical value, `OPTIMIZE FOR UNKNOWN`
  (density average), or forcing a plan with Query Store.
- **A forced plan is a decision you now own.** Learn: forcing doesn't guarantee that exact plan, it fails if the
  plan's index is dropped or disabled (`force_failure_count`, `last_force_failure_reason_desc`), and manually forced
  plans shouldn't stay forever. `qs-forced-plans.sql` is the check; the runner unforces leftovers before it starts.
- **Query Store is on by default for new databases in SQL Server 2022**, but `QUERY_CAPTURE_MODE` defaults to `AUTO`
  (thresholds on executions and CPU). Queries inside stored procedures are always captured; the lab database uses
  `ALL` anyway so the ad hoc queries show up too.
- **Implicit conversion converts the side with lower precedence.** `int` ranks above `varchar`, so
  `AccountNumber = 104242` converts every `AccountNumber` (`CONVERT_IMPLICIT(int, ...)`); `'104242'` converts
  nothing. Learn's post-migration guide lists `int`-to-`varchar` conversions among non-SARGable predicates and says to
  look for `CONVERT_IMPLICIT` warnings in actual plans; the runner checks the plan for a `PlanAffectingConvert`
  warning.
- **Date ranges: half-open.** `>= '2025-03-01' AND < '2025-04-01'` is right for `date` and for `datetime` columns
  alike; the ISO `yyyy-MM-dd` literal is read the same whatever the session's `DATEFORMAT` (Learn, `date` type).
- **Engine differences in the local harness:** DuckDB compares the `varchar` column with the `int` literal without
  complaint, so locally `q02a` and `q02b` return the same row, as they do on SQL Server; the difference is only in the
  plan. DuckDB rejects `'20250301'` as a date literal, so the files use `'2025-03-01'`.

## References

- [Index design guide: SARGable predicates, key order](https://learn.microsoft.com/sql/relational-databases/sql-server-index-design-guide)
- [Post-migration guide: non-SARGable predicates, CONVERT_IMPLICIT warnings](https://learn.microsoft.com/sql/relational-databases/post-migration-validation-and-optimization-guide#inability-to-use-predicates-to-filter-data)
- [Data type precedence](https://learn.microsoft.com/sql/t-sql/data-types/data-type-precedence-transact-sql) and [Data type conversion](https://learn.microsoft.com/sql/t-sql/data-types/data-type-conversion-database-engine)
- [Query processing architecture guide: parameter sensitivity, OPTION (RECOMPILE)](https://learn.microsoft.com/sql/relational-databases/query-processing-architecture-guide#parameter-sensitivity)
- [Parameter Sensitive Plan optimization](https://learn.microsoft.com/sql/relational-databases/performance/parameter-sensitive-plan-optimization) and [ALTER DATABASE SCOPED CONFIGURATION](https://learn.microsoft.com/sql/t-sql/statements/alter-database-scoped-configuration-transact-sql)
- [Query hints (RECOMPILE, OPTIMIZE FOR)](https://learn.microsoft.com/sql/t-sql/queries/hints-transact-sql-query)
- [Tune performance with the Query Store (force and unforce plans)](https://learn.microsoft.com/sql/relational-databases/performance/tune-performance-with-the-query-store), [sp_query_store_force_plan](https://learn.microsoft.com/sql/relational-databases/system-stored-procedures/sp-query-store-force-plan-transact-sql), [sys.query_store_plan (forcing failures)](https://learn.microsoft.com/sql/relational-databases/system-catalog-views/sys-query-store-plan-transact-sql)
- [Best practices for monitoring workloads with Query Store (check forced plans)](https://learn.microsoft.com/sql/relational-databases/performance/best-practice-with-the-query-store)
- [ALTER DATABASE SET options: QUERY_CAPTURE_MODE](https://learn.microsoft.com/sql/t-sql/statements/alter-database-transact-sql-set-options) and [How Query Store collects data](https://learn.microsoft.com/sql/relational-databases/performance/how-query-store-collects-data)
- [Automatic tuning: forced plans shouldn't stay forever](https://learn.microsoft.com/sql/relational-databases/automatic-tuning/automatic-tuning#automatic-plan-correction)
- [Showplan operator reference (Key Lookup)](https://learn.microsoft.com/sql/relational-databases/showplan-logical-and-physical-operators-reference) and [SET STATISTICS XML](https://learn.microsoft.com/sql/t-sql/statements/set-statistics-xml-transact-sql)
- [date literal formats](https://learn.microsoft.com/sql/t-sql/data-types/date-transact-sql#supported-string-literal-formats-for-date)
- [mssql-python driver](https://learn.microsoft.com/sql/connect/python/mssql-python/python-sql-driver-mssql-python)
- Blog: [Query Optimization — Complete Guide](https://www.devladlog.com/articles/sql/2025-07-27-query-optimization-complete-guide-2025/)
