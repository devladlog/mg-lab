# DEVLADLOG SQL #8 — SQL Server Performance Tuning

Episodes 3 and 4 tuned a query (indexes, plans, parameters). This episode is about the server around the queries, and
about **measuring before changing anything**. On episode 4's `ContosoBikesPerf` database (200,000 orders) it runs four
measurements: the configuration, the most expensive statements, a **real blocking incident** that the runner causes on
purpose and diagnoses from the DMVs (then fixes with `READ_COMMITTED_SNAPSHOT`), and wait statistics taken as the
**difference of two snapshots**. It does not repeat indexing or query rewriting.

| Step | What it shows | Expected (`expected/`) |
|---|---|---|
| `t01` configuration review | `max server memory`, `max degree of parallelism`, `cost threshold for parallelism` from `sys.configurations`, plus CPUs and memory from `sys.dm_os_sys_info` | the three Learn defaults in `LearnDefault`; the live values and notes are `*` (any value) |
| `w01` + `t02` top statements | a workload with markers (3 scans, 50 seeks), then `sys.dm_exec_query_stats` | `scan` 3 executions, rank 1; `seek` 50 executions, rank 2 (average reads are `*`) |
| `t03a`-`t03e` blocking | A holds an open `UPDATE` (no commit), B reads that row and waits, C diagnoses it (`dm_exec_requests`, `dm_exec_sql_text`, `dm_exec_sessions`, `dm_exec_connections`); A rolls back. Then RCSI on and the same round again | blocked, `LCK_M_S`, blocker = writer, open transaction, the reader reads `Shipped` after the rollback and also while the writer is still open under RCSI, without waiting |
| `t04` / `t04b` wait deltas | `Tune.usp_WaitDelta` between the snapshots around each round | top watch-list wait is `LCK_M_S` and covers the blocked time; no `LCK_M_*` wait with RCSI |

The two blocking tables are built by the runner from what each connection saw (`expected/t03-blocking.csv`,
`expected/t04-wait-delta.csv`), because session ids and wait milliseconds change on every run.

