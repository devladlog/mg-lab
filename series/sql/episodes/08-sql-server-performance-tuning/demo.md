# Demo shot list — SQL #8 SQL Server Performance Tuning

## Lab environment

Everything runs on the shared lab VM **CON-SQL01** (SQL Server 2022 Developer). One database, `ContosoBikesPerf` (episode 4's
200,000 orders, ~100 MB, created by episodes 3-4 or by `--setup`) plus a small `Tune` schema in it. No tenant, no Azure, no
licence, cost 0. The only server-level change is a permission for the demo login; the only database-level change is
`READ_COMMITTED_SNAPSHOT`, switched on during the demo and **off again in tear-down**.

| Machine | What | Notes |
|---|---|---|
| **CON-SQL01** (existing, `series/LAB.md`) | Windows Server 2025 Datacenter Eval, Server Core, SQL Server 2022 Developer, default instance, TCP 1433, mixed auth, 10.50.0.30, 2 vCPU / 2–6 GB | ~100 MB for the data. With 2 vCPUs, parallelism waits will be rare: that is expected |
| **Recording laptop** (host, 10.50.0.1) | SSMS (any current version), Python 3.10+, Windows Terminal (dark theme) | `py -m pip install -r requirements.txt` in this folder |

Login: `lab_demo`, the SQL login from episode 3's demo.md. This episode needs more than episodes 3-4:
`CREATE DATABASE` for `--setup` if the database does not exist (or run `--setup` as the lab Administrator), and **server-state
rights for the DMVs**. Learn lists `VIEW SERVER PERFORMANCE STATE` as the permission for the server-state DMVs and
`DBCC SQLPERF` on SQL Server 2022 and later (it was `VIEW SERVER STATE` before). As the lab Administrator:

```sql
GRANT VIEW SERVER PERFORMANCE STATE TO lab_demo;      -- undo in tear-down step 3
```

`lab_demo` also has to be allowed to `ALTER DATABASE ContosoBikesPerf` (the RCSI switch). The permission needed for that
statement was not checked here; if the first real run says it is denied, use a sysadmin login on the lab VM for this
episode (and undo it in tear-down) rather than guessing at narrower grants.

## What was verified where

| Step | Verified in the build container (Linux, no Docker) | Needs CON-SQL01 (the recording) |
|---|---|---|
| Every `.sql` file | parsed with Microsoft's ScriptDom (`TSql160Parser`): 0 errors; structure checks | **run them** |
| Data and statements: 200,000 orders, the workload statements, `UPDATE` then `ROLLBACK`, the delta query on made-up snapshots | yes: executed on DuckDB | the same on SQL Server |
| `t01` configuration review | no (`sys.configurations`, `dm_os_sys_info`) | **first real run**: `LearnDefault` column must match; live values are `*` in `expected/` |
| `t02` top statements | no (`dm_exec_query_stats`) | **first real run**: scan = 3 executions rank 1, seek = 50 executions rank 2 |
| Blocking, diagnosis, RCSI, waits | the **orchestration** runs against a fake server with real threads (blocks until rollback, refuses RCSI while another connection is open) | **the real behaviour**: `LCK_M_S`, the diagnosis columns, the reader returning `Shipped` instantly under RCSI, the wait deltas |
| Runner against a fake connection | yes (setup order, the three steps, failure cases, tear-down) | — |

If SQL Server disagrees with an expected row, **don't edit `expected/` to make it pass**: find out why, write it in README
"gotchas" and adjust the narration in `script.yaml`. Things most likely to need a look on the first real run:

- **`t02`**: the statement-offset idiom and the `SELECT @%mglab-w-%` filter must match exactly one row per workload (the
  outer batch that calls `sp_executesql` could also appear in `dm_exec_query_stats`); executions 3 and 50 assume one cached
  plan per statement (parameterised via `sp_executesql`). The ranking is by logical reads (3 scans of a 200,000-row table
  against 50 key lookups), so scan first is expected, but it has not been seen on a real server.
- **`t03`**: the reader must show up in `dm_exec_requests` with `LCK_M_S` (it takes a shared lock on the key or row); if a
  different lock type shows (`LCK_M_IS` is possible for an intent lock at page or table level when the plan scans), the
  expected row `LCK_M_S` and the narration need a look. The blocker's last statement comes from
  `sys.dm_exec_connections.most_recent_sql_handle`: it should be the batch that ran the `UPDATE`, which includes the file's
  comments (the check only looks for `UPDATE Sales.Orders`).
- **`t04`**: `Tune.usp_WaitDelta` ranks by wait time; on a quiet lab VM the 3 seconds of `LCK_M_S` should lead, but a busy
  `WRITELOG` or `PAGEIOLATCH_*` burst during the window could outrank it. The "covers the time the reader was blocked" check is
  `LCK_M_S` delta >= 80% of the reader's measured elapsed time. The wait is recorded only once it finishes (Learn), so the
  snapshot must be taken after the writer has rolled back: the runner does this.
- **RCSI second round**: the reader is expected to return in under 2 seconds with `Shipped`. Under RCSI the plan cache of the
  database is cleared by the `ALTER DATABASE` (Learn); nothing in the episode depends on cached plans after that point.

