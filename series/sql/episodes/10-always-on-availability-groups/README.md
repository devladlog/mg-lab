# DEVLADLOG SQL #10 — Always On Availability Groups

Episode 9 failed over by hand. This episode builds the real thing: a **two-node Windows Server Failover Cluster** and an
availability group, **`ag_contoso`**, between **CON-SQL01** (primary) and a new **CON-SQL02**, with a file share witness on
CON-SRV01. The database is a throwaway copy of episode 5's data (`ContosoBikesAG`, FULL recovery). The group uses
synchronous commit, automatic failover, automatic seeding and `DB_FAILOVER = ON`. The lab breaks it once on purpose
(reading a secondary that is not readable, error 976), fixes it, then runs a planned failover and a failback.

Docker is not available in the build container and nothing here needs it: the AG needs two Windows machines in a domain.
What could be checked without them was checked (see "What was verified where"). The cluster and the group are built in the lab.

| Step | What it shows | Expected |
|---|---|---|
| `a02` prerequisites | on each replica: Always On enabled, collation, version, quorum state, nodes up | both rows equal; `NORMAL_QUORUM`; 2 nodes up |
| `a03` endpoints | `Hadr_endpoint` on port 5022 on each instance, peer login + `CONNECT` | both `STARTED`, `ALL`, `AES` |
| `a04` database | `ContosoBikesAG`, ep05 data, the full backup the join needs | FULL, 1 full backup, 8 orders |
| `a05` create the group | `CREATE AVAILABILITY GROUP`, `JOIN` + `GRANT CREATE ANY DATABASE`, seeding; polled until synchronized | both `SYNCHRONIZED` / `HEALTHY`; verdict `AUTOMATIC FAILOVER READY` |
| `a08` gotcha | read on the secondary with `ALLOW_CONNECTIONS = NO` | error 976 |
| `a09` allow reads | `MODIFY REPLICA ... ALLOW_CONNECTIONS = ALL` on both, then read | 8 orders, `SECONDARY` |
| `a11` write and read | order 1009 on the primary, read on the secondary (redo lag, polled) | 9 orders |
| `a12` failover | `ALTER AVAILABILITY GROUP ... FAILOVER` on CON-SQL02; timed | roles swapped, synchronized |
| `a13` write on the new primary | order 1010, read on the old primary | 10 orders |
| `a14` failback | the same statement on CON-SQL01; timed | back to the `a05` state |
| `a15` listener (optional) | `ADD LISTENER` on a static IP | listener on port 1433 |

| Path | What it is |
|---|---|
| [`src/sql/a*.sql`](src/sql) | The steps, one script per action, each says on which replica it runs |
| [`src/sql/01-schema-and-data.sql`](src/sql/01-schema-and-data.sql) | Episode 5's tables and data, **unchanged copy** (a test compares it byte for byte) |
| [`src/sql/d01`, `d02`](src/sql) | The two orders taken during the drill (plain `INSERT`s, also run on DuckDB) |
| [`src/ps/`](src/ps) | `Prepare-AgCluster.ps1` (feature, cluster, witness, Always On), `Remove-AgCluster.ps1`, `Stop-AgPrimary.ps1`. All support `-WhatIf` |
| [`src/ag_health.py`](src/ag_health.py) | The health query rows to a verdict per replica (`AUTOMATIC FAILOVER READY`, `MANUAL FAILOVER READY`, `DATA LOSS POSSIBLE`, `NOT READY`, `PRIMARY`) |
| [`src/ag_lab.py`](src/ag_lab.py) | The runner: setup, steps against two connections, polling, stopwatch, `--health`, `--watch`, `--reset-only`; local run on DuckDB |
| [`src/labdb.py`](src/labdb.py), [`tools/TsqlParse/`](tools/TsqlParse) | Same files as episode 8: engines, and Microsoft's T-SQL parser (ScriptDom) as a JSON CLI |
| [`expected/`](expected) | Expected result of every step (`*` = any value) |
| [`tests/`](tests) | 109 pytest tests |

## Run it locally (no SQL Server, no cluster)

```bash
pip install -r requirements.txt
python3 src/ag_lab.py                # order counts of the drill on DuckDB: match expected/
python3 -m pytest tests -q           # 109 passed
```

