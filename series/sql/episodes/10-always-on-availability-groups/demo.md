# Demo shot list — SQL #10 Always On Availability Groups

## Lab environment

This episode needs **one new VM**. Nothing else changes: no tenant, no Azure, no licence, cost 0. Destructive steps touch only
the throwaway database `ContosoBikesAG` and the group `ag_contoso`. The cluster, witness and Always On setting are removed in
the tear-down.

| Machine | Role | OS | vCPU / RAM / disk | IP | Software |
|---|---|---|---|---|---|
| **CON-SQL01** (existing, `series/LAB.md`) | primary, cluster node 1 | Windows Server 2025 Datacenter Eval, Server Core | existing | 10.50.0.30:1433 | SQL Server 2022 Developer, mixed auth |
| **CON-SQL02** (**new**) | secondary, cluster node 2 | Windows Server 2025 Datacenter Eval, Server Core, joined to `lab.contoso.com` | 2 vCPU / 2–6 GB / 60 GB | 10.50.0.42 (range 10.50.0.40–99) | SQL Server 2022 Developer, same edition, version and **collation** as CON-SQL01, default instance, mixed auth, TCP on 1433; SQL login `lab_demo`. Add it in `lab/hyperv/lab.config.psd1` |
| **CON-SRV01** (existing) | file share witness host | existing | existing | existing | needs about 50 MB for `C:\AgWitness` |
| Cluster name `CON-AGCL01` | cluster IP | — | — | 10.50.0.44 (static, unused) | created by `Prepare-AgCluster.ps1` |
| Listener `agl-contoso` (optional) | listener IP | — | — | 10.50.0.43 (static, unused) | `a15` |
| **Recording laptop** (host, 10.50.0.1): **records everything** | runner and SSMS | Windows 11 | — | — | SSMS, Python 3.10+, Windows Terminal, `py -m pip install -r requirements.txt` here |

Sign in as the **lab Administrator** (domain account) for the PowerShell scripts, and as `lab_demo` for SSMS and the runner.
`lab_demo` needs sysadmin on both instances: `ALTER SERVER ROLE sysadmin ADD MEMBER lab_demo;` as the lab Administrator
(revert in tear-down). The recorder types every password off-screen.

## What was verified where

See the README table. **Everything that touches a second machine is "needs lab/tenant"**: cluster creation, endpoints, seeding,
error 976, failover, listener, `--watch`. Open items for the first real run: the endpoint's `connection_auth_desc`, whether
`FAILOVER` needs the poll, the service accounts (`SELECT servicename, service_account FROM sys.dm_server_services;` on
both nodes; if they run as a domain account, change the login in `a03-endpoint-sql01.sql` and `a03-endpoint-sql02.sql`),
the 60 s and 120 s limits (our own targets).

## Setup (once, before recording) — needs lab/tenant

1. Start the lab (`lab/hyperv/Start-MGLab.ps1`); build CON-SQL02 and join it to the domain; both SQL instances answer on 1433.
2. Dry run: `.\src\ps\Prepare-AgCluster.ps1 -WhatIf`, read it, then run it elevated on CON-SQL01 as the lab Administrator.
   It installs the clustering feature, runs `Test-Cluster` (read the report), creates `CON-AGCL01`, sets the witness on
   CON-SRV01, opens TCP 5022 and runs `Enable-SqlAlwaysOn` (restarts both SQL services).
3. Terminal on the laptop, in this folder (passwords off-screen):
   ```powershell
   py -m pip install -r requirements.txt
   $env:SQL_CONNECTION_STRING       = "Server=10.50.0.30,1433;Database=master;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
   $env:SQL_CONNECTION_STRING_SQL02 = "Server=10.50.0.42,1433;Database=master;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
   py src/ag_lab.py --engine sqlserver --setup
   ```
   Expected: ten steps ending `=> OK`, the verdict `AUTOMATIC FAILOVER READY` after `a05`, `a12` and `a14`, `check error:
   contains: not accessible for queries  OK` in `a08`, `step took N s (limit 60 s)` in `a12` and `a14`, and
   `10/10 steps behaved as expected on sqlserver`. It is repeatable: `--setup` starts by dropping the group and database.
4. SSMS: connect to both servers (two windows), database **master**, files `a07`, `a08`, `a09`, `a12` open.

## Screens to capture (match the `screen` scenes in script.yaml)

Run the steps by hand in SSMS or follow the runner: `--setup --step a02-prereqs --step a03-endpoints --step a04-database --step a05-create-ag`.

| Scene id | File | What must be on screen |
|---|---|---|
| `health-screen` | `screens/a07-health.jpg` | `a07-health.sql` on CON-SQL01 after seeding: two rows, PRIMARY and SECONDARY, `SYNCHRONOUS_COMMIT`, `AUTOMATIC`, `CONNECTED`, `SYNCHRONIZED`, `HEALTHY`, 0. Optional: the Always On High Availability dashboard all green |
| `gotcha-screen` | `screens/a08-error-976.jpg` | CON-SQL02, `a08-secondary-read-fails.sql`: Messages tab `Msg 976 ... not accessible for queries`; then after `a09` the same query returns 8 |
| `failover-screen` | `screens/a12-failover.jpg` | split screen: terminal `py src/ag_lab.py --engine sqlserver --step a12-failover` with `step took N s (limit 60 s)` and `=> OK` (bring the lab to the state before it with `--setup --step a02-prereqs ... --step a11-write-and-read`), SSMS on CON-SQL02 with the health grid (CON-SQL02 PRIMARY) and the order count 9; Object Explorer `ag_contoso` shows `(Primary)` |

Optional extras (not scenes): `py src/ag_lab.py --engine sqlserver --step a15-listener` (needs the CNO right to create
computer objects), and the automatic failover: `py src/ag_lab.py --engine sqlserver --watch` in one terminal, and in
another `.\src\ps\Stop-AgPrimary.ps1 -Node CON-SQL02 -WhatIf` first, then without `-WhatIf` (stops the service on the
primary for 45 s). `--watch` fails above 120 s, our own target.

## Masking

- Never show the passwords or the `$env:SQL_CONNECTION_STRING*` variables.
- Blur `10.50.0.x` addresses and the login name in SSMS, or connect through hosts-file aliases so they read `CON-SQL01`/`CON-SQL02`.
- Never show the lab's real domain or tenant; the lab domain here is `lab.contoso.com`. All names (`Alex Demo`, `Contoso Bikes`) are fictional.

## Tear-down — needs lab/tenant

1. `py src/ag_lab.py --engine sqlserver --reset-only` (drops the group and `ContosoBikesAG` on both replicas).
2. `.\src\ps\Remove-AgCluster.ps1 -WhatIf`, then run it elevated: `Disable-SqlAlwaysOn` on both (restarts SQL), removes the
   cluster and its AD objects, the witness share and the firewall rule.
3. Delete `MGLab_ContosoBikesAG_Full.bak` from CON-SQL01's backup folder (`SELECT SERVERPROPERTY(N'InstanceDefaultBackupPath');`).
4. As the lab Administrator: `ALTER SERVER ROLE sysadmin DROP MEMBER lab_demo;` on both instances if you added it; remove the
   login `CONTOSO\CON-SQL02$` / `CONTOSO\CON-SQL01$` if `a14` did not.
5. Shut CON-SQL02 down (or delete it); `Remove-Item Env:SQL_CONNECTION_STRING, Env:SQL_CONNECTION_STRING_SQL02`.