| Path | What it is |
|---|---|
| [`src/sql/00-create-database.sql`](src/sql/00-create-database.sql), [`01-schema-and-data.sql`](src/sql/01-schema-and-data.sql) | Episode 4's database and data, **unchanged copies** (a test compares them byte for byte with episode 4) |
| [`src/sql/10-tune-tools.sql`](src/sql/10-tune-tools.sql) | Schema `Tune`: `WaitSnapshot`, `usp_TakeWaitSnapshot`, `usp_WaitDelta`. The delta query sits between `-- delta-query-begin` and `-- delta-query-end` so the local check can run it |
| [`src/sql/t01`](src/sql/t01-config-review.sql), [`w01`](src/sql/w01-workload.sql), [`t02`](src/sql/t02-top-queries.sql) | Configuration review, workload (clears only this database's plan cache), top statements |
| [`src/sql/t03a`..`t03e`](src/sql) | Writer, reader, diagnosis, release (`ROLLBACK`), RCSI on. Each is a file you can also run by hand in three SSMS windows |
| [`src/sql/t04*.sql`](src/sql/t04-wait-delta.sql), [`t05-cleanup.sql`](src/sql/t05-cleanup.sql) | The two delta reads; tear-down (RCSI off, `Tune` objects dropped) |
| [`src/perf_lab.py`](src/perf_lab.py) | The runner: setup, the three steps, `blocking_phase` (three connections, a reader thread), `--reset-only`; local run on DuckDB |
| [`src/labdb.py`](src/labdb.py), [`tools/TsqlParse/`](tools/TsqlParse) | Engines (episode 6's file plus the `GENERATE_SERIES` adjustment of episodes 3-4) and Microsoft's T-SQL parser (ScriptDom) as a JSON CLI (same as episode 7) |
| [`expected/`](expected) | Expected results; a `*` cell matches any value |
| [`tests/`](tests) | 64 pytest tests |

## Run it locally (no SQL Server needed)

```bash
pip install -r requirements.txt
python3 src/perf_lab.py              # DuckDB: data, workload statements, rollback, the delta query on made-up snapshots
python3 -m pytest tests -q           # 64 passed
```

What runs where (Docker isn't available in the build container, so there is no SQL Server here):

- **Executed locally (DuckDB):** episode 4's data (200,000 orders); the two workload statements (the scan counts 57,164
  orders from 2025, the seek reads order 1 and gets `Shipped`); the blocker's `UPDATE` and the `ROLLBACK` (the row says
  `Cancelled` inside the transaction and `Shipped` after it); and the **delta query extracted from `usp_WaitDelta`**, run
  on two made-up snapshots (background waits `SLEEP_TASK` and `LAZYWRITER_SLEEP` are excluded even with huge deltas, a wait
  that did not change is absent, a wait that is new counts in full, the order is by delta time). DuckDB has no locks,
  DMVs or waits: nothing about blocking itself is checked there.
- **Parsed by Microsoft's parser (ScriptDom, SQL Server 2022 grammar):** every `.sql` file, 0 errors, plus structure checks
  (the diagnosis is read-only and uses the four DMVs, the blocker never commits, RCSI is switched on `WITH ROLLBACK
  IMMEDIATE` and off again in the tear-down, the workload clears only the database's plan cache, the ranking is a watch list).
- **Runner against a fake server with real threads:** the fake blocks the reader until the writer rolls back (unless RCSI is
  on), shows the wait to the diagnosing connection, and **refuses `ALTER DATABASE ... READ_COMMITTED_SNAPSHOT` while another
  connection is open**. Tests: all steps pass; a reader that is never blocked fails; RCSI that does not help fails; a lock
  wait shorter than the blocked time fails; a changed default or a wrong ranking fails; setup order; tear-down.
- **Needs SQL Server:** everything the DMVs return, the real waits, the real effect of RCSI. That is the recording on CON-SQL01
  ([demo.md](demo.md)).

## Run it on SQL Server 2022 (CON-SQL01)

```powershell
# a login that can create the database and read server state; see demo.md (GRANT VIEW SERVER PERFORMANCE STATE)
$env:SQL_CONNECTION_STRING = "Server=10.20.0.30,1433;Database=master;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
py src/perf_lab.py --engine sqlserver --setup
# expect: "3/3 steps behaved as expected on sqlserver"  (the blocking step takes about 10-15 seconds: the writer holds the lock for 3 s)
py src/perf_lab.py --engine sqlserver --step t03-blocking     # only the incident
py src/perf_lab.py --engine sqlserver --reset-only            # tear-down: RCSI off, Tune objects dropped
```

## What we learned / gotchas

- **Measure first.** Wait statistics tell you what the server waited for; the plan tells you what one query did. Learn's
  rule of thumb in its latch-contention guide: resolve the resource wait that represents the greatest proportion of overall
  wait time first.
- **`sys.dm_os_wait_stats` is cumulative and shows completed waits only.** Learn: values are since the instance started (or
  since `DBCC SQLPERF('sys.dm_os_wait_stats', CLEAR)`, which needs `ALTER SERVER STATE`), and the view "doesn't show current
  waits". Hence the snapshots: take one before and one after and subtract (Learn recommends exactly that). It also
  means a blocked reader is **invisible** in this view until its wait ends; the current block is in `sys.dm_exec_requests`.
- **A watch list, not an exclusion list.** A server always has background (queue) waits that add up to seconds in any window
  (Learn: queue waits belong to system background tasks). `usp_WaitDelta` ranks only waits worth acting on: `LCK_M_*`,
  `PAGEIOLATCH_*`, `PAGELATCH_*`, `WRITELOG`, `SOS_SCHEDULER_YIELD`, `CXPACKET`, `CXCONSUMER`, `ASYNC_NETWORK_IO`,
  `RESOURCE_SEMAPHORE`, `THREADPOOL`. It is a starting list, not a complete one.
- **Defaults are starting points.** Learn: `max degree of parallelism` 0 means up to 64 processors and "isn't the
  recommended value for most cases"; `cost threshold for parallelism` 5 is "a starting point, not a recommendation"; too low
  shows as `CXPACKET`/`CXCONSUMER` (and `THREADPOOL`, `SOS_SCHEDULER_YIELD`), too high as `SOS_SCHEDULER_YIELD`. The lab only
  **reads** these settings; it never changes them.
- **`sys.dm_exec_query_stats` is a cache, not a history.** One row per statement in a cached plan; rows disappear with the
  plan (Learn). It counts finished executions only. Query Store (episode 4) keeps the history. The lab clears only its own
  database's plan cache (`ALTER DATABASE SCOPED CONFIGURATION CLEAR PROCEDURE_CACHE`) so the counts start at zero, and cuts
  each statement out of its batch with the offsets (bytes, hence `/ 2`). Executions alone mislead: the 3 scans are expected to cost more
  than the 50 seeks (expected, not yet seen on a real server).
- **The blocker can be idle.** The writer is not running anything; it has an open transaction and an exclusive lock
  (Learn: a modification always takes an exclusive lock held until the transaction completes). The reader's session shows
  `blocking_session_id`, `wait_type`, `wait_time`; the blocker's last statement is in
  `sys.dm_exec_connections.most_recent_sql_handle`.
- **RCSI needs the database to itself.** Learn: setting `READ_COMMITTED_SNAPSHOT` needs no other active connection in the
  database (single-user mode is not required), and it accepts the `WITH ROLLBACK IMMEDIATE` termination clause. So the runner
  closes its three connections first and issues the `ALTER DATABASE` from `master`. Costs (Learn): up to 14 extra bytes per
  row, row versions in `tempdb`. Many `ALTER DATABASE` operations also clear the plan cache of that database, so the
  top-statements step runs **before** RCSI is switched on. The fix that matters in production is a shorter transaction.
- **Tear-down switches RCSI off again** (episodes 3 and 4 were recorded without row versioning) and drops the `Tune` objects.
- **Local harness:** DuckDB 2.0.1 returned too many rows for `LIMIT n` on the delta query (found by a test of `TOP`), so the
  local check removes `TOP (@Top)` and cuts the rows in Python; `TOP` itself is ordinary T-SQL for SQL Server. sqlglot attaches
  comments to statements, so the local check strips them before running the blocker/reader files.

## References

- [sys.dm_os_wait_stats](https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-objects/sys-dm-os-wait-stats-transact-sql) and [DBCC SQLPERF](https://learn.microsoft.com/sql/t-sql/database-console-commands/dbcc-sqlperf-transact-sql)
- [Diagnose and resolve latch contention (snapshots before and after peak load)](https://learn.microsoft.com/sql/relational-databases/diagnose-resolve-latch-contention)
- [sys.dm_exec_query_stats](https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-objects/sys-dm-exec-query-stats-transact-sql), [sys.dm_exec_requests](https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-objects/sys-dm-exec-requests-transact-sql), [sys.dm_exec_connections](https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-objects/sys-dm-exec-connections-transact-sql)
- [Server configuration: max degree of parallelism](https://learn.microsoft.com/sql/database-engine/configure-windows/configure-the-max-degree-of-parallelism-server-configuration-option) and [cost threshold for parallelism](https://learn.microsoft.com/sql/database-engine/configure-windows/configure-the-cost-threshold-for-parallelism-server-configuration-option)
- [ALTER DATABASE SET options (READ_COMMITTED_SNAPSHOT)](https://learn.microsoft.com/sql/t-sql/statements/alter-database-transact-sql-set-options) and [Transaction locking and row versioning guide](https://learn.microsoft.com/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide)
- [Monitor performance by using the Query Store](https://learn.microsoft.com/sql/relational-databases/performance/monitoring-performance-by-using-the-query-store)
- [mssql-python driver](https://learn.microsoft.com/sql/connect/python/mssql-python/python-sql-driver-mssql-python)
- Blog: [SQL Server Performance Tuning — Complete Guide](https://www.devladlog.com/articles/sql/2025-07-13-sql-server-performance-tuning-complete-guide-2025/)
