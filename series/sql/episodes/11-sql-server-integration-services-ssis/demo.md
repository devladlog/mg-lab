# Demo shot list — SQL #11 SQL Server Integration Services (SSIS)

## Lab environment

Everything is real: Visual Studio on the lab laptop designs and builds the package, the shared VM **CON-SQL01**
hosts the SSIS catalog and runs it. No tenant, no Azure, no licence; cost 0. The only change to a shared VM is adding
the Integration Services feature to the existing SQL Server instance (step 1) and creating `SSISDB`.

| Machine | What | Notes |
|---|---|---|
| **CON-SQL01** (`series/LAB.md`) | Windows Server 2025 Datacenter Eval, Server Core, SQL Server 2022 Developer, default instance, TCP 1433, mixed auth, 10.50.0.30, 2 vCPU / 2-6 GB | **Add**: Integration Services (shared feature) and the SSIS catalog `SSISDB`. Raise the VM to 4 GB during the recording (the catalog and `ISServerExec` need room). Install **Microsoft OLE DB Driver 19 for SQL Server** (the package uses `MSOLEDBSQL19`). Folders `C:\MGLab\ssis\` and `C:\MGLab\ssis\in\` |
| **Recording laptop** (host, 10.50.0.1) | Visual Studio 2022 (Community is fine) with the **SQL Server Integration Services Projects 2022** extension; SSMS; Python 3.10+; Windows Terminal (dark theme); **Microsoft OLE DB Driver 19 for SQL Server** | `py -m pip install -r requirements.txt` in this folder |

Login for the runner and SSMS: `lab_demo` (episode 3's demo.md), with `ALTER SERVER ROLE sysadmin ADD MEMBER lab_demo;`
for this episode (undo in tear-down). The package itself uses Windows authentication: it runs as the account that
executes it on CON-SQL01 (see "Permissions" below).

## What was verified where

See the table in README ("What runs where"). Short version: all T-SQL parsed with ScriptDom, merge rules and split rule
executed on DuckDB, package structure cross-checked; **the package, the catalog calls and the `.ispac` deploy have never run**.
Expect to fix small things on the first real run, and record what you fix in README "gotchas". If SQL Server or SSIS
disagrees with `expected/`, do not edit `expected/` to match: find out why.

## Setup (once, before recording; dry-run everything)

1. **Add SSIS to CON-SQL01** (console or PowerShell remoting as the lab Administrator; SQL Server 2022 Developer media
   mounted as `D:`). Learn: on Server Core Setup runs in quiet mode and unattended runs must pass the licence switch;
   `IS` installs all Integration Services components:
   `D:\setup.exe /QS /ACTION=Install /FEATURES=IS /IACCEPTSQLSERVERLICENSETERMS`
   (check the options against "Install SQL Server from the command prompt" before running). Then the OLE DB Driver 19 installer.
2. **Create the catalog.** SSMS on the laptop, connect to CON-SQL01 as `lab_demo`: Object Explorer, **Integration
   Services Catalogs**, right-click, **Create Catalog**; tick CLR if asked, set a catalog password (type it off-screen,
   keep it only in your password manager). Confirm `SSISDB` appears.
3. **Self-signed certificate:** the package sets `TrustServerCertificate=yes` for this lab (README gotchas). Nothing to do.
4. **Files on CON-SQL01** (from the laptop, as the lab Administrator, over the admin share or PowerShell remoting):
   copy `data\partner-sales-2025-05-21.csv` and `data\partner-sales-2025-05-22.csv` to `C:\MGLab\ssis\in\`.
   Give **Read** on `C:\MGLab\ssis\` to the SQL Server service account (and, if a run says the file cannot be opened,
   to the login that starts the execution: which account reads the file is not verified, see README).
5. **Database and objects** (terminal on the laptop, in this folder; password typed off-screen):
   ```powershell
   py -m pip install -r requirements.txt
   $env:SQL_CONNECTION_STRING = "Server=10.50.0.30,1433;Database=master;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
   py src/etl_lab.py --engine sqlserver --setup --skip-runs
   ```
   Expected: `setup: ContosoBikesEtl created with episode 5's tables and the ETL objects`, then it stops.
6. **Visual Studio:** New project, **Integration Services Project**, name `PartnerSalesProject`, project deployment model,
   target server version SQL Server 2022. Delete the empty `Package.dtsx`. **Add > Existing Item**
   `src\package\PartnerSalesLoad.dtsx` (copy it into the project). Open it: the designer must show the three tasks and the
   data flow. For design-time preview set the parameter `ServerName` to `10.50.0.30` (do not save that value into the repo copy).
   **Fallback if Visual Studio refuses or repairs the file:** build the same package in the designer (Execute SQL
   Task with an expression on `SqlStatementSource` calling `Etl.usp_PrepareLoad`; Data Flow Task: Flat File Source on
   the CSV with the seven columns of `build_package.py`, Conditional Split with output `Valid rows` = `Quantity > 0 && UnitPrice >= 0`
   and default output `Rejected rows`, two OLE DB destinations with fast load into `Stg.PartnerSales` and
   `Etl.RejectedRows`; Execute SQL Task calling `Etl.usp_MergePartnerSales`; parameters `InputFile`, `ServerName`; OLE DB
   connection `ContosoBikesEtl` with `Provider=MSOLEDBSQL19`), save it over `src\package\PartnerSalesLoad.dtsx` and change
   `build_package.py` and `tests/test_package.py` to describe what the designer wrote.
