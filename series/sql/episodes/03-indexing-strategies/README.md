# DEVLADLOG SQL #3 — Indexing Strategies

Contoso Bikes (the fictional company from episodes 1 and 2) has grown: **20,000 customers and 200,000 orders**,
and the only index on `Sales.Orders` is the clustered primary key. We take three real queries and design an index
for each, step by step, and **measure every step from SQL Server's actual execution plan**: which operators ran,
on which index, how many pages were read, and how big the index is.

| Query | Index steps | What it shows |
|---|---|---|
| `q01` order history for one customer | none → `(CustomerId)` → `(OrderDate, CustomerId)` covering → `(CustomerId, OrderDate DESC)` covering | Seek vs scan, Key Lookup, covering indexes, and **key column order** (same columns, wrong order = a scan) |
| `q02` open orders since June 2026 | none → full-table `(Status, OrderDate)` → filtered `(OrderDate) WHERE Status = 'Open'` | A filtered index does the same seek with a fraction of the size |
| `q03` revenue per year and channel | none → nonclustered columnstore | No `WHERE`, every row: columnstore + batch mode instead of a B-tree |

Each step has **checks** written as plain strings (`"has: Index Seek @ IX_Orders_CustomerId"`,
`"not: Key Lookup"`, `"fewer pages than: no index"`, `"index pages below 10% of: full-table index"`). The run fails
if SQL Server does something else. Every step also compares the query result with `expected/`: an index must
never change the answer.

| Path | What it is |
|---|---|
| [`src/sql/00-create-database.sql`](src/sql/00-create-database.sql) | SQL Server only: `ContosoBikesPerf`, compatibility level 160, SIMPLE recovery, Query Store on (episode 4 reuses this database) |
| [`src/sql/01-schema-and-data.sql`](src/sql/01-schema-and-data.sql) | `Sales.Customers`, `Sales.Orders` and the generated data (`GENERATE_SERIES`, integer arithmetic only: deterministic) |
| [`src/sql/q01…q03*.sql`](src/sql) | The three queries |
| [`src/sql/ix00…ix06*.sql`](src/sql) | `ix00` drops every lab index; `ix01`–`ix06` create one index each |
| [`src/sql/dmv-*.sql`](src/sql) | Index sizes (`sys.dm_db_partition_stats`), index usage (`sys.dm_db_index_usage_stats`), missing index requests |
| [`src/index_lab.py`](src/index_lab.py) | The runner: scenarios, checks, local run (DuckDB) and SQL Server run (`--save-plans` writes each actual plan as `.sqlplan`) |
| [`src/showplan.py`](src/showplan.py) | Reads XML showplans: access operators, pages read (`ActualLogicalReads` + `ActualLobLogicalReads`), missing index requests as `CREATE INDEX`, warnings, parameter values. `python src/showplan.py file.sqlplan` |
| [`src/labdb.py`](src/labdb.py) | Plumbing shared with episode 4: GO-batch splitting, mssql-python engine (with `SET STATISTICS XML`), DuckDB engine (T-SQL transpiled by sqlglot), CSV comparison |
| [`expected/`](expected) | Expected result of each query (CSV) |
| [`tests/`](tests) | 49 pytest tests (data, queries, checks, runner, plan reader, script.yaml); `plan_builder.py` builds showplan XML for the tests |

## Run it locally (no SQL Server needed)

```bash
pip install -r requirements.txt
python3 src/index_lab.py              # 200,000 orders generated, 3/3 queries match expected/, 14/14 files parse
python3 -m pytest tests -q            # 49 passed (40 passed, 9 skipped without the schema file, see below)
```

What runs locally, and what doesn't:

- **Data and results: executed.** Docker isn't available in the build container, so the T-SQL runs on **DuckDB**
  (in-process) after sqlglot parses it with its T-SQL dialect and transpiles it. The tests compare the data and
  all three results with an independent Python computation of the same formulas.
- **Plans: not executed.** DuckDB has no SQL Server optimizer. The checks and the plan reader are tested against
  showplan XML built with the elements and attributes of the official schema; with the schema file present, every
  test plan is validated against it:
  ```bash
  mkdir -p tests/.xsd && curl -o tests/.xsd/showplanxml.xsd \
      https://schemas.microsoft.com/sqlserver/2004/07/showplan/sql2022/showplanxml.xsd
  ```
- **The SQL Server run** (drop, create, capture the actual plan, measure the index, compare the result) is tested
  end to end against a fake connection. That proves the orchestration, not SQL Server's choices. **Those come from
  the recording on CON-SQL01** ([demo.md](demo.md)).
- The SQL Server path was exercised here up to the network: mssql-python loads and fails with
  `TCP Provider: Error code 0x2749` (no server).

## Run it on SQL Server 2022 (CON-SQL01)

```bash
# 1. run src/sql/00-create-database.sql against master (SSMS or sqlcmd), as the lab Administrator
# 2. from this folder (the password is typed off-screen):
export SQL_CONNECTION_STRING="Server=10.50.0.30,1433;Database=ContosoBikesPerf;UID=<lab login>;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
python3 src/index_lab.py --engine sqlserver --setup --save-plans plans
# expect: three step tables, every check OK, "9/9 steps behaved as expected on sqlserver",
# then the final design's index sizes and usage
```

`TrustServerCertificate=yes` is for the lab's self-signed certificate only. `plans/*.sqlplan` open in SSMS.

## What we learned / gotchas

