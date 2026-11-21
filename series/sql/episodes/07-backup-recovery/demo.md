# Demo shot list — SQL #7 Backup & Recovery

## Lab environment

Everything runs on the shared lab VM **CON-SQL01** (SQL Server 2022 Developer). Two small throwaway databases
(`ContosoBikesBackup`, `ContosoBikesRecovered`, a few MB each) and four backup files in the instance's default backup
folder. No tenant, no Azure, no licence, cost 0. Restores happen only into the throwaway copy; no shared database
is restored over.

| Machine | What | Notes |
|---|---|---|
| **CON-SQL01** (existing, `series/LAB.md`) | Windows Server 2025 Datacenter Eval, Server Core, SQL Server 2022 Developer, default instance, TCP 1433, mixed auth, 10.50.0.30, 2 vCPU / 2–6 GB | Needs ~100 MB free on the system drive (data files + backups). Backup compression is available in Developer edition |
| **Recording laptop** (host, 10.50.0.1) | SSMS (any current version), Python 3.10+, Windows Terminal (dark theme) | `py -m pip install -r requirements.txt` in this folder |

Login: `lab_demo`, the SQL login from episode 3's demo.md (create it as described there if it doesn't exist). This
episode needs **server-level** rights: `CREATE DATABASE`, `BACKUP`, `RESTORE` and the msdb history procedure.
On the lab VM the simple way is `ALTER SERVER ROLE sysadmin ADD MEMBER lab_demo;` (run as the lab Administrator,
and undo it in tear-down step 3). The SQL Server service account writes the backup files, so no folder permission is
needed beyond SQL Server's own default backup folder.

## What was verified where

| Step | Verified in the build container (Linux, no Docker) | Needs CON-SQL01 (the recording) |
|---|---|---|
| Every `.sql` file | parsed with Microsoft's ScriptDom (`TSql160Parser`): 0 errors; the five `RESTORE` statements built by `b06` and the planner's output parsed too; structure checks | **run them** |
| Data logic: orders, the accident, the repair, counts in `b05`, `b06` (counts), `b07` | yes: executed on DuckDB; restore modelled as a copy of the tables at the mark | the same counts from the real restore |
| Restore planner | 16 unit tests on synthetic msdb rows | **planner check after `b06` must print the four files** and say OK |
| `BACKUP`, `RESTORE`, msdb rows, error 4214, `DBCC CHECKDB`, `RESTORE VERIFYONLY` | not possible here | **first real run**: every step must say OK |
| Runner against a fake connection | yes (setup order, expected failure of `b01`, planner check) | — |

If SQL Server disagrees with an expected row, **don't edit `expected/` to make it pass**: find out why (Messages tab
in SSMS), write it in README "gotchas", and adjust the narration in `script.yaml`. Things most likely to need a look
on the first real run: the exact message and number of the `b01` error; the logical file names `ContosoBikesBackup`
and `ContosoBikesBackup_log` (`RESTORE FILELISTONLY FROM DISK = '<full backup>'` shows them); whether
`SERVERPROPERTY('InstanceDefaultBackupPath')` returns a value on this instance (it is documented for SQL Server
2019 and later); that the msdb columns the planner reads (`first_lsn`, `last_lsn`) behave as the planner assumes.

## Setup (once, before recording)

1. Start the lab (`lab/hyperv/Start-MGLab.ps1`); check CON-SQL01 answers on 10.50.0.30:1433.
2. Terminal on the laptop, in this folder (password typed off-screen):
   ```powershell
   py -m pip install -r requirements.txt
   $env:SQL_CONNECTION_STRING = "Server=10.50.0.30,1433;Database=master;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
   py src/backup_lab.py --engine sqlserver --setup
   ```
   Expected: the setup line, `ran d01-orders-after-full.sql` before `b03`, `ran d02-order-after-diff.sql` before `b04`,
   `b01` with `check error: contains: no current database backup  OK`, seven steps ending `=> OK`, the line
   `planner picked: ...Full.bak -> ...Diff.bak -> ...Log1.trn -> ...Log2.trn` and
   `7/7 steps behaved as expected on sqlserver`. Dry-run it; it is repeatable (`--setup` starts with `b00-reset.sql`,
   which drops both databases and deletes their msdb history; the `INIT` option overwrites the old backup files).