## Setup (once, before recording)

1. Start the lab (`lab/hyperv/Start-MGLab.ps1`); check CON-SQL01 answers on 10.50.0.30:1433. Grant `lab_demo` the permission above.
2. Terminal on the laptop, in this folder (password typed off-screen):
   ```powershell
   py -m pip install -r requirements.txt
   $env:SQL_CONNECTION_STRING = "Server=10.50.0.30,1433;Database=master;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
   py src/perf_lab.py --engine sqlserver --setup
   ```
   Expected: the setup line, three steps ending `=> OK` (the first prints the config table, the second prints `ran w01-workload`
   and the scan/seek table, the third prints the incident table and the waits table), then `3/3 steps behaved as expected on sqlserver`.
   The data load takes a minute or two (200,000 rows). Dry-run it; it is repeatable (`01-schema-and-data.sql` drops and
   recreates the tables, `10-tune-tools.sql` recreates the `Tune` objects).
3. SSMS: connect to CON-SQL01 as `lab_demo` **three times** (three query windows, three sessions: writer, reader, diagnoser). Open
   `t03a-blocker.sql`, `t03b-reader.sql`, `t03c-diagnose.sql` in them, and `t02-top-queries.sql`, `t04-wait-delta.sql` in a fourth tab.
   Make sure RCSI is off before the first take: `SELECT is_read_committed_snapshot_on FROM sys.databases WHERE name = N'ContosoBikesPerf';` returns 0.

## Screens to capture (match the `screen` scenes in script.yaml)

Capture by hand in SSMS, in this order (the steps change the server):

| Scene id | File | What must be on screen |
|---|---|---|
| `top-screen` | `screens/t02-top-queries.jpg` | after `w01-workload.sql` (run it in SSMS first, a few seconds): `t02-top-queries.sql` grid, two rows: `scan, 3, 1, <large>` and `seek, 50, 2, <single digits>` |
| `gotcha-screen` | `screens/t03c-diagnose.jpg` | order: (1) `Tune.usp_TakeWaitSnapshot` N'before-blocking' in the diagnoser window; (2) window 1: run `t03a-blocker.sql` (open transaction); (3) window 2: run `t03b-reader.sql`: it spins; (4) window 3: run `t03c-diagnose.sql`: one row, `LCK_M_S`, `BlockerOpenTransactions` 1. Mask session numbers and the wait resource |
| `rcsi-screen` | `screens/t03-rcsi-reader.jpg` | first finish the first round: window 1 `t03d-release.sql` (ROLLBACK), window 2 returns `Shipped`; take `after-blocking` snapshot. Close windows 1 and 2 (and any other connection to the database), run `t03e-enable-rcsi.sql` from a window connected to `master`, take `before-rcsi`. Reopen windows 1 and 2: `t03a-blocker.sql`, then `t03b-reader.sql`: it returns `Shipped` instantly while the transaction in window 1 is still open |
| `waits-screen` | `screens/t04-wait-delta.jpg` | `t04-wait-delta.sql` (needs the labels `before-blocking`, `after-blocking`): `LCK_M_S` first; then roll back window 1, take `after-rcsi`, run `t04b-wait-delta-after-rcsi.sql`: no `LCK_M_` row |

The simplest way to capture the waits screen without juggling: run the whole thing with the runner
(`py src/perf_lab.py --engine sqlserver --step t03-blocking`) and then run `t04-wait-delta.sql` and `t04b-wait-delta-after-rcsi.sql`
in SSMS; the runner leaves the four snapshots in `Tune.WaitSnapshot`. Optional inset for the `config` code scene: `t01-config-review.sql`
output. Optional terminal shot for the `runner` scene: the `=> OK` lines of `--step t03-blocking`.

To confirm the whole thing end to end once more before recording: `--reset-only`, then `--setup` again (3/3 OK).

## Masking

- Never show the password or `$env:SQL_CONNECTION_STRING`.
- Blur `10.50.0.30` and the login name in SSMS (title bar, status bar, Object Explorer), or connect through a hosts-file alias so it reads `CON-SQL01`.
- Session numbers and `wait_resource` in the diagnosis grid are not secret but change every run: mask them so the screen does not
  contradict the narration.
- All names (`Contoso Bikes`, `Customer 123`, `@contoso.com`) are fictional.

## Tear-down

1. `py src/perf_lab.py --engine sqlserver --reset-only`: `READ_COMMITTED_SNAPSHOT` OFF (`WITH ROLLBACK IMMEDIATE`) and the `Tune`
   objects dropped. Check in SSMS: `SELECT name, is_read_committed_snapshot_on FROM sys.databases WHERE name = N'ContosoBikesPerf';` returns 0.
   `ContosoBikesPerf` and its data stay (episodes 3 and 4 use it).
2. If a window with an open transaction is still open in SSMS, roll it back or close it (an open transaction would block the next episode's
   setup).
3. As the lab Administrator: `REVOKE VIEW SERVER PERFORMANCE STATE FROM lab_demo;`
4. `Remove-Item Env:SQL_CONNECTION_STRING` in the terminal.
