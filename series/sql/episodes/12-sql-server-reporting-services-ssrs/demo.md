# Demo shot list — SQL #12 SQL Server Reporting Services (SSRS)

## Lab environment

Everything is real: the shared VM **CON-SQL01** hosts the data, the report server catalog and the SQL login; a Desktop
Experience server hosts the report server; the laptop authors the report and records. No tenant, no Azure, no licence;
cost 0. Reporting Services is **not supported on Server Core** (Learn, "Install SQL Server on Server Core"), and CON-SQL01
is Server Core, so the report server goes on an existing GUI VM.

| Machine | What | Notes |
|---|---|---|
| **CON-SQL01** (`series/LAB.md`) | Windows Server 2025 Datacenter Eval, Server Core, SQL Server 2022 Developer, default instance, TCP 1433, mixed auth, 10.50.0.30, 2 vCPU / 2-6 GB | Hosts `ContosoBikesRpt` (throwaway), the login `rs_reader`, and the report server catalog databases `ReportServer` and `ReportServerTempDB` (remote report server database). Nothing is installed on it |
| **CON-SRV02** (`series/LAB.md`) | Windows Server 2025 Datacenter Eval, Desktop Experience, domain member, 10.50.0.22, 2 vCPU / 2-3 GB | **Add**: SQL Server 2022 Reporting Services (SSRS), native mode, choose the Developer edition in the installer. Raise the VM to 4 GB during the recording (SSRS service plus the web portal) |
| **Recording laptop** (host, 10.50.0.1) | Windows with Microsoft Report Builder, SSMS, a browser, Windows PowerShell 5.1, Python 3.10+, Windows Terminal (dark theme) | `py -m pip install -r requirements.txt` in this folder |

