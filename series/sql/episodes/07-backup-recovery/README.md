# DEVLADLOG SQL #7 — Backup & Recovery

Episode 5 built an order system, episode 6 locked it down. This episode answers the question that comes after
every incident: **can you get the data back, and have you ever tried?** A new throwaway database,
`ContosoBikesBackup` (episode 5's tables and data, **FULL recovery model**), gets a full, a differential and two
log backups. Then somebody runs `UPDATE Sales.Products SET ListPrice = 0;` (no `WHERE`), a legitimate order arrives
after it, and we restore the chain **into a copy**, stopped just before the accident, check it, and repair the
live database from the copy. Every step prints one result set that is compared with `expected/`.

| Step | What it shows | Expected |
|---|---|---|
| `b01` the gotcha | `BACKUP LOG` on a FULL-recovery database that has never had a full backup | error 4214, "no current database backup" |
| `b02` full backup | `WITH INIT, CHECKSUM, COMPRESSION`, to the instance's default backup folder | msdb: `Full`, `FULL`, checksums 1, copy-only 0 |
| `b03` differential | `WITH DIFFERENTIAL` after two more orders (`d01`) | `Differential`, `FULL`, 1, 0 |
| `b04` log backup | after one more order (`d02`); starts the point-in-time capability | `Log`, `FULL`, 1, 0 |
| `b05` the accident | a note of the time (`dbo.RecoveryMarks`), the `UPDATE` without `WHERE`, order 1012, a second log backup | 5 products at price 0, 12 orders |
| `b06` restore into a copy | full, differential, log 1, log 2: all `NORECOVERY`, `CHECKSUM` and the same `STOPAT`; then `RESTORE ... WITH RECOVERY`. Afterwards the planner must pick the same four files | copy `ONLINE`, 0 products at price 0, 11 orders, order 1012 absent |
| `b07` verify and repair | `DBCC CHECKDB` on the copy, `RESTORE VERIFYONLY ... WITH CHECKSUM`, then the live prices are set from the copy | 0 free products, 5 prices equal to the copy, **12 orders** (1012 kept) |

| Path | What it is |
|---|---|
| [`src/sql/00-create-database.sql`](src/sql/00-create-database.sql), [`b00-reset.sql`](src/sql/b00-reset.sql) | Create `ContosoBikesBackup` in FULL recovery; reset = drop both databases and delete their msdb backup history |
| [`src/sql/01-schema-and-data.sql`](src/sql/01-schema-and-data.sql) | Episode 5's tables and seed data, **unchanged copy** (a test compares it byte for byte) |
| [`src/sql/b01…b07*.sql`](src/sql) | The seven steps; `b02`–`b07` end with one result set |
| [`src/sql/d01`, `d02`](src/sql) | The orders taken between backups. Plain, portable `INSERT`s: the local check runs them on DuckDB too |
| [`src/sql/msdb-history.sql`](src/sql/msdb-history.sql) | The backup history of the lab database, the input of the planner |
| [`src/restore_plan.py`](src/restore_plan.py) | Restore planner: msdb rows + target time to the `RESTORE` statements (rules below) |
| [`src/backup_lab.py`](src/backup_lab.py) | The runner: setup, steps, checks, the planner check, `--plan`, `--reset-only`; local run on DuckDB |
| [`src/labdb.py`](src/labdb.py), [`tools/TsqlParse/`](tools/TsqlParse) | Same files as episode 6: engines, and Microsoft's T-SQL parser (ScriptDom) as a JSON CLI |
| [`expected/`](expected) | Expected result of every step with a result set |
| [`tests/`](tests) | 76 pytest tests |

The planner's rules, all from Learn: start from the most recent full backup that finished before the target (a
copy-only backup is never a base); then the most recent differential taken after it (and before the next full);
then every log backup in order up to and including the first one that reaches the target; every statement
`NORECOVERY` with the same `STOPAT`, and a separate final `RECOVERY`. A log backup that starts after the previous
backup ends is a gap and an error; a target after the last log backup is a warning (Learn: the database stays
unrecovered).

## Run it locally (no SQL Server needed)

```bash
pip install -r requirements.txt
python3 src/backup_lab.py            # data model on DuckDB: counts match expected/
python3 -m pytest tests -q           # 76 passed
```

