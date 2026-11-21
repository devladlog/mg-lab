# DEVLADLOG SQL #11 — SQL Server Integration Services (SSIS)

Episodes 5 to 7 worked on Contoso Bikes' order system. This episode feeds it. A bike dealer sends a daily CSV of
sales lines; an **SSIS package** (`PartnerSalesLoad.dtsx`) reads it, splits off the rows that break a rule, lands the
rest in a staging table, and a stored procedure merges them into the new table `Sales.PartnerSales` so that **loading
the same file twice changes nothing** and a corrected line is updated, not duplicated. The package is deployed to the
SSIS catalog (`SSISDB`) on CON-SQL01, run from T-SQL three times, and each run is compared with `expected/`.
A new throwaway database `ContosoBikesEtl` holds episode 5's tables (unchanged copy) and the ETL objects.

**Honest limit, read this first.** Integration Services runs only on Windows and there is no SSIS in the build
container, so **the package has never been opened or run here**. Everything around it is built and tested (below);
the `.dtsx` itself is checked structurally (well-formed, unique ids, every reference resolving, columns and types equal
to the SQL tables, the split rule evaluated on the sample files). The first real open in Visual Studio and the first
run on CON-SQL01 happen during the recording (`demo.md`). If Visual Studio refuses the file, demo.md has the fallback.

| Run | Input | Logging | Expected (`expected/`) |
|---|---|---|---|
| 1 | `data/partner-sales-2025-05-21.csv`: 8 lines (2 break the quantity/price rule, 1 has an unknown product) | Basic (1) | succeeded, 6 staged, 3 rejected, 5 inserted, 0 updated, 5 lines, **0** rows in the data statistics |
| 2 | the same file again | Verbose (3) | succeeded, 6 staged, 3 rejected, **0 inserted, 0 updated**, still 5 lines, **8** rows sent by the source |
| 3 | `data/partner-sales-2025-05-22.csv`: 2 new lines, 1 correction (quantity 2 to 3) | Verbose (3) | succeeded, 3 staged, 0 rejected, 2 inserted, 1 updated, 7 lines |

| Path | What it is |
|---|---|
| [`src/package/PartnerSalesLoad.dtsx`](src/package/PartnerSalesLoad.dtsx) | The package (SQL Server 2022, project deployment model): Execute SQL "Prepare load", Data Flow "Load partner file" (Flat File Source, Conditional Split, OLE DB destinations "Staging table" and "Rejected rows table"), Execute SQL "Merge into Sales.PartnerSales". Parameters `InputFile`, `ServerName`; Windows authentication only |
| [`src/package/build_package.py`](src/package/build_package.py) | Generates the `.dtsx` from one table of columns, so source, split, destinations and the connection manager cannot drift apart. `--check` fails if the file on disk differs |
| [`src/sql/e00-reset.sql`](src/sql/e00-reset.sql), [`00-create-database.sql`](src/sql/00-create-database.sql) | Drop and create `ContosoBikesEtl` |
| [`src/sql/01-schema-and-data.sql`](src/sql/01-schema-and-data.sql) | Episode 5's tables and data, **unchanged copy** (a test compares it byte for byte) |
| [`src/sql/e01-etl-objects.sql`](src/sql/e01-etl-objects.sql) | `Stg.PartnerSales`, `Etl.RejectedRows`, `Etl.RunLog`, `Sales.PartnerSales`, `Etl.usp_PrepareLoad`, `Etl.usp_MergePartnerSales`. The four statements between `-- merge-begin` and `-- merge-end` are portable T-SQL that the local check runs on DuckDB |
| [`src/sql/c00` to `c04`, `c99`](src/sql) | The catalog side, run in `SSISDB`: deploy the `.ispac` (`catalog.deploy_project`), environment and reference, run (`create_execution`, `set_execution_parameter_value`, `start_execution`), results, error messages, clean-up |
| [`src/etl_lab.py`](src/etl_lab.py) | The runner: `--setup`, `--deploy`, three runs with result comparison, `--reset-only`; local run on DuckDB |
| [`src/labdb.py`](src/labdb.py), [`tools/TsqlParse/`](tools/TsqlParse) | Engines (same file as episodes 6 to 9) and Microsoft's T-SQL parser (ScriptDom) as a JSON CLI (same as episode 7) |
| [`data/`](data), [`expected/`](expected) | The two dealer files and the expected result of each run |
| [`tests/`](tests) | 51 pytest tests |