Login for the runner and SSMS: `lab_demo` (episode 3's demo.md), with `ALTER SERVER ROLE sysadmin ADD MEMBER lab_demo;`
for this episode (undo in tear-down).

## What was verified where

See the table in README ("What runs where"). Short version: all T-SQL parsed with ScriptDom, both report queries executed on
DuckDB, the `.rdl` XSD-valid and cross-checked; **the `.rdl` in Report Builder, the SSRS install, the SOAP publish, and
the permission check have never run**. Expect small fixes on the first real run and record them in README "gotchas". If SQL
Server or SSRS disagrees with `expected/`, do not edit `expected/` to match: find out why.

## Setup (once, before recording; dry-run everything)

1. **Install SSRS on CON-SRV02** (console or RDP as the lab Administrator). Download the SQL Server 2022 Reporting Services
   installer from the link on Learn's "Install and configure SQL Server Reporting Services" page, run it, choose the
   Developer edition (no key). Do not record the installer.
2. **Report Server Configuration Manager** (on CON-SRV02): connect to the instance; **Service Account**: Virtual Service
   Account is the default (README: with a remote database use a domain account or a SQL login for the *database
   connection*). **Database > Change Database > Create a new report server database** on `CON-SQL01`; on the
   credentials page choose **SQL Server Credentials** with `lab_demo` for this setup step only (type it off-screen), or
   **Service Credentials** after creating a login for `CONTOSO\CON-SRV02$` on CON-SQL01 (the Configuration Manager then grants
   the rights). Which of the two works first time is not verified here: write it in README "gotchas". **Web Service URL**:
   Apply (default `http://CON-SRV02:80/ReportServer`). **Web Portal URL**: Apply (`http://CON-SRV02:80/Reports`).
   Open the portal in a browser on the laptop: it must show an empty Home.
3. **Database and objects** (terminal on the laptop, in this folder; passwords typed off-screen):
   ```powershell
   py -m pip install -r requirements.txt
   $env:SQL_CONNECTION_STRING = "Server=10.50.0.30,1433;Database=master;UID=lab_demo;PWD=<password>;Encrypt=yes;TrustServerCertificate=yes"
   $env:RS_READER_PASSWORD = Read-Host "rs_reader password (a strong one: CHECK_POLICY is ON)"
   py src/rpt_lab.py --engine sqlserver --setup
   ```
   Expected: `setup: ContosoBikesRpt created ...`, `setup: login rs_reader created ...`, the four steps ending `=> OK`, and
   `4/4 steps behaved as expected on sqlserver`.
4. **Report Builder** on the laptop: open `src\report\SalesByProduct.rdl`. Expect it to open without a repair prompt. The
   shared data source `/MGLab/ContosoBikesRpt` does not exist yet (step 5), so do not preview here. **Fallback if
   Report Builder refuses the file:** build the same report by hand (data source ContosoBikesRpt; dataset `SalesByProduct`
   with query type Stored Procedure `Rpt.usp_SalesByProduct` and parameters From, To, Region; dataset `Regions` with
   `Rpt.usp_Regions` feeding the Region parameter's available values; a table with Product, Units sold, Orders, Revenue and
   a Total row), save over `src\report\SalesByProduct.rdl`, and change `build_report.py` and the tests to describe what
   Report Builder wrote.
5. **Publish** (Windows PowerShell 5.1, not `pwsh`; the same two environment variables; run as an account with rights on the
   report server, e.g. the lab Administrator via `runas`, since the script uses the current Windows credentials):
   ```powershell
   cd src
   .\Deploy-Report.ps1
   ```
   Expected: `Published: http://CON-SRV02/Reports/report/MGLab/SalesByProduct`. Repeat it: it must succeed again. The
   web service URL and server names are parameters (`-ReportServer`, `-SqlServer`).
6. **Dry run in the portal:** open the report, defaults: From 2025-03-01, To 2025-04-30, Region (All regions). Five rows,
   City Bike 4 / 3 / 2,531.10 first. Compare with `r03` in SSMS. Pick North: four rows.

## Screens to capture (match the `screen` scenes in script.yaml)

| Image | Scene | What the frame shows |
|---|---|---|
| `screens/ssrs-report-builder.jpg` | builder-screen | Report Builder, Design view of `SalesByProduct.rdl`; Report Data pane open (Parameters, Data Sources, Datasets); Properties pane on dataset `SalesByProduct` showing Query Type Stored Procedure |
| `screens/ssrs-portal-report.jpg` | portal-screen | Web portal, `MGLab / SalesByProduct`, default parameters, the five-row result and the footer |
| `screens/ssrs-portal-north.jpg` | north-screen | Region drop-down open, then North selected and the four-row result with the subtitle ending `| North` |
| `screens/ssrs-permissions.jpg` | gotcha-screen | SSMS, `r06-permissions-check.sql` result grid: 1, 1, 0, 0 |

Record the code scenes (procedure, login, report XML, deploy script, test) from the files in `src/` in VS Code, not from slides.

## Permissions (to check on the first run)

- The runner/SSMS login needs `ALTER ANY LOGIN` and database creation (sysadmin is simplest in the lab).
- The publisher needs rights on the report server: by default only local administrators on CON-SRV02 can create
  folders and data sources at the root. If `CreateFolder` returns an `rsAccessDenied` fault, add the account as a
  **Content Manager** in the portal (Settings > Security) and write it in README "gotchas".
- `rs_reader` must run both procedures and read no table: `r06` shows it. If a row differs, fix the grant, never
  `expected/`.

## Masking

- Never show `$env:RS_READER_PASSWORD`, `$env:SQL_CONNECTION_STRING`, the database credentials page of the Configuration
  Manager, or the data source's password field in the portal (it is masked, keep it closed).
- Blur `10.50.0.30` and `10.50.0.22` and the login name in SSMS, or use host aliases so it reads `CON-SQL01` and `CON-SRV02`.
- All names (`Contoso Bikes`, region names, product names) are fictional.

## Tear-down

1. `.\Deploy-Report.ps1 -Remove` from Windows PowerShell 5.1 (deletes folder `/MGLab` with the data source and report).
2. `py src/rpt_lab.py --engine sqlserver --reset-only` (drops `ContosoBikesRpt` and the login `rs_reader`).
3. SSRS and its catalog stay installed on CON-SRV02 / CON-SQL01 unless you want them gone (uninstall from Apps; drop
   `ReportServer` and `ReportServerTempDB` on CON-SQL01). Set the VM memory back to 2 GB.
4. As the lab Administrator: `ALTER SERVER ROLE sysadmin DROP MEMBER lab_demo;`; remove any login/permission added under
   "Permissions". `Remove-Item Env:SQL_CONNECTION_STRING, Env:RS_READER_PASSWORD` in the terminal.