What runs where (Docker isn't available in the build container, so there is no SQL Server here):

- **Executed locally (DuckDB):** the data statements of the lab: the seed, the orders of `d01`/`d02`, the accident
  (`UPDATE` without `WHERE`), order 1012 and the repair `UPDATE` from `b07`, with the result queries of `b05` and
  `b07`. "Restore to the mark" is **modelled** as a copy of the tables taken at the mark; the counts that come out
  (5 free products, 12 orders live, 11 orders in the copy, order 1012 absent, 5 prices repaired, 12 orders after the
  repair) are compared with `expected/`. That checks the lab's logic, not SQL Server's restore.
- **Planner:** 16 unit tests on synthetic msdb rows (one per rule: most recent differential only, differential of the
  next full excluded, copy-only ignored, older full when the target is earlier, log gap, target after the last log...).
- **Parsed by Microsoft's parser (ScriptDom, SQL Server 2022 grammar):** every `.sql` file, 0 errors. Also the five
  `RESTORE` statements that `b06` builds as text (the test evaluates its `CONCAT`s and parses the result) and the
  planner's output. Structure checks: every backup has `CHECKSUM` and `INIT`, the restore chain is `NORECOVERY` with the
  same `STOPAT` and one final `RECOVERY`, no hard-coded folders, the file names in the restore match the backups and
  the runner, the `UPDATE` really has no `WHERE`, the mark is written before the accident and the last log backup comes
  after it, nothing ever restores over `ContosoBikesBackup`.
- **Runner against a fake connection:** setup order, that `b01` must fail with the documented message (a `b01` that
  succeeds, or fails with another error, is a failure), result comparison, and the planner check (a planner that
  disagrees with the SQL fails `b06`).
- **Needs SQL Server:** `BACKUP`, `RESTORE`, msdb history, `DBCC CHECKDB`. That is the recording on CON-SQL01
  ([demo.md](demo.md)). The mssql-python path was exercised up to the network in earlier episodes (no server here).

## Run it on SQL Server 2022 (CON-SQL01)

```powershell
# a login that is sysadmin on the lab VM (BACKUP/RESTORE, CREATE DATABASE, msdb history); see demo.md
$env:SQL_CONNECTION_STRING = "Server=10.50.0.30,1433;Database=master;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
py src/backup_lab.py --engine sqlserver --setup
# expect: "7/7 steps behaved as expected on sqlserver" and "planner picked: ...Full.bak -> ...Diff.bak -> ...Log1.trn -> ...Log2.trn"
py src/backup_lab.py --engine sqlserver --plan           # the planner's RESTORE statements for the lab's incident
py src/backup_lab.py --engine sqlserver --reset-only     # tear-down: databases and msdb history (files: see demo.md)
```

## What we learned / gotchas

- **FULL recovery does nothing until the first full backup.** `b01`: `BACKUP LOG` on a new FULL database fails with
  error 4214 (Learn: "BACKUP LOG cannot be performed because there is no current database backup"). Learn's BACKUP
  page: before you can create the first log backup, you must create a full backup.
- **A differential needs its base.** At restore time you restore the full backup, then only the most recent
  differential; a copy-only full backup can't be a base (the differential bitmap isn't updated), and
  `COPY_ONLY` is ignored if combined with `DIFFERENTIAL`.
- **Same `STOPAT` in every `RESTORE LOG`.** Learn: a specified time is always restored from a log backup, and you
  must give an identical `STOPAT` in every `RESTORE LOG` of the sequence; the full backup's end point must be earlier
  than the target. The recovery point is the latest commit at or before the time. The runner takes the time from a mark
  written right before the accident; in a real incident you read it from the application log or the user's report.
- **`NORECOVERY` all the way, then `RECOVERY` on its own.** Learn's best practice. Recover too early and you can't
  apply more logs without restarting the whole sequence. If `STOPAT` is after the last log backup, the database is
  left unrecovered (the planner warns about this).
- **Restore into a copy.** The live database stays online, so no tail-log backup is needed, and the repair takes only
  what's wrong (prices) while keeping what's right (order 1012). Overwriting live with the restored database would
  have lost that order. The copy's files are named after the copy (`MOVE`), because a restore would otherwise try to
  reuse the live files' paths.