3. SSMS: connect to CON-SQL01 as `lab_demo`. Open the `b0*.sql` files and `msdb-history.sql`.

## Screens to capture (match the `screen` scenes in script.yaml)

The steps build on each other and each one changes the server, so capture them **while running the steps by hand in
SSMS**, in this order. Start from a clean state: `py src/backup_lab.py --engine sqlserver --step b01-log-before-full --setup`
(reset, create, seed, run `b01` only). Then, for every step below, run the `.sql` file in SSMS (the data files `d01`
before `b03` and `d02` before `b04` are run in SSMS too, with `ContosoBikesBackup` selected as the database):

| Scene id | File | What must be on screen |
|---|---|---|
| `gotcha-screen` | `screens/b01-log-before-full.jpg` | `b01-log-before-full.sql` in a query window (the `BACKUP LOG` line visible); Messages tab: `Msg 4214 ... BACKUP LOG cannot be performed because there is no current database backup.` and `BACKUP LOG is terminating abnormally.` |
| `history-screen` | `screens/b04-backup-history.jpg` | after running `b02`, `d01`, `b03`, `d02`, `b04` in that order: `msdb-history.sql` grid with three rows `D`, `I`, `L`, their LSNs, `is_copy_only` 0 and the three file names |
| `restore-screen` | `screens/b06-restore-copy.jpg` | after `b05-incident.sql` (it takes ~5 seconds because of the `WAITFOR`s): `b06-restore-copy.sql`; Messages tab with the four RESTORE progress blocks; grid with `Recovered copy state / ONLINE`, `0`, `11`, `0`; Object Explorer refreshed showing both databases |
| `repair-screen` | `screens/b07-verify-and-repair.jpg` | `b07-verify-and-repair.sql` (all batches); Messages: `The backup set on file 1 is valid.` and `(5 rows affected)`; grid `0`, `5`, `12` |

Optional inset for the `incident` code scene: before `b05`, run `SELECT ProductName, ListPrice FROM Sales.Products;`
and after it again, to show every price at 0.00. Also optional: after `b06`, run
`py src/backup_lab.py --engine sqlserver --plan` in the terminal to show the planner's statements next to the SQL.

To confirm the whole thing end to end once more before recording: `--setup` again (all seven steps OK).

## Masking

- Never show the password or `$env:SQL_CONNECTION_STRING`.
- Blur `10.50.0.30` and the login name in SSMS (title bar, status bar, Object Explorer), or connect through a
  hosts-file alias so it reads `CON-SQL01`.
- The messages from BACKUP and RESTORE show the full path of the backup folder on the VM (default instance folder
  under `C:\Program Files\Microsoft SQL Server\...`): that is the lab VM, not a client path, but blur it if you prefer.
- All names (`Alex Demo`, `Contoso Bikes`, `@contoso.com`) are fictional.

## Tear-down

1. `py src/backup_lab.py --engine sqlserver --reset-only` (drops `ContosoBikesBackup` and `ContosoBikesRecovered`, deletes
   their msdb backup history). Check in SSMS: `SELECT name FROM sys.databases WHERE name LIKE N'ContosoBikes%';`
   returns nothing from this episode (episodes 3–6 databases, if still there, are listed).
2. Delete the backup files. SQL Server never deletes them. Read the folder with
   `SELECT SERVERPROPERTY(N'InstanceDefaultBackupPath');` in SSMS, then on CON-SQL01 (console or PowerShell remoting)
   remove `MGLab_ContosoBikes*.bak` and `MGLab_ContosoBikes*.trn` from that folder (four files: Full, Diff, Log1, Log2;
   `b01`'s Log0 file is never created because that backup fails). If a restore was interrupted, also remove
   any leftover `MGLab_ContosoBikesRecovered*.mdf` and `.ldf` from the data and log folders (a normal `DROP DATABASE`
   removes them).
3. As the lab Administrator: `ALTER SERVER ROLE sysadmin DROP MEMBER lab_demo;` (if you added it for this episode).
4. `Remove-Item Env:SQL_CONNECTION_STRING` in the terminal.