7. **Build** the project (Build > Build Solution). Copy `bin\<configuration>\PartnerSalesProject.ispac` to
   `C:\MGLab\ssis\` on CON-SQL01.
8. **Deploy and run the whole thing once:** `py src/etl_lab.py --engine sqlserver --setup --deploy`. Expected: the c00 and
   c01 result grids, three runs ending `=> OK`, `3/3 runs behaved as expected on sqlserver`. Repeatable (`--setup` drops
   the database first; the catalog project is overwritten by `c00`).

## Screens to capture (match the `screen` scenes in script.yaml)

Run the steps by hand in SSMS for the screens that need a particular state. Start clean: `--setup --skip-runs`, then open `c00` and `c01` in SSMS and run them yourself
(or `--deploy --skip-runs`).

| Scene id | File | What must be on screen |
|---|---|---|
| `designer-screen` | `screens/ssis-designer.jpg` | Visual Studio, `PartnerSalesLoad.dtsx`: Control Flow (three tasks, green arrows), then the Data Flow tab (Flat File Source, Conditional Split, two OLE DB destinations), Package Parameters tab (`InputFile`, `ServerName`). Mask the machine name and user in the title bar |
| `deploy-screen` | `screens/ssis-catalog.jpg` | SSMS Object Explorer: Integration Services Catalogs, SSISDB, MGLab, Projects, PartnerSalesProject, Packages, `PartnerSalesLoad.dtsx`, Environments, Lab; the `c00` grid (`MGLab`, `PartnerSalesProject`, `PartnerSalesLoad.dtsx`); the `c01` grid (`Lab`, `ServerName`, `localhost`) |
| `basic-screen` | `screens/ssis-run1.jpg` | after `c02-run-package.sql` with `@LoggingLevel = 1` and the 21 May file: `c03-results.sql` grid (Succeeded, 6, 3, 5, 0, 5, **0**); second tab `SELECT * FROM Etl.RejectedRows` with three rows and their reasons |
| `gotcha-screen` | `screens/ssis-run2-verbose.jpg` | edit `c02` to `@LoggingLevel = 3`, same file, run; `c03` grid (Succeeded, 6, 3, **0, 0**, 5, **8**); keep the run-1 grid beside it so the 0 and the 8 can be compared. Optional: `SELECT ... FROM SSISDB.catalog.execution_data_statistics` for the same execution |
| `correction-screen` | `screens/ssis-run3.jpg` | `c02` with `@LoggingLevel = 3` and `@InputFile` set to the 22 May file; `c03` grid (Succeeded, 3, 0, 2, 1, 7, 3); then `SELECT Qty, LoadedRunLogId FROM Sales.PartnerSales WHERE PartnerOrderRef = 'PO-77001' AND LineNumber = 1` returning `3`, `3` |

Optional extras for the narration: SSMS standard report **All Executions** (right-click `SSISDB`, Reports) after run 3;
`c04-errors.sql` after a deliberately failed run (point `@InputFile` at a file that does not exist) to show the
OnError messages; the three `code` scenes can be shown from VS Code on the laptop.

## Permissions (to check on the first run)

- The runner/SSMS login needs rights in `SSISDB` (sysadmin is simplest in the lab).
- Reading `C:\MGLab\ssis\in\*.csv` and connecting to `localhost` with Windows authentication happen under the account
  that runs the package on CON-SQL01. If a run fails with a file or login error, read `c04-errors.sql`, grant the right
  to that account (a login for it in `ContosoBikesEtl` with `db_datareader`, `db_datawriter` and `EXECUTE` on schemas `Etl` and `Stg` is enough),
  and write the account and fix into README "gotchas".

## Masking

- Never show the password, the catalog password or `$env:SQL_CONNECTION_STRING`.
- Blur `10.50.0.30` and the login name in SSMS and Visual Studio (title bar, status bar, Object Explorer, parameter
  values), or connect through a hosts-file alias so it reads `CON-SQL01`.
- All names (`Alex Demo`, `Contoso Bikes`, dealer codes `DLR-N01`, order refs `PO-77001`) are fictional.

## Tear-down

1. `py src/etl_lab.py --engine sqlserver --reset-only` (runs `c99-catalog-cleanup.sql`: project, environment, folder
   `MGLab` removed from the catalog; then `e00-reset.sql` drops `ContosoBikesEtl`).
2. On CON-SQL01 delete `C:\MGLab\ssis\` (the `.ispac` and the two CSV files).
3. `SSISDB` and the Integration Services feature stay installed unless you want them gone (the catalog can be deleted
   in SSMS; project versions and operation records linger until the SSISDB cleanup job runs). Set the VM memory back to 2 GB.
4. As the lab Administrator: `ALTER SERVER ROLE sysadmin DROP MEMBER lab_demo;`; remove any login/permission added under
   "Permissions". `Remove-Item Env:SQL_CONNECTION_STRING` in the terminal.
