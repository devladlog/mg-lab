# Demo shot list — SQL #9 High Availability & Disaster Recovery

## Lab environment

Everything runs on the shared lab VM **CON-SQL01** (SQL Server 2022 Developer). No new VM, no tenant, no Azure, no
licence, cost 0. Two small throwaway databases (`ContosoBikesHA`, `ContosoBikesHA_Standby`, a few MB each), five backup
files and one undo file. Both databases live on the same instance, so this episode demonstrates the log-shipping
mechanics (backup, restore, chain, tail-log failover) and does **not** protect against losing the server: say so on
camera (the `scope` scene does). Nothing shared is restored over: only the two throwaway databases are touched.

| Machine | Role | OS | vCPU / RAM / disk | IP | Software |
|---|---|---|---|---|---|
| **CON-SQL01** (existing, `series/LAB.md`) | the primary and the standby | Windows Server 2025 Datacenter Eval, Server Core | 2 vCPU / 2–6 GB, existing disk; needs about 100 MB free on the system drive | 10.50.0.30:1433 | SQL Server 2022 Developer, default instance, mixed auth. Backup compression is available in Developer edition |
| **Recording laptop** (host, 10.50.0.1): **records everything** | runs the runner and SSMS | Windows 11 | — | — | SSMS (current), Python 3.10+, Windows Terminal (dark theme), `py -m pip install -r requirements.txt` in this folder |

Login: `lab_demo`, the SQL login from episode 3's demo.md. This episode needs **server-level** rights (`CREATE DATABASE`,
`BACKUP`, `RESTORE`, the msdb history procedure). On the lab VM: `ALTER SERVER ROLE sysadmin ADD MEMBER lab_demo;` run as
the lab Administrator (undo it in tear-down step 3). The SQL Server service account writes the backup files.

## What was verified where

| Step | Verified in the build container (Linux, no Docker) | Needs CON-SQL01 (the recording) |
|---|---|---|
| Every `.sql` file | parsed with Microsoft's ScriptDom (`TSql160Parser`): 0 errors; the `RESTORE` built by `h02` parsed too; structure checks | **run them** |
| Data logic: orders 1009–1013, counts per step | yes: executed on DuckDB; "ship a log" modelled as a table copy | the same counts from real log restores |
| RPO report rules | 12 unit tests on synthetic rows | **h01 and h10 tables, then `--report`** |
| `BACKUP`, `RESTORE ... WITH STANDBY`, tail-log backup, errors 3906 and 4305, msdb rows, the stopwatch | not possible here | **first real run**: every step must say OK |
| Runner against a fake connection | yes (setup order, both expected errors, limit, filter, wildcard) | — |

If SQL Server disagrees with an expected row, **don't edit `expected/` to make it pass**: find out why (Messages tab in
SSMS), write it in README "gotchas", and adjust the narration in `script.yaml`. Most likely to need a look on the first
real run:

- the exact text and number of the errors in `h04` (3906) and `h06` (4305): the runner only checks for "database is
  read-only" and "too recent to apply";
- that an SSMS window left open on `ContosoBikesHA_Standby` (even just Object Explorer expanded with a query window) can
  make `RESTORE LOG` wait: keep query windows in `master` while running the steps;
- the logical file names `ContosoBikesHA` and `ContosoBikesHA_log` (`RESTORE FILELISTONLY FROM DISK = '<full backup>'`
  shows them);
- whether `BACKUP LOG ... WITH NORECOVERY` in `h08` needs the SSMS sessions in the primary closed;
- the time the failover step reports (the limit of 60 seconds is our own target, not a Microsoft figure).

## Setup (once, before recording)

1. Start the lab (`lab/hyperv/Start-MGLab.ps1`); check CON-SQL01 answers on 10.50.0.30:1433.
2. Terminal on the laptop, in this folder (password typed off-screen):
   ```powershell
   py -m pip install -r requirements.txt
   $env:SQL_CONNECTION_STRING = "Server=10.50.0.30,1433;Database=master;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
   py src/ha_lab.py --engine sqlserver --setup
   ```
   Expected: the setup line, `ran d01-order-1009.sql` before `h03`, `ran d02` before `h05`, `ran d03` before `h06`, `ran d04`
   before `h08`, `check error: contains: database is read-only  OK` in `h04`, `check error: contains: too recent to apply  OK`
   in `h06`, `step took N s (limit 60 s)` in `h08`, ten steps ending `=> OK`, the RPO verdict blocks after `h01` and `h10`, and
   `10/10 steps behaved as expected on sqlserver`. Dry-run it; it is repeatable (`--setup` starts with `h00-reset.sql`,
   which drops both databases and deletes their msdb history; `INIT` overwrites the old backup files).
