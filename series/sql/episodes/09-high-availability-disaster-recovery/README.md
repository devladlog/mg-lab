# DEVLADLOG SQL #9 — High Availability & Disaster Recovery

Episode 7 made sure you can get the data back. This episode asks the two questions that come with it: **how much would
we lose** (RPO) and **how long until we are selling again** (RTO). The lab builds **log shipping by hand** between two
databases on CON-SQL01, breaks it twice on purpose, fails over with a stopwatch running, and measures the exposure from
msdb.

`ContosoBikesHA` is the primary (episode 5's tables and data, **FULL recovery**). `ContosoBikesHA_Standby` is a restored
copy (`WITH STANDBY`: readable between log restores). Every step prints one result set that is compared with `expected/`.

| Step | What it shows | Expected |
|---|---|---|
| `h01` RPO before | `sys.databases` + `msdb.dbo.backupset`: newest full/diff/log and minutes at risk | primary, FULL, no backup at all (`NULL`s) |
| `h02` the standby | full backup, `RESTORE ... WITH STANDBY` (`MOVE` built as text) | standby `ONLINE (read-only standby)`, 8 orders on both |
| `h03` ship a log | order 1009 (`d01`), `BACKUP LOG`, `RESTORE LOG ... WITH STANDBY` | 9 and 9, 1 log restored |
| `h04` gotcha 1 | `INSERT` on the standby | error 3906 (read-only), standby still 9 |
| `h05` rogue log backup | order 1010 (`d02`), then a log backup the shipping job never sees | 2 log backups taken, 1 restored |
| `h06` gotcha 2 | order 1011 (`d03`), the next cycle | error 4305 ("too recent to apply"), primary 11, standby 9 |
| `h07` repair | restore the missing (rogue) log first, then the failed one | 11 and 11, 3 logs restored |
| `h08` failover | order 1012 (`d04`), tail-log backup `WITH NORECOVERY`, `RESTORE LOG ... WITH RECOVERY`; timed | old primary `RESTORING`, copy `ONLINE`, 12 orders, order 1012 present |
| `h09` write on the promoted copy | order 1013 | 13 orders |
| `h10` RPO after | the same query as `h01` | old primary `RESTORING`; promoted copy has **no backup history** |

| Path | What it is |
|---|---|
| [`src/sql/00-create-database.sql`](src/sql/00-create-database.sql), [`h00-reset.sql`](src/sql/h00-reset.sql) | Create `ContosoBikesHA` in FULL recovery; reset = drop both databases and delete their msdb history |
| [`src/sql/01-schema-and-data.sql`](src/sql/01-schema-and-data.sql) | Episode 5's tables and seed data, **unchanged copy** (a test compares it byte for byte) |
| [`src/sql/h01…h09*.sql`](src/sql) | The steps; each ends with one result set (`h01` is also run as `h10`) |
| [`src/sql/d01…d04*.sql`](src/sql) | The four orders taken between the log backups. Plain, portable `INSERT`s: the local check runs them on DuckDB too |
| [`src/dr_report.py`](src/dr_report.py) | RPO report: rows of `h01` to a verdict per database (`OK`, `AT RISK`, `NO BACKUP`, `SKIPPED`) |
| [`src/ha_lab.py`](src/ha_lab.py) | The runner: setup, steps, checks, stopwatch, `--report --rpo N`, `--reset-only`; local run on DuckDB |
| [`src/labdb.py`](src/labdb.py), [`tools/TsqlParse/`](tools/TsqlParse) | Same files as episode 8: engines, and Microsoft's T-SQL parser (ScriptDom) as a JSON CLI |
| [`expected/`](expected) | Expected result of every step (`*` = any value, for times and minutes) |
| [`tests/`](tests) | 81 pytest tests |

## Run it locally (no SQL Server needed)

```bash
pip install -r requirements.txt
python3 src/ha_lab.py                # order counts of the drill on DuckDB: match expected/
python3 -m pytest tests -q           # 81 passed
```

What runs where (Docker isn't available in the build container, so there is no SQL Server here):

- **Executed locally (DuckDB):** episode 5's seed, the four orders, the `INSERT`s and the result query of `h09`. "Ship a
  log" is **modelled** as a copy of the tables, so the counts (8, 9, 9, 11 vs 9, 11, 12, 13) are compared with
  `expected/`. That checks the lab's logic, not SQL Server's backup and restore.
- **Unit tested:** `dr_report.assess` (12 tests, one per rule).
- **Parsed by Microsoft's parser (ScriptDom, SQL Server 2022 grammar):** every `.sql` file, 0 errors, and the `RESTORE`
  that `h02` builds as text (the test evaluates its `CONCAT` and parses the result). Structure checks: every backup has
  `CHECKSUM`, `INIT` and `COMPRESSION`; every restore before the failover is `WITH STANDBY` with the undo file; the
  failover is a tail-log backup `WITH NORECOVERY` followed by a restore `WITH RECOVERY`; the repair restores the rogue log
  before the one that failed; file names match the runner; no hard-coded folders; nothing restores over the primary.
- **Runner against a fake connection:** setup order, that `h04` and `h06` must fail with the documented messages (a step
  that succeeds, or fails with another error, is a failure), the stopwatch limit, the name filter and wildcard compare of
  the RPO steps, `--report` exit codes.
- **Needs SQL Server:** `BACKUP`, `RESTORE`, `WITH STANDBY`, the errors, msdb history, the stopwatch value. That is the
  recording on CON-SQL01 ([demo.md](demo.md)). The mssql-python path was exercised up to the network in earlier episodes.

## Run it on SQL Server 2022 (CON-SQL01)

```powershell
# a login that is sysadmin on the lab VM (CREATE DATABASE, BACKUP, RESTORE, msdb history); see demo.md
$env:SQL_CONNECTION_STRING = "Server=10.50.0.30,1433;Database=master;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
py src/ha_lab.py --engine sqlserver --setup
# expect: "10/10 steps behaved as expected on sqlserver"
py src/ha_lab.py --engine sqlserver --report --rpo 15     # verdicts for every user database; exit 1 if AT RISK / NO BACKUP
py src/ha_lab.py --engine sqlserver --reset-only          # tear-down: databases and msdb history (files: see demo.md)
```

## What we learned / gotchas

- **Availability is not a backup.** Learn's business-continuity overview: availability features don't replace a tested
  backup and restore strategy. A standby faithfully copies a bad `UPDATE`, too.
- **Log shipping, in Learn's words:** it automates backing up, copying and restoring transaction logs with SQL Server Agent
  jobs; the role change is always manual; a delay in applying logs protects against human error; it is often combined
  with availability groups or failover cluster instances for disaster recovery. The lab does the cycle by hand so every
  statement is visible; it does not create the Agent jobs or the monitor.
- **One instance is a limit of this lab, not of the technique.** Both databases live on CON-SQL01, so the drill covers a
  damaged or dropped database, not a dead server. Real log shipping puts the standby on a second server and copies the
  files there. The statements are the same.
- **`WITH STANDBY` needs an undo file, and the standby is read-only.** Learn: the standby file allows read-only access
  between log restores; the next `RESTORE` deletes it automatically; if it is deleted by hand the whole database must be
  re-restored. Restoring a log needs exclusive use of the standby, which is why the runner's connection stays in `master`
  (and why an SSMS window left open on the standby will make a restore wait or fail).
- **Gotcha 1: writes on the standby fail with error 3906.** Learn lists it as "Failed to update database ... because the
  database is read-only." The standby only moves forward through log restores.
- **Gotcha 2: a log backup nobody told the shipping job about breaks the chain (error 4305).** Learn: "The log in this backup
  set begins at LSN ..., which is too recent to apply to the database. An earlier log backup that includes LSN ... can be
  restored." The fix is to restore the missing log first. Every other tool that touches the log must take `COPY_ONLY`
  backups (a copy-only log backup doesn't truncate the log or change the chain); this lab doesn't demonstrate that.
- **Tail-log backup before a planned failover.** `BACKUP LOG ... WITH NORECOVERY` backs up the log that was never
  backed up and leaves the database `RESTORING`, so no more writes can land on the old primary. Restoring that tail
  `WITH RECOVERY` on the standby is what makes the failover lossless. If the primary were gone you would recover with
  the last shipped log and lose what was not shipped: that is the RPO.
- **RTO is measured, not promised.** The runner times the whole step (tail backup, restore, result query) and fails it
  above 60 seconds. That limit is our own target for a database of a few hundred KB; it is not a Microsoft figure, and a
  real RTO also includes noticing the failure, deciding, and pointing the application at the new database.
- **The old primary is not a standby yet.** After the failover it is `RESTORING` and the log chain moved to the promoted
  copy. Re-establishing the pair (failback) is not covered here.
- **After the failover, back up the new primary.** The promoted copy has no backup history of its own, so the RPO report
  says `NO BACKUP` until it is backed up (`h10`). The report skips databases that are not `ONLINE` or that are read-only
  standbys: backups are taken from the live one.
- **SIMPLE recovery has no log backups.** The report says so, and the SQL only counts log backups when the model is not
  `SIMPLE`. `GREATEST` ignores `NULL` arguments (SQL Server 2022, compatibility level 160).
- **No hard-coded paths.** `SERVERPROPERTY('InstanceDefaultBackupPath' / 'InstanceDefaultDataPath' / 'InstanceDefaultLogPath' /
  'PathSeparator')` give the folders. `RESTORE ... MOVE` takes string literals only, so `h02` builds that one statement as text.
- **Where the other options fit** (Learn): availability groups protect a set of databases, can be synchronous or
  asynchronous, and have a listener; failover cluster instances protect the whole instance on shared storage; both are
  next episode's subject (the AG).

## References

- [Business continuity and database recovery (HA/DR overview, log shipping, AGs, FCIs)](https://learn.microsoft.com/sql/database-engine/sql-server-business-continuity-dr)
- [About log shipping](https://learn.microsoft.com/sql/database-engine/log-shipping/about-log-shipping-sql-server) and [Fail over to a log shipping secondary](https://learn.microsoft.com/sql/database-engine/log-shipping/fail-over-to-a-log-shipping-secondary-sql-server)
- [Tail-log backups](https://learn.microsoft.com/sql/relational-databases/backup-restore/tail-log-backups-sql-server) and [BACKUP (Transact-SQL)](https://learn.microsoft.com/sql/t-sql/statements/backup-transact-sql)
- [Copy-only backups](https://learn.microsoft.com/sql/relational-databases/backup-restore/copy-only-backups-sql-server)
- [RESTORE (Transact-SQL)](https://learn.microsoft.com/sql/t-sql/statements/restore-statements-transact-sql) and [RESTORE arguments (STANDBY, NORECOVERY, RECOVERY, MOVE)](https://learn.microsoft.com/sql/t-sql/statements/restore-statements-arguments-transact-sql)
- [Restore a transaction log backup](https://learn.microsoft.com/sql/relational-databases/backup-restore/restore-a-transaction-log-backup-sql-server)
- [Database Engine errors 4000 to 4999 (error 4305)](https://learn.microsoft.com/sql/relational-databases/errors-events/database-engine-events-and-errors-4000-to-4999) and [Troubleshoot common errors (error 3906)](https://learn.microsoft.com/azure/azure-sql/database/troubleshoot-common-errors-issues)
- [sys.databases (is_in_standby)](https://learn.microsoft.com/sql/relational-databases/system-catalog-views/sys-databases-transact-sql), [backupset](https://learn.microsoft.com/sql/relational-databases/system-tables/backupset-transact-sql), [restorehistory](https://learn.microsoft.com/sql/relational-databases/system-tables/restorehistory-transact-sql)
- [sp_delete_database_backuphistory](https://learn.microsoft.com/sql/relational-databases/system-stored-procedures/sp-delete-database-backuphistory-transact-sql)
- [GREATEST (Transact-SQL)](https://learn.microsoft.com/sql/t-sql/functions/logical-functions-greatest-transact-sql) and [SERVERPROPERTY](https://learn.microsoft.com/sql/t-sql/functions/serverproperty-transact-sql)
- [mssql-python driver](https://learn.microsoft.com/sql/connect/python/mssql-python/python-sql-driver-mssql-python)
- Blog: [High Availability & Disaster Recovery — Complete Guide](https://www.devladlog.com/articles/sql/2025-08-11-high-availability-disaster-recovery-complete-guide-2025/)
