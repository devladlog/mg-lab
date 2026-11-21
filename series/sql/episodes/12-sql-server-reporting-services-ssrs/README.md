# DEVLADLOG SQL #12 — SQL Server Reporting Services (SSRS)

Episode 11 loaded data into Contoso Bikes. This episode reports on it. A **paginated report** (`SalesByProduct.rdl`)
shows units, orders and revenue per product for a date range and one region, and it reaches the data only through two
stored procedures in a new schema `Rpt`. The report server connects with a SQL login, `rs_reader`, that has `EXECUTE` on
schema `Rpt` and nothing else, so a report author or a leaked data source cannot read the order tables. A PowerShell
script publishes the report through the report server web service. A new throwaway database `ContosoBikesRpt` holds
episode 5's tables (unchanged copy) and the `Rpt` objects.

**Honest limit, read this first.** There is no SQL Server and no report server in the build container, so **nothing here
has run on SQL Server or SSRS**. What is checked: every `.sql` file parses with Microsoft's T-SQL parser; the two report
queries run on DuckDB and give the numbers in `expected/`; the `.rdl` is well formed, validates against Microsoft's RDL 2016/01
schema, and its fields, parameters and procedure names agree with the SQL; the deploy script parses in PowerShell and calls
only documented methods. **Not checked until the recording (`demo.md`): that Report Builder opens the `.rdl`, that the report
server renders it, that the SOAP deploy script runs, and that `rs_reader` ends up with the rights the check expects.**

| Report | Parameters | Expected result (`expected/`) |
|---|---|---|
| `SalesByProduct` | From 2025-03-01, To 2025-04-30, Region ALL | 5 products: City Bike 4 / 3 / 2,531.10 down to Bike Lock 7 / 3 / 171.50 |
| `SalesByProduct` | same range, Region North | 4 products (no Carbon Wheelset) |
| `Regions` (drop-down) | none | ALL, Centre, North, South |
| permissions as `rs_reader` | none | EXECUTE on both procedures 1, SELECT on `Sales.Orders` and `Sales.Customers` 0 |

| Path | What it is |
|---|---|
| [`src/report/SalesByProduct.rdl`](src/report/SalesByProduct.rdl) | The report (RDL 2016/01): shared data source reference `/MGLab/ContosoBikesRpt`, datasets `SalesByProduct` and `Regions` (stored procedures), parameters `From`, `To`, `Region`, one table with a total row, page footer |
| [`src/report/build_report.py`](src/report/build_report.py) | Generates the `.rdl` from one table of fields and one of parameters, so dataset, table and query parameters cannot drift. `--check` fails if the file on disk differs |
| [`src/sql/r00-reset.sql`](src/sql/r00-reset.sql), [`00-create-database.sql`](src/sql/00-create-database.sql) | Drop and create `ContosoBikesRpt` (reset also drops the login) |
| [`src/sql/01-schema-and-data.sql`](src/sql/01-schema-and-data.sql) | Episode 5's tables and data, **unchanged copy** (a test compares it byte for byte) |
| [`src/sql/r01-report-objects.sql`](src/sql/r01-report-objects.sql) | Schema `Rpt`, `Rpt.usp_SalesByProduct`, `Rpt.usp_Regions` |
| [`src/sql/r02-reader-login.sql`](src/sql/r02-reader-login.sql) | Login and user `rs_reader`, `GRANT EXECUTE ON SCHEMA::Rpt`. The password is read from `RS_READER_PASSWORD` by the runner, never stored |
| [`src/sql/r03` to `r06`](src/sql) | What the report's datasets return for the default parameters, for North, the drop-down list, and the permission check (`EXECUTE AS USER`, `HAS_PERMS_BY_NAME`) |
| [`src/Deploy-Report.ps1`](src/Deploy-Report.ps1) | Creates folder `/MGLab`, shared data source with stored credentials, publishes the report, links it to the data source (`-Remove` deletes the folder). Windows PowerShell 5.1 |
| [`src/rpt_lab.py`](src/rpt_lab.py) | Runner: `--setup`, `--reset-only`, the four steps compared with `expected/` and with the `.rdl` fields; local run on DuckDB |
| [`src/labdb.py`](src/labdb.py), [`tools/TsqlParse/`](tools/TsqlParse) | Engines (same file as episodes 6 to 11) and Microsoft's T-SQL parser (ScriptDom) as a JSON CLI |
| [`expected/`](expected), [`tests/`](tests) | Expected results; 44 pytest tests (2 need `RDL_XSD`, see below) |