The tests need Python 3.10+ and the .NET 10 SDK (they build `tools/TsqlParse`, which references Microsoft's ScriptDom).

## Run it for real (needs the lab, see demo.md)

```powershell
$env:SQL_CONNECTION_STRING      = "<connection string for CON-SQL01>"   # set it off-screen
$env:SQL_CONNECTION_STRING_SQL02 = "<connection string for CON-SQL02>"
py src/ag_lab.py --engine sqlserver --setup          # ten steps, each must end => OK
py src/ag_lab.py --engine sqlserver --health         # verdicts from the primary
py src/ag_lab.py --engine sqlserver --step a15-listener
py src/ag_lab.py --engine sqlserver --watch          # then run src/ps/Stop-AgPrimary.ps1 -Node <primary>
py src/ag_lab.py --engine sqlserver --reset-only
```

## What was verified where

| Piece | In the build container (Linux, no Docker, no SQL Server) | Needs the lab |
|---|---|---|
| T-SQL syntax of every `.sql` | ScriptDom `TSql160Parser`, 0 errors, **except** the pieces listed below | run it |
| Data logic (orders per step) | executed on DuckDB | real replication |
| Health verdicts | 14 unit tests on synthetic rows | the real `a07` rows |
| Runner (two connections, polling, stopwatch, `--watch`) | against fake connections and a fake clock | the real group |
| PowerShell scripts | parsed with the PowerShell parser; `-WhatIf` structure tested | **run them** |
| Cluster, endpoints, seeding, error 976, failover timing | not possible here | **first real run** |

**ScriptDom's TSql160 grammar does not know five things that Learn documents** for the availability-group statements:
`CLUSTER_TYPE`, `DB_FAILOVER`, `SEEDING_MODE` inside `CREATE AVAILABILITY GROUP`, `GRANT CREATE ANY DATABASE` and
`ADD LISTENER`. `tests/test_sql_structure.py` cuts exactly those pieces out (matched by pattern and counted), parses the
rest with ScriptDom, and checks the cut pieces against the documented syntax with a regex. They are verified against Learn,
not by a parser.

Things the first real run must confirm (do not edit `expected/` to make it pass; find out why, then fix `expected/` or the narration):

- `connection_auth_desc` of the endpoint is `NEGOTIATE` for `AUTHENTICATION = WINDOWS NEGOTIATE`;
- whether `ALTER AVAILABILITY GROUP ... FAILOVER` returns before the roles show as swapped (the runner polls either way);
- which account the SQL Server services run as: the logins in `a03` assume the peer connects as its computer account
  (`CONTOSO\CON-SQL0x$`). Not verified on Learn for this lab: check `sys.dm_server_services` and change the login if needed;
- the 60 s (planned failover) and 120 s (`--watch`, automatic failover as a poller sees it) limits are **our own targets**,
  not Microsoft figures.

## Gotchas (all verified on Learn, see References)

- **Error 976 on the secondary.** The default secondary role does not allow connections. Text: "The target database,
  'x', is participating in an availability group and is currently not accessible for queries. Either data movement is
  suspended or the availability replica is not enabled for read access." Fix: `MODIFY REPLICA ... SECONDARY_ROLE
  (ALLOW_CONNECTIONS = ALL)` (or `READ_ONLY`, which then needs `ApplicationIntent=ReadOnly`). Do both replicas.
- **Redo lag.** Synchronous commit hardens the log on the secondary before the commit; applying it (redo) is
  asynchronous, so a read can briefly lag. The runner polls.
- **Automatic seeding needs `GRANT CREATE ANY DATABASE`** on the secondary replica, after it joins.
- **The planned failover runs on the target secondary** and needs synchronous commit and a synchronized secondary.
  Do not fail an availability group over from Failover Cluster Manager.
- **`sys.dm_hadr_*` views need `VIEW SERVER PERFORMANCE STATE`** in SQL Server 2022.
- **Listener:** the cluster name object (CNO) needs the Create Computer objects permission on its OU, and by default can
  create only 10 virtual computer objects.
- **Witness:** the file share witness needs permissions for the CNO (Change on the share, Modify on the folder).
- **`Enable-SqlAlwaysOn` restarts the SQL Server service.** `New-Cluster` cannot run remotely without CredSSP, so
  `Prepare-AgCluster.ps1` runs on CON-SQL01. `Remove-Cluster -CleanupAD` removes the cluster's AD objects.
- **An availability group is not a backup**, and a bad `DELETE` replicates to every replica.

## References (Microsoft Learn)

- https://learn.microsoft.com/en-us/sql/database-engine/availability-groups/windows/overview-of-always-on-availability-groups-sql-server
- https://learn.microsoft.com/en-us/sql/database-engine/availability-groups/windows/prereqs-restrictions-recommendations-always-on-availability
- https://learn.microsoft.com/en-us/sql/database-engine/availability-groups/windows/availability-modes-always-on-availability-groups
- https://learn.microsoft.com/en-us/sql/database-engine/availability-groups/windows/failover-and-failover-modes-always-on-availability-groups
- https://learn.microsoft.com/en-us/sql/database-engine/availability-groups/windows/perform-a-planned-manual-failover-of-an-availability-group-sql-server
- https://learn.microsoft.com/en-us/sql/database-engine/availability-groups/windows/automatic-seeding-secondary-replicas
- https://learn.microsoft.com/en-us/sql/database-engine/availability-groups/windows/configure-read-only-access-on-an-availability-replica-sql-server
- https://learn.microsoft.com/en-us/sql/database-engine/availability-groups/windows/active-secondaries-readable-secondary-replicas-always-on-availability-groups
- https://learn.microsoft.com/en-us/sql/database-engine/availability-groups/windows/enable-and-disable-always-on-availability-groups-sql-server
- https://learn.microsoft.com/en-us/sql/t-sql/statements/create-availability-group-transact-sql
- https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-views/sys-dm-hadr-database-replica-states-transact-sql
- https://learn.microsoft.com/en-us/windows-server/failover-clustering/manage-cluster-quorum
- https://learn.microsoft.com/en-us/windows-server/failover-clustering/prestage-cluster-adds
- https://learn.microsoft.com/en-us/powershell/module/failoverclusters/new-cluster
- https://learn.microsoft.com/en-us/powershell/module/failoverclusters/remove-cluster
- https://learn.microsoft.com/en-us/powershell/module/sqlserver/enable-sqlalwayson
- Blog guide: https://www.devladlog.com/articles/sql/2025-08-22-always-on-availability-groups-complete-guide-2025/