- **Same columns, wrong order.** `(OrderDate, CustomerId) INCLUDE (TotalAmount)` covers `q01`, but the rows for one
  customer are spread across the whole index, so it can only be scanned. Learn's design guide: put the column used
  in the equality predicate first. `(CustomerId, OrderDate DESC)` seeks to the customer and returns the rows
  already sorted.
- **A foreign key doesn't create an index** (episode 2). `FK_Orders_Customers` exists from the start; `q01` still
  scans the table until we index `CustomerId`.
- **Key Lookup = one trip to the clustered index per row.** Fine for 7 rows; Learn notes that a Key Lookup with
  many executions relative to the table size might benefit from a covering index. Episode 4 shows what happens when
  the same plan meets 60,000 rows.
- **You don't need the clustered key in your index.** Every nonclustered index carries the clustered key (`OrderId`)
  already.
- **A filtered index only helps queries whose predicate matches the filter.** `Status` isn't in `IX_Orders_Open`:
  Learn says the filter column needn't be a key or included column when the query predicate is equivalent to the
  filter and the column isn't returned. Filtered indexes also need the `SET` options listed in `CREATE INDEX`
  (`ANSI_NULLS`, `QUOTED_IDENTIFIER` and others `ON`); the ODBC defaults used by mssql-python satisfy them.
- **Missing index requests are hints, not designs** (Learn): key columns come without an order, filtered and unique
  indexes are never suggested, included columns come without a size check, at most 600 groups are kept, nothing
  is suggested for trivial plans, and the DMVs are cleared on restart and whenever the table's indexes change. The
  runner prints the request from the step 1 plan as a `CREATE INDEX` (equality, then inequality, then `INCLUDE`)
  or says why there is none, so you can compare it with the index we designed.
- **Batch mode isn't only for columnstore.** Since SQL Server 2019, batch mode on rowstore can kick in for
  analytic queries, so the `q03` baseline may already show batch operators. The check that matters is the
  columnstore scan and how much it reads.
- **Index usage counters reset on restart** (`sys.dm_db_index_usage_stats`). `user_updates` is what every index
  costs your writes.
- **Engine differences we handled in the local harness** (never in the `.sql` files' logic):
  - sqlglot can't parse `PRIMARY KEY CLUSTERED` inline, so the schema uses `PRIMARY KEY`, which is clustered by
    default in SQL Server when the table has no clustered index yet.
  - T-SQL's `GENERATE_SERIES` returns a column named `value`; DuckDB calls it `generate_series`. `transpile()`
    adds the column alias (`AS s(value)`); a test covers it.
  - Date literals are ISO `'2026-06-01'`: DuckDB rejects `'20260601'` as a date, and for the `date` type SQL
    Server reads `YYYY-MM-DD` the same way whatever the language setting.
  - The index DDL is only syntax-checked locally: DuckDB has no `INCLUDE`, filtered or columnstore indexes.

## References

- [Index architecture and design guide (key order, covering, filtered, columnstore)](https://learn.microsoft.com/sql/relational-databases/sql-server-index-design-guide)
- [Create filtered indexes](https://learn.microsoft.com/sql/relational-databases/indexes/create-filtered-indexes) and [CREATE INDEX: required SET options](https://learn.microsoft.com/sql/t-sql/statements/create-index-transact-sql#filtered-indexes)
- [Columnstore indexes: overview (nonclustered columnstore, batch mode)](https://learn.microsoft.com/sql/relational-databases/indexes/columnstore-indexes-overview)
- [Batch mode on rowstore](https://learn.microsoft.com/sql/relational-databases/performance/intelligent-query-processing-details#batch-mode-on-rowstore)
- [Tune nonclustered indexes with missing index suggestions (limitations)](https://learn.microsoft.com/sql/relational-databases/indexes/tune-nonclustered-missing-index-suggestions) and [sys.dm_db_missing_index_details](https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-objects/sys-dm-db-missing-index-details-transact-sql)
- [sys.dm_db_index_usage_stats](https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-objects/sys-dm-db-index-usage-stats-transact-sql)
- [Showplan operator reference (Key Lookup, Index Seek, Columnstore Index Scan)](https://learn.microsoft.com/sql/relational-databases/showplan-logical-and-physical-operators-reference)
- [SET STATISTICS XML](https://learn.microsoft.com/sql/t-sql/statements/set-statistics-xml-transact-sql) and [Save an execution plan in XML format](https://learn.microsoft.com/sql/relational-databases/performance/save-an-execution-plan-in-xml-format)
- [Primary and foreign key constraints (FKs aren't indexed automatically)](https://learn.microsoft.com/sql/relational-databases/tables/primary-and-foreign-key-constraints)
- [CREATE TABLE (PRIMARY KEY constraints default to CLUSTERED)](https://learn.microsoft.com/sql/t-sql/statements/create-table-transact-sql#primary-key-constraints)
- [date literal formats](https://learn.microsoft.com/sql/t-sql/data-types/date-transact-sql#supported-string-literal-formats-for-date) and [SET DATEFORMAT (ISO 8601 is read independently of it)](https://learn.microsoft.com/sql/t-sql/statements/set-dateformat-transact-sql)
- [GENERATE_SERIES (compatibility level 160, column `value`)](https://learn.microsoft.com/sql/t-sql/functions/generate-series-transact-sql)
- [mssql-python driver](https://learn.microsoft.com/sql/connect/python/mssql-python/python-sql-driver-mssql-python)
- Showplan schema: `https://schemas.microsoft.com/sqlserver/2004/07/showplan/sql2022/showplanxml.xsd`
- Blog: [Indexing Strategies — Complete Guide](https://www.devladlog.com/articles/sql/2025-07-24-indexing-strategies-complete-guide-2025/)