## Run it locally (no SQL Server, no report server needed)

```bash
pip install -r requirements.txt
python3 src/report/build_report.py --check   # exit 0: the .rdl is what the generator writes
python3 src/rpt_lab.py                       # DuckDB: both procedures' queries vs expected/ and the .rdl's fields
python3 -m pytest tests -q                   # 42 passed, 2 skipped (RDL_XSD not set); the ScriptDom tests build a small .NET tool the first time
RDL_XSD=/path/to/rdl2016.xsd python3 -m pytest tests/test_rdl.py -q   # 2 passed
```

The schema is not stored here. Save the XSD text from the [MS-RDL page "RDL XML Schema for Version 2016/01"](https://learn.microsoft.com/openspecs/sql_server_protocols/ms-rdl/52ce3983-2bfc-4e72-9359-42aaf5fe4509)
to a file. While building, three things in the saved copy had to be fixed before it loaded: non-breaking spaces from the
web page, the XML declaration (it sits after a comment), and an `AuthoringMetadata` element whose namespace prefix is
never bound (removed from the copy). With those fixes the `.rdl` validated, and the test also proves the check can fail.

What the local run does: takes the SELECT between `-- query-begin` and `-- query-end` in each procedure, substitutes the
parameter values the report passes, runs it on DuckDB against episode 5's data, and compares with `expected/`. It also
checks that the result's columns equal the dataset's `Field` names **read out of the `.rdl`**, in order, and that an empty
date range returns no rows with the same columns.

| | Build container (Linux, no SQL Server, no SSRS) | CON-SQL01 + report server (the recording) |
|---|---|---|
| Every `.sql` file | parsed with ScriptDom (`TSql160Parser`): 0 errors | run them |
| The two report queries | executed on DuckDB, compared with `expected/` | same numbers from SQL Server |
| `SalesByProduct.rdl` | generated, XSD-valid, fields/parameters/commands cross-checked | **open in Report Builder, publish, render: not verified** |
| `Deploy-Report.ps1` | parsed by PowerShell; method names checked against Learn; no secret in it | **first real run** |
| Permission check (r06), `CREATE LOGIN` with `CHECK_POLICY = ON` | parsed only | **first real run** |
| Runner against a fake connection | yes (setup order, password only in memory, failure detection) | the same code against the server |

If SQL Server or SSRS disagrees with an expected row, do not edit `expected/` to make it pass: find out why, write it
under "gotchas" and adjust the narration in `script.yaml`.

## What we learned / gotchas

Only things hit while building, or documented on Learn:

- **Stored credentials are one identity for every viewer.** Learn: with stored credentials "every user who runs the
  report retrieves data under the same identity, so the report can't enforce per-user data access", and "a report isn't a
  security boundary". So the *account* is the boundary: `rs_reader` gets `EXECUTE` on schema `Rpt` and no table
  rights, and a new procedure added to `Rpt` widens what the report server can run. Stored credentials are also what
  subscriptions and snapshots need, because they run with no user present.
- **SSRS is not supported on Server Core.** Learn ("Install SQL Server on Server Core", supported features): Reporting
  Services "No", Integration Services "Yes". CON-SQL01 is Server Core, so the report server goes on **CON-SRV02** (Desktop
  Experience) and its catalog database on CON-SQL01, which is a remote report server database.
- **A remote catalog database needs the right service account.** Learn: with a remote report server database use a
  domain account or a SQL Server login for the connection; a local service account is not enough, and the built-in
  Network Service needs a registered remote name on a cluster. The Configuration Manager grants the account's rights for you.
- **SSRS 2022 is the last version.** Learn (consolidation FAQ): no new SSRS versions after 2022, Power BI Report Server is
  the on-premises successor, SSRS 2022 is supported to 11 January 2033. Existing RDL reports are compatible with PBIRS.
- **Parameters in the drop-down cannot be NULL**, so "all regions" is the real value `ALL`, which the procedure tests with
  `@Region = N'ALL' OR c.Region = @Region` (a comment in `r01` says why).
- **The deploy script needs Windows PowerShell 5.1.** `New-WebServiceProxy` is not available in PowerShell 7. Learn
  documents the `ReportService2010` SOAP methods used (`CreateFolder`, `CreateDataSource`, `CreateCatalogItem`,
  `SetItemDataSources`, `DeleteItem`); native-mode paths are written `/Folder/Item`. Whether the data source name needs `.rsds` in native mode is not
  settled by the pages read (Learn mentions the extension for SharePoint mode); the script uses none and the first run will tell.
- **The REST API is left out on purpose.** The REST v2.0 JSON shapes could not be confirmed on Learn from the build
  container, so the episode uses the SOAP endpoint that Learn documents method by method.
- **Local harness:** DuckDB has no `IDENTITY(1,1)` and no cross-schema foreign keys, so the local setup swaps identity
  columns for sequences and drops `REFERENCES` (SQL Server enforces them in the lab).
- **Not verified, on purpose left open:** whether Report Builder accepts the generated `.rdl` without a repair prompt;
  how `New-WebServiceProxy` exposes the generated types and the `out Warnings` parameter (`[ref]`) on PowerShell 5.1;
  whether `Encrypt=True;TrustServerCertificate=True` in the data source's connection string is the right spelling for the
  data processing extension `SQL` (the lab certificate is self-signed; Learn recommends a trusted one); that the
  `rs_reader` password you choose satisfies the Windows password policy (the login is created with `CHECK_POLICY = ON`).

## References

- [Reporting Services consolidation FAQ (SSRS 2022 last version, supported to January 11, 2033, PBIRS)](https://learn.microsoft.com/sql/reporting-services/reporting-services-consolidation-faq?view=sql-server-ver17)
- [Install SQL Server on Server Core (supported features: Reporting Services No)](https://learn.microsoft.com/sql/database-engine/install-windows/install-sql-server-on-server-core?view=sql-server-ver17#supported-features)
- [Install and configure SQL Server Reporting Services](https://learn.microsoft.com/sql/reporting-services/install-windows/install-reporting-services?view=sql-server-ver17)
- [Credentials and connections for report data sources (stored credentials, one identity, not a security boundary)](https://learn.microsoft.com/sql/reporting-services/report-data/specify-credential-and-connection-information-for-report-data-sources?view=sql-server-ver17#specify-credentials-for-connecting-to-remote-data-sources) and [Store credentials in a Reporting Services data source](https://learn.microsoft.com/sql/reporting-services/report-data/store-credentials-in-a-reporting-services-data-source?view=sql-server-ver17)
- [Configure a report server database connection](https://learn.microsoft.com/sql/reporting-services/install-windows/configure-a-report-server-database-connection-ssrs-configuration-manager?view=sql-server-ver17) and [Configure the report server service account](https://learn.microsoft.com/sql/reporting-services/install-windows/configure-the-report-server-service-account-ssrs-configuration-manager?view=sql-server-ver17)
- [Report Definition Language (SSRS)](https://learn.microsoft.com/sql/reporting-services/reports/report-definition-language-ssrs?view=sql-server-ver17), [Plan for report design and report deployment (RDL schema versions, publishing through the SOAP API)](https://learn.microsoft.com/sql/reporting-services/plan-for-report-design-and-report-deployment-reporting-services?view=sql-server-ver17) and [MS-RDL: RDL XML Schema for Version 2016/01](https://learn.microsoft.com/openspecs/sql_server_protocols/ms-rdl/52ce3983-2bfc-4e72-9359-42aaf5fe4509)
- [ReportingService2010.CreateCatalogItem](https://learn.microsoft.com/dotnet/api/reportservice2010.reportingservice2010.createcatalogitem?view=sqlserver-2016), [CreateDataSource](https://learn.microsoft.com/dotnet/api/reportservice2010.reportingservice2010.createdatasource?view=sqlserver-2016), [SetItemDataSources](https://learn.microsoft.com/dotnet/api/reportservice2010.reportingservice2010.setitemdatasources?view=sqlserver-2016) and [Data sources and connection methods](https://learn.microsoft.com/sql/reporting-services/report-server-web-service/methods/data-sources-and-connection-methods?view=sql-server-ver17)
- [SQL Server Reporting Services features supported by editions (edition requirements for the report server database)](https://learn.microsoft.com/sql/reporting-services/reporting-services-features-supported-by-the-editions-of-sql-server?view=sql-server-ver17#edition-requirements-for-the-report-server-database)
- Blog: [SQL Server Reporting Services (SSRS) — Complete Guide](https://www.devladlog.com/articles/sql/2025-08-18-sql-server-reporting-services-ssrs-complete-guide-2025/)
