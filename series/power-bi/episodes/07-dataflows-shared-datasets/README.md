# DEVLADLOG Power BI #7: Dataflows & Shared Datasets

Same **Contoso Bikes** project as [episode 3](../03-power-query-m-language/) (the messy ERP exports, prepared in Power
Query), [episode 5](../05-row-level-security/) (RLS) and [episode 6](../06-dashboards-publishing/) (published, but
**not refreshable without a gateway**). This episode takes the preparation out of the Power BI file:

1. a **Dataflow Gen2** (*Contoso Bikes Prep*) reads the monthly exports from a **SharePoint** site and publishes six
   entities, so the service can refresh without a gateway
2. a **contract** (`contract.json`: entity, column names, order, types) says what the dataflow publishes, and a checker
   compares the semantic model with it
3. **one shared semantic model** (`ContosoSales`: the episode 5 measures, relationships and RLS roles) reads the dataflow
   with the *Dataflows* connector, with the workspace and dataflow IDs as parameters
4. a **thin report** (`StoreManagers`) connects to that model live: no tables, no measures, no copy
5. a PowerShell module **audits** the workspaces (duplicate models, which reports depend on the shared one, models that
   still prepare their own data) and sets the model's parameters through the REST API

| Path | What it is |
|---|---|
| [`src/dataflow/queries/`](src/dataflow/queries) | The ten M queries (`.pq`): `ExportSite` (parameter), `fnReadExport`, `fnDimension`, `SalesExport` (staging), `Product`, `Customer`, `Store`, `Date`, `Sales`, `StoreAccess`. Episode 3's queries with `SharePoint.Files` as the source; `Date` now outputs the contract's names |
| [`src/dataflow/contract.json`](src/dataflow/contract.json) | The contract: six entities, every column with its type; `from` remembers the old name |
| [`src/dataflow/ContosoBikesPrep.Dataflow/`](src/dataflow/ContosoBikesPrep.Dataflow) | **Generated**: the Dataflow Gen2 item as Fabric Git integration stores it: `mashup.pq`, `queryMetadata.json`, `.platform` |
| [`src/tools/build_dataflow.py`](src/tools/build_dataflow.py) | Queries + contract → the item folder (`--check` fails on drift) |
| [`src/tools/check_contract.py`](src/tools/check_contract.py) | `contract-check`: rules DC001-DC008 on the model's TMDL and the query files |
| [`src/pq-lint/`](src/pq-lint) | Episode 3's `pq-lint` (Microsoft's open-source Power Query parser), plus `--section` to parse a whole `mashup.pq` |
| [`src/ContosoSales.SemanticModel/`](src/ContosoSales.SemanticModel) | The shared model (TMDL): episode 5's model, partitions now read the dataflow; parameters `WorkspaceId`, `DataflowId`, `UpnDomain` |
| [`src/ContosoSales.Report/`](src/ContosoSales.Report), [`src/ContosoSales.pbip`](src/ContosoSales.pbip) | The model owner's report (two pages, bound by path), generated |
| [`src/thin-report/`](src/thin-report) | `StoreManagers.pbip` + report with a `byConnection` reference to `Contoso Data (Lab)` / `ContosoSales`, generated |
| [`src/tools/build_report.py`](src/tools/build_report.py), [`report_lint.py`](src/tools/report_lint.py) | Episode 4/5's generator (now two reports) and its lint (alt text, grid, tab order, fields exist in the model) |
| [`src/TmdlLoad/`](src/TmdlLoad) | `tmdl-load` (.NET 10, `Microsoft.AnalysisServices` 19.120.1): loads the TMDL folder with TOM and prints tables, entities, parameters, roles |
| [`src/data/ContosoBikesData/`](src/data/ContosoBikesData) | The SharePoint site's *Documents* library as the dataflow expects it: `exports/` (24 CSV + `_README.txt`, same files as episode 3) and `security/store_access.csv` |
| [`src/reference/pq_reference.py`](src/reference/pq_reference.py) | Python mirror of the queries (episode 3's, moved to SharePoint layout + contract names) → [`expected/summary.json`](src/reference/expected/summary.json), incl. what every lab user must see |
| [`src/service/PbiShared/`](src/service/PbiShared), [`Invoke-SharedModelCheck.ps1`](src/service/Invoke-SharedModelCheck.ps1) | `Get-PbiSharedModelInventory`, `Test-PbiSharedModel` (SM001-SM004), `Set-PbiModelParameter` (REST) |
| [`tests/`](tests) | pytest (dataflow item, contract, mirror, projects, schemas), Pester (`PbiShared.Tests.ps1`), vendored Microsoft schemas in `tests/schemas` (`fetch_schemas.py` re-downloads them) |

## The layers

```
SharePoint site ContosoBikesData ──▶ Dataflow Gen2 "Contoso Bikes Prep"      workspace Contoso Data (Lab)
  exports/  24 CSV                    ExportSite · fnReadExport · fnDimension · SalesExport   (not published)
  security/ store_access.csv          Product · Customer · Store · Date · Sales · StoreAccess  (the contract)
                                              │ PowerPlatform.Dataflows(null)  (WorkspaceId, DataflowId)
                                              ▼
                                      Semantic model ContosoSales + roles Store Managers / Head Office
                                              │ live connection (byConnection)
                                              ▼
                                      Thin report StoreManagers                workspace Contoso Sales (Lab)
```

| contract-check rule | Severity | Checks |
|---|---|---|
| DC001 | error | model table without a partition that reads an entity through `PowerPlatform.Dataflows` |
| DC002 | error | partition reads an entity the contract doesn't list |
| DC003 | error | `sourceColumn` that isn't a column of the entity (renamed or dropped in the dataflow) |
| DC004 | error | model data type that can't hold the contract type |
| DC005 | info | entity column the model doesn't load (today: `UserAlias`, which the model turns into the UPN) |
| DC006 | error | contract query without a `.pq` file, or a `.pq` the contract doesn't list |
| DC007 | error | entity or column name with anything but letters and digits (our naming rule, not a Microsoft one) |
| DC008 | error | workspace or dataflow ID hard-coded in a partition |

| audit rule | Severity | Reports |
|---|---|---|
| SM001 | warning | the same semantic model name in more than one workspace |
| SM002 | info | a shared model used by reports in other workspaces (thin reports), by name |
| SM003 | warning | a model in the data workspace with no upstream dataflow (it prepares its own data) |
| SM004 | warning | a report whose model is in none of the inspected workspaces |

## Run it

```bash
# 1. queries, dataflow item, mirror
cd src/pq-lint && npm ci --no-audit --no-fund && npm test      # tsc + 10 queries: 0 error(s), 0 warning(s) + mashup.pq parses (10 shared members)
cd .. && python3 tools/build_dataflow.py                       # wrote 3 files, 10 queries   (--check: matches the queries)
python3 reference/pq_reference.py                              # expected numbers -> reference/expected/summary.json

# 2. model against the contract, TOM, reports
python3 tools/check_contract.py --model ContosoSales.SemanticModel/definition
#   INFO DC005 Store Access: entity column 'UserAlias' isn't loaded ...   6 entities, 6 model tables: 0 error(s), 1 info
dotnet build TmdlLoad -m:1 -v q && dotnet TmdlLoad/bin/Debug/net10.0/tmdl-load.dll ContosoSales.SemanticModel/definition
#   6 table(s), 3 parameter(s), 5 relationship(s), 2 role(s): loaded
python3 tools/build_report.py --check                          # reports match the spec
python3 tools/report_lint.py thin-report/StoreManagers.Report --model ContosoSales.SemanticModel/definition   # 0 error(s), 0 warning(s)

# 3. tests (from the episode folder)
cd ..
python3 -m pytest tests -q                                                  # 80 passed
pwsh -NoProfile -Command "Invoke-Pester ./tests -Output Detailed"           # Tests Passed: 14, Failed: 0
```

Without `npm ci` / `dotnet build`, the tests that need `pq-lint` or `tmdl-load` are skipped (with the reason), the other
tests still run. Delete `src/pq-lint/node_modules`, `src/TmdlLoad/bin` and `obj` when done: they're gitignored.

In the lab tenant (needs sign-ins, see [demo.md](demo.md)):

```powershell
Install-Module MicrosoftPowerBIMgmt -Scope CurrentUser
Connect-PowerBIServiceAccount
./src/service/Invoke-SharedModelCheck.ps1 -DataWorkspaceId $dataWs -ReportWorkspaceId $salesWs
Import-Module ./src/service/PbiShared/PbiShared.psd1
Set-PbiModelParameter -WorkspaceId $dataWs -DatasetId $model -Parameter @{ WorkspaceId = $dataWs; DataflowId = $df } -WhatIf
```

## Expected results (`src/reference/expected/summary.json`)

| | |
|---|---|
| Entities and rows | Sales 4,071 · Date 1,096 · Product 19 · Customer 301 (incl. Unknown) · Store 5 · StoreAccess 6 |
| Sales Amount | **1,862,401.98**, Orders 2,440, Units 7,462: the same star as episode 3, from SharePoint instead of a folder |
| Gotcha: older copy of re-exported lines kept | 1,902,513.76 (episode 3's `Table.Distinct` lesson still applies in the service) |
| Sam Demo through the thin report | Contoso Madrid only, Visible stores 1, Sales amount **366,058.87**, Orders 484 |
| Alex / Riley / Taylor | 389,707.34 (Lisboa) · 1,111,159.04 (Lisboa, Online, Porto) · 385,184.07 (Paris) |
| Audit (lab) | SM001 for *ContosoSales* in both workspaces, SM002 for *StoreManagers*; SM003 depends on whether the links API lists a Gen2 dataflow (not verified) |

## What we learned / gotchas

- **Dataflow Gen1 is legacy.** Learn: Gen1 "is now in a legacy state and won't receive new feature investment"; Gen2 is
  recommended where Fabric is available, Pro/PPU customers can keep using Gen1. Since April 2026 every new Gen2 item is
  created with CI/CD and Git support, which is why this episode ships the item in the Git integration format.
- **The legacy `PowerBI.Dataflows` connector can't read a Gen2 (CI/CD) dataflow.** Consumers must use
  `PowerPlatform.Dataflows` (it has the extra `Workspaces` navigation step the model's partitions use). Learn's
  upgrade-wizard page says the same.
- **Workspace and dataflow IDs differ in every workspace**, so the model keeps them in parameters (zero GUIDs in the
  repo). Learn: *Update Parameters In Group* sets them by REST (the caller must own the model; refresh afterwards).
  `check_contract` DC008 fails a partition with a hard-coded ID.
- **Why there's no REST "publish the dataflow" script.** Learn's Gen2 public API page lists limitations: a dataflow
  defined through the API can't get a data destination, and "you can invoke Run APIs, but the actual run never succeeds".
  So the item folder is meant for Git integration (or manual paste), not for `POST .../items`.
- **Two refreshes, no cascade.** Learn: an import model "requires the semantic model to be refreshed independently of
  the dataflow". Schedule the model after the dataflow, or use the Power Automate trigger *When a dataflow refresh
  completes* to refresh it.
- **Do the merges in the dataflow.** Learn (Dataflows connector FAQ): the connector returns HTTP 429 above 1,000
  requests a minute, and the advice is to avoid nested joins that re-request dataflow data and to merge inside the
  dataflow. `Sales` gets its keys by joining the dimension queries inside the dataflow, so the model does no merges.
- **`SharePoint.Files` is one flat list of the whole site.** Learn: "Folder Path" is the absolute URL of the containing
  folder; non-English sites need `ApiVersion` 15 (we always pass 15). Our filter is a suffix test on `/exports/`, so a
  second library on the same site with an `exports` folder would be read too. Match the full path if that can happen.
- **Staging queries and *Enable load*.** `SalesExport` is referenced by five queries and isn't loaded. Learn's Gen1
  guidance warns that referencing a query with load disabled makes the engine recompute it; we haven't measured it for
  Gen2. demo.md records the refresh duration. Learn (Gen2): consume dataflow tables through the connector, never the
  staging storage directly.
- **A live connection can't change the model.** Learn: you can create report measures, calculated columns and visual
  calculations, not tables or columns. Our thin report adds none (a test checks there are no report extensions).
- **Hidden isn't secret.** Learn: hidden columns become visible to users with Build permission in a live connection.
  `Store Access` is hidden, and what protects it is the RLS role that filters the table itself. RLS is enforced on live
  connections (Learn), but workspace Contributors and above aren't restricted (episode 5): publish thin reports to a
  separate workspace and give creators Build, not membership of the data workspace.
- **A shared model can't be deleted while reports outside its workspace use it** (Learn, Build permission). SM002 lists
  them by name first.
- **The referenced-linked-entities retirement doesn't touch us.** Learn: it applies to *Power Platform* dataflows (new
  ones disabled 1 September 2026, existing ones stop 31 October 2026), not to the Dataflows connector or Power BI linked
  tables. Note the date if you use Power Apps dataflows.
- **Not verified on this machine (needs the lab tenant):** the M never ran (parser for syntax, `pq-lint` for names,
  the Python mirror for the logic, TOM for the TMDL); whether Fabric imports `ContosoBikesPrep.Dataflow` unchanged
  (demo.md step 3 has a manual fallback); whether `queryMetadata.json` keeps `allowNativeQueries: false` and the group
  layout after a round trip; whether Desktop opens the generated thin `StoreManagers.pbip`; the exact Build and Security
  dialogs; what the REST links return for a Gen2 dataflow. demo.md lists each as something to record and report.

## References
- [What are dataflows? (Gen1 legacy notice, Gen2 recommended)](https://learn.microsoft.com/power-query/dataflows/overview-dataflows-across-power-platform-dynamics-365) · [What is Dataflow Gen2? (CI/CD by default since April 2026)](https://learn.microsoft.com/fabric/data-factory/dataflows-gen2-overview) · [Dataflow Gen2 with CI/CD and Git integration](https://learn.microsoft.com/fabric/data-factory/dataflow-gen2-cicd-and-git-integration)
- [Dataflow definition (`queryMetadata.json`, `mashup.pq`, formatVersion 202502)](https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/dataflow-definition) · [Git integration source code format (`.platform`)](https://learn.microsoft.com/fabric/cicd/git-integration/source-code-format) · [Public APIs for Dataflow Gen2 (limitations)](https://learn.microsoft.com/fabric/data-factory/dataflow-gen2-public-apis)
- [Dataflows connector (`PowerPlatform.Dataflows`, 429 / 1,000 requests a minute)](https://learn.microsoft.com/power-query/connectors/dataflows) · [Migrate Gen1 to Gen2: scenarios (the navigation M, parameterize IDs, consume through the connector)](https://learn.microsoft.com/fabric/data-factory/dataflow-gen2-migrate-from-dataflow-gen1-scenarios) · [Upgrade wizard: legacy vs modern connector](https://learn.microsoft.com/fabric/data-factory/migrate-to-dataflow-gen2-using-upgrade-wizard) · [Data in Dataflow Gen2 staging items](https://learn.microsoft.com/fabric/data-factory/data-in-staging-items)
- [Configure and consume a dataflow (import needs its own refresh)](https://learn.microsoft.com/power-bi/transform-model/dataflows/dataflows-configure-consume) · [Trigger dataflows and semantic models sequentially (Power Automate)](https://learn.microsoft.com/power-query/dataflows/trigger-dataflows-and-power-bi-dataset-sequentially) · [Develop solutions with dataflows (Enable load guidance, Gen1)](https://learn.microsoft.com/power-bi/transform-model/dataflows/dataflows-develop-solutions) · [Link tables between dataflows (retirement is Power Platform only)](https://learn.microsoft.com/power-query/dataflows/linked-tables)
- [SharePoint.Files](https://learn.microsoft.com/powerquery-m/sharepoint-files) · [SharePoint folder connector](https://learn.microsoft.com/power-query/connectors/sharepoint-folder)
- [Semantic models across workspaces](https://learn.microsoft.com/power-bi/connect-data/service-datasets-across-workspaces) · [Build permission](https://learn.microsoft.com/power-bi/connect-data/service-datasets-build-permissions) · [Connect to semantic models from Desktop (live connection limits, hidden columns, RLS)](https://learn.microsoft.com/power-bi/connect-data/desktop-report-lifecycle-datasets) · [Managed self-service BI (separate workspaces)](https://learn.microsoft.com/power-bi/guidance/powerbi-implementation-planning-usage-scenario-managed-self-service-bi) · [Endorse your content](https://learn.microsoft.com/power-bi/collaborate-share/service-endorse-content)
- REST: [Get Dataset To Dataflows Links In Group](https://learn.microsoft.com/rest/api/power-bi/datasets/get-dataset-to-dataflows-links-in-group) · [Get Reports In Group](https://learn.microsoft.com/rest/api/power-bi/reports/get-reports-in-group) · [Get Dataflows](https://learn.microsoft.com/rest/api/power-bi/dataflows/get-dataflows) · [Update Parameters In Group](https://learn.microsoft.com/rest/api/power-bi/datasets/update-parameters-in-group) · [Power BI project report folder (PBIR, `byConnection`)](https://learn.microsoft.com/power-bi/developer/projects/projects-report)
- [Power Query parser (GitHub monorepo, MIT)](https://github.com/microsoft/powerquery-language-services/tree/master/packages/powerquery-parser) · [TMDL overview](https://learn.microsoft.com/analysis-services/tmdl/tmdl-overview)
- Blog: [Dataflows & Shared Datasets — Complete Guide](https://www.devladlog.com/articles/power-bi/2025-05-06-dataflows-shared-datasets-complete-guide-2025/). Note: the guide is a generic template (no dataflow, M or REST content), so this episode takes its facts from Learn and the blog should be updated from this folder.