## Run it locally (no SQL Server, no SSIS needed)

```bash
pip install -r requirements.txt
python3 src/package/build_package.py --check   # exit 0: the .dtsx is what the generator writes
python3 src/etl_lab.py                         # DuckDB: data flow model + merge statements, three runs
python3 -m pytest tests -q                     # 51 passed (the ScriptDom tests build a small .NET tool the first time)
```

What the local run does: reads each CSV with the columns the `.dtsx` declares, takes the Conditional Split condition
**out of the `.dtsx`** (`Quantity > 0 && UnitPrice >= 0`) and applies it, inserts the two row sets into the staging and
rejected tables like the two destinations do, then runs the merge statements **out of the procedure's text**. Run 1 to
3 must give the numbers in `expected/` (except the two catalog-only rows: execution status and data statistics).

What runs where:

| | Build container (Linux, no Docker, no SSIS) | CON-SQL01 + Visual Studio (the recording) |
|---|---|---|
| Every `.sql` file | parsed with ScriptDom (`TSql160Parser`): 0 errors | run them |
| Merge rules and the data flow's split rule | executed on DuckDB with the sample files | the same numbers from the real package |
| `PartnerSalesLoad.dtsx` | generated, XML-checked, cross-checked against the SQL (14 tests) | **open in Visual Studio, build, deploy, run: not verified** |
| Catalog calls (`catalog.*`) | parsed; order and parameter types checked against Learn | **first real run** |
| `OPENROWSET(BULK ...)` deploy of the `.ispac`, SSISDB views | not possible here | **first real run** |
| Runner against a fake connection | yes (setup/deploy order, edited logging level and file, failure detection) | the same code against the server |

If SQL Server or SSIS disagrees with an expected row, do not edit `expected/` to make it pass: find out why, write it
under "gotchas" and adjust the narration in `script.yaml`.

## What we learned / gotchas

Only things hit while building, or documented on Learn:

- **Basic logging records no data flow row counts.** Learn: for `catalog.execution_data_statistics`, "by default, when an
  execution is started, the information about the number of rows that are sent is not logged"; the logging level must
  be **Verbose** (value 3; Basic is 1 and the default). That is why run 1 expects 0 in the last row and runs 2 and 3 expect the row counts.
- **`object_type` 50 vs 30.** Learn: 50 for execution settings such as `LOGGING_LEVEL` and `SYNCHRONIZED`, 20 for a project
  parameter, 30 for a package parameter. `SYNCHRONIZED` makes `start_execution` wait for the package.