3. SSMS: connect to CON-SQL01 as `lab_demo`, **database master**. Open `h01`…`h09*.sql` and the four `d0*.sql` files.

## Screens to capture (match the `screen` scenes in script.yaml)

The steps build on each other and change the server, so capture them **while running the steps by hand in SSMS**, in this
order, starting from `py src/ha_lab.py --engine sqlserver --step h01-rpo-before --setup` (reset, create, seed, report
before any backup). For every step, run the `.sql` file in SSMS; each `d0*` file is run first with `ContosoBikesHA` selected
as the database (then switch the window back to `master`): `h02`, `d01`, `h03` (screen 1), `h04`, `d02`, `h05`, `d03`, `h06`
(screen 2), `h07`, `d04`, `h08` (screen 3), `h09`, then the report (screen 4).

| Scene id | File | What must be on screen |
|---|---|---|
| `standby-screen` | `screens/h03-standby-readable.jpg` | after `h02`, `d01`, `h03`: grid `Orders on the primary` 9, `Orders on the standby` 9, `Log backups restored on the standby` 1; Object Explorer refreshed: `ContosoBikesHA_Standby` with `(Standby / Read-Only)` |
| `gotcha-screen` | `screens/h06-chain-broken.jpg` | after `d02`, `h05`, `d03`, `h06-ship-log-fails.sql`: Messages tab `Msg 4305 ... too recent to apply ... An earlier log backup that includes LSN ... can be restored.` and `RESTORE LOG is terminating abnormally.`; grid 11 / 9 / 1 |
| `failover-screen` | `screens/h08-failover.jpg` | split screen: terminal running `py src/ha_lab.py --engine sqlserver --step h08-failover` with `step took N s (limit 60 s)` and `=> OK` (needs the state before `h08`: see the note below the table); SSMS with `h08` grid `RESTORING`, `ONLINE`, 12, 1; Object Explorer: `ContosoBikesHA (Restoring...)` |
| `rpo-screen` | `screens/h10-rpo-after.jpg` | terminal: `py src/ha_lab.py --engine sqlserver --report --rpo 15`: `ContosoBikesHA SKIPPED`, `ContosoBikesHA_Standby NO BACKUP` |

Optional inset for the `readonly` code scene: before `h04`, show the error in the Messages tab (`Msg 3906 ... database is
read-only`). To confirm the whole thing once more before recording: `--setup` again (all ten steps OK).

The failover screen needs the state just before `h08`. In a separate pass, bring the lab there with the runner and stop:
`py src/ha_lab.py --engine sqlserver --setup --step h02-init-standby --step h03-ship-log --step h04-standby-write --step h05-rogue-log-backup --step h06-ship-log-fails --step h07-repair-chain`
(the steps run in file order; `--setup` first resets everything), then record `py src/ha_lab.py --engine sqlserver --step h08-failover`,
which runs `d04` and then the failover while the camera is on.

## Masking

- Never show the password or `$env:SQL_CONNECTION_STRING`.
- Blur `10.50.0.30` and the login name in SSMS (title bar, status bar, Object Explorer), or connect through a hosts-file alias so
  it reads `CON-SQL01`.
- BACKUP and RESTORE messages show the full path of the backup folder on the VM (default instance folder): the lab VM, not a
  client path; blur it if you prefer.
- All names (`Alex Demo`, `Contoso Bikes`, `@contoso.com`) are fictional.

## Tear-down

1. `py src/ha_lab.py --engine sqlserver --reset-only` (drops both databases, deletes their msdb history). Check in SSMS:
   `SELECT name FROM sys.databases WHERE name LIKE N'ContosoBikesHA%';` returns nothing.
2. Delete the files SQL Server never deletes. Read the folders with `SELECT SERVERPROPERTY(N'InstanceDefaultBackupPath'),
   SERVERPROPERTY(N'InstanceDefaultDataPath');` then on CON-SQL01 (console or PowerShell remoting) remove
   `MGLab_ContosoBikesHA_*.bak` and `MGLab_ContosoBikesHA_*.trn` from the backup folder (Full, Log1, Rogue, Log2, Tail) and
   `MGLab_ContosoBikesHA_Standby.undo` (and any leftover `MGLab_ContosoBikesHA_Standby*.mdf` / `.ldf`) from the data and log
   folders.
3. As the lab Administrator: `ALTER SERVER ROLE sysadmin DROP MEMBER lab_demo;` (if you added it for this episode).
4. `Remove-Item Env:SQL_CONNECTION_STRING` in the terminal.