- **`MOVE` takes string literals.** RESTORE's syntax in Learn shows `MOVE 'logical_file_name_in_backup' TO
  'operating_system_file_name'`, so `b06` builds each statement as text from the instance's folders. The logical
  names are `ContosoBikesBackup` and `ContosoBikesBackup_log` because the database was created with defaults; if you
  are unsure, `RESTORE FILELISTONLY` lists them.
- **No hard-coded paths.** `SERVERPROPERTY('InstanceDefaultBackupPath')` (SQL Server 2019 and later),
  `InstanceDefaultDataPath`, `InstanceDefaultLogPath` and `PathSeparator` give the folders; the scripts add a
  trailing separator if the value has none.
- **`CHECKSUM` and `VERIFYONLY` have limits.** Without `CHECKSUM` a backup is only checksummed if compressed (Learn:
  the default except for compressed backups); a failed page checksum stops the backup by default. Learn on
  `RESTORE VERIFYONLY`: it checks that the backup is intact and readable, and does not verify the structure of the
  data in it. That is why `b07` also runs `DBCC CHECKDB` on the restored copy, and why the real proof is a restore.
- **Backup history lives in msdb.** The planner reads `msdb.dbo.backupset` (type `D`/`I`/`L`, LSNs, copy-only flag) and
  `backupmediafamily` (file name). Back up msdb too (Learn). `sp_delete_database_backuphistory` removes a
  database's history but "the physical backup files are preserved": the lab's `.bak` and `.trn` files stay on
  CON-SQL01 until you delete them (demo.md, tear-down).
- **A `GETDATE()` mark is a `datetime`.** `STOPAT` takes a `datetime` (or `char`/`varchar`); the statement text uses
  the ISO 8601 form with a `T` (style 126), which `datetime` reads the same whatever `SET DATEFORMAT` is.
- **Local harness:** DuckDB has no `UPDATE ... FROM` with the target's alias, so the repair is written with
  correlated subqueries (valid T-SQL too). `copy` is a keyword in DuckDB, so the alias is `rec`.

## References

- [BACKUP (Transact-SQL): first log backup needs a full backup, COPY_ONLY, CHECKSUM](https://learn.microsoft.com/sql/t-sql/statements/backup-transact-sql)
- [MSSQLSERVER_4214 (BACKUP LOG before a full backup)](https://learn.microsoft.com/sql/relational-databases/errors-events/mssqlserver-4214-database-engine-error)
- [Recovery models](https://learn.microsoft.com/sql/relational-databases/backup-restore/recovery-models-sql-server) and [Differential backups](https://learn.microsoft.com/sql/relational-databases/backup-restore/differential-backups-sql-server)
- [Restore a database to a point in time (full recovery model)](https://learn.microsoft.com/sql/relational-databases/backup-restore/restore-a-sql-server-database-to-a-point-in-time-full-recovery-model) and [RESTORE arguments (STOPAT, NORECOVERY, CHECKSUM)](https://learn.microsoft.com/sql/t-sql/statements/restore-statements-arguments-transact-sql)
- [RESTORE statements (MOVE)](https://learn.microsoft.com/sql/t-sql/statements/restore-statements-transact-sql), [Apply transaction log backups](https://learn.microsoft.com/sql/relational-databases/backup-restore/apply-transaction-log-backups-sql-server), [Plan and perform restore sequences](https://learn.microsoft.com/sql/relational-databases/backup-restore/plan-and-perform-restore-sequences-full-recovery-model)
- [backupset (msdb)](https://learn.microsoft.com/sql/relational-databases/system-tables/backupset-transact-sql) and [Backup history and header information (verification, msdb)](https://learn.microsoft.com/sql/relational-databases/backup-restore/backup-history-and-header-information-sql-server)
- [sp_delete_database_backuphistory](https://learn.microsoft.com/sql/relational-databases/system-stored-procedures/sp-delete-database-backuphistory-transact-sql)
- [Enable or disable backup checksums](https://learn.microsoft.com/sql/relational-databases/backup-restore/enable-or-disable-backup-checksums-during-backup-or-restore-sql-server) and [Possible media errors during backup and restore](https://learn.microsoft.com/sql/relational-databases/backup-restore/possible-media-errors-during-backup-and-restore-sql-server)
- [SERVERPROPERTY (InstanceDefaultBackupPath, InstanceDefaultDataPath, PathSeparator)](https://learn.microsoft.com/sql/t-sql/functions/serverproperty-transact-sql)
- [mssql-python driver](https://learn.microsoft.com/sql/connect/python/mssql-python/python-sql-driver-mssql-python)
- Blog: [Backup & Recovery — Complete Guide](https://www.devladlog.com/articles/sql/2025-08-07-backup-recovery-complete-guide-2025/)