- **An execution is started once.** Learn: it must be in the created state; to run again create a new execution (the
  runner's `c02` does).
- **OLE DB Driver 19 encrypts by default.** Learn: provider `MSOLEDBSQL19`, `Encrypt` defaults to `Mandatory`; version 19
  with a self-signed server certificate fails ("certificate chain ... not trusted") unless `TrustServerCertificate=yes`
  is in the provider string (`Trust Server Certificate=true` is the spelling for ADO/initialization strings). The lab
  package sets it and says so; Learn recommends a trusted certificate instead. The driver must be installed on every
  machine that runs the package (laptop and SSIS server).
- **SSIS install is not the designer.** Learn: installing Integration Services alone does not install the tools to
  design packages; Visual Studio plus the "SQL Server Integration Services Projects 2022" extension does. SSIS is not in
  Express; on Server Core the SSIS *server* is supported (`/FEATURES=IS`), the designer is not.
- **Dropping a project keeps versions for a while.** Learn: `catalog.delete_project` retains project versions and
  operation records until the cleanup job runs.
- **Local harness:** DuckDB has no `IDENTITY(1,1)` and no foreign keys across schemas, so the local setup replaces the
  identity columns with sequences and drops the `REFERENCES` clauses (SQL Server enforces them in the lab). The
  correlated `UPDATE ... SET col = (SELECT ...)` in the procedure exists because DuckDB has no `UPDATE ... FROM`.
- **Not verified, on purpose left open:** which Windows account reads the CSV when a package runs from the catalog
  (grant read on the folder to the SQL Server service account and to the login that starts the run, and read the
  message if the file cannot be opened); how `start_execution` reports a failed package when `SYNCHRONIZED` is set
  (the runner prints the error and lets `c03` show the status).

## References

- [Install Integration Services (SSIS)](https://learn.microsoft.com/sql/integration-services/install-windows/install-integration-services) and [Install SQL Server on Server Core (supported features, `/FEATURES=IS`)](https://learn.microsoft.com/sql/database-engine/install-windows/install-sql-server-on-server-core)
- [Install SQL Server Data Tools (SSDT): the SSIS Projects extension](https://learn.microsoft.com/sql/ssdt/download-sql-server-data-tools-ssdt) and [SSIS Projects extension for Visual Studio 2022+ troubleshooting](https://learn.microsoft.com/sql/ssdt/ssis-vs2022-troubleshooting-guide)
- [SSIS Catalog](https://learn.microsoft.com/sql/integration-services/catalog/ssis-catalog) and [Deploy Integration Services projects and packages (stored procedures, `.ispac`)](https://learn.microsoft.com/sql/integration-services/packages/deploy-integration-services-ssis-projects-and-packages)
- [catalog.create_execution](https://learn.microsoft.com/sql/integration-services/system-stored-procedures/catalog-create-execution-ssisdb-database), [catalog.set_execution_parameter_value](https://learn.microsoft.com/sql/integration-services/system-stored-procedures/catalog-set-execution-parameter-value-ssisdb-database), [catalog.start_execution](https://learn.microsoft.com/sql/integration-services/system-stored-procedures/catalog-start-execution-ssisdb-database)
- [catalog.create_environment_variable](https://learn.microsoft.com/sql/integration-services/system-stored-procedures/catalog-create-environment-variable-ssisdb-database), [catalog.create_environment_reference](https://learn.microsoft.com/sql/integration-services/system-stored-procedures/catalog-create-environment-reference-ssisdb-database), [catalog.set_object_parameter_value](https://learn.microsoft.com/sql/integration-services/system-stored-procedures/catalog-set-object-parameter-value-ssisdb-database), [catalog.delete_project](https://learn.microsoft.com/sql/integration-services/system-stored-procedures/catalog-delete-project-ssisdb-database)
- [catalog.executions](https://learn.microsoft.com/sql/integration-services/system-views/catalog-executions-ssisdb-database), [catalog.execution_data_statistics](https://learn.microsoft.com/sql/integration-services/system-views/catalog-execution-data-statistics), [catalog.event_messages](https://learn.microsoft.com/sql/integration-services/system-views/catalog-event-messages)
- [Integration Services (SSIS) logging: logging levels](https://learn.microsoft.com/sql/integration-services/performance/integration-services-ssis-logging) and [dtexec utility](https://learn.microsoft.com/sql/integration-services/packages/dtexec-utility)
- [Major version differences in MSOLEDBSQL](https://learn.microsoft.com/sql/connect/oledb/major-version-differences) and [certificate chain not trusted after upgrading to OLE DB Driver 19](https://learn.microsoft.com/troubleshoot/sql/database-engine/connect/certificate-chain-not-trusted)
- [Data flow (inputs, outputs, error outputs)](https://learn.microsoft.com/sql/integration-services/data-flow/data-flow)
- Blog: [SQL Server Integration Services (SSIS) — Complete Guide](https://www.devladlog.com/articles/sql/2025-08-15-sql-server-integration-services-ssis-complete-guide-2025/)
