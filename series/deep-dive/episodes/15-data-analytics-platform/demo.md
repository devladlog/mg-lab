# Demo shot list — DEVLADLOG Deep Dive #15, Data Analytics Platform

Code and test scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs tenant + Azure subscription** for everything on screen. Offline (container, no Azure): 58 pytest tests and
12 Pester tests pass, `bicep build` and `bicep lint` are clean. **Not yet run against Azure:** the Bicep deployment, the Data
Factory pipeline, the Synapse scripts, `sqlcmd -G`, the files Data Factory writes (Parquet types), Power BI. Record the outcome
of each in the README ("Not verified in the lab yet").

## Lab environment

Recorded on the **lab Windows laptop** (host): Edge (Azure portal, Data Factory Studio), Windows Terminal with PowerShell 7,
**SSMS** (Microsoft Entra MFA), **Power BI Desktop**. No Hyper-V VM is needed: everything lives in Azure. Nothing from
`series/LAB.md` is consumed except the Azure subscription and `labadmin`.

**Local tools on the laptop:** Azure CLI (`az`), Python 3.13 with `pip install -r requirements.txt` (pandas, numpy, scikit-learn,
duckdb, sqlglot), `sqlcmd` (go-sqlcmd; the script uses `-G`, check `sqlcmd --version` and that `-G` signs in with Microsoft Entra
on this build), SSMS, Power BI Desktop, PowerShell 7, Bicep CLI, the repo checked out.

**Azure** (lab subscription, one resource group `rg-mglab-deep-dive-15`, West Europe)

| Resource | SKU | Estimated cost for the recording window |
|---|---|---|
| Storage account `stan<suffix>` (ADLS Gen2, hierarchical namespace, LRS, Hot), containers `lake` and `synapse` | Standard LRS | cents: a few MB stored (not measured yet) |
| Azure SQL logical server `sql-an-<suffix>` (Entra-only) | no charge for the server | 0 |
| Azure SQL database `sourcedb` | General Purpose serverless Gen5 2 vCores, **free offer** (`useFreeLimit`, `AutoPause`) | 0 within the monthly allowance (Learn: free offer); max 10 free databases per subscription: check none is left from episodes 3 or 11 |
| Data Factory `adf-an-<suffix>` (V2), 1 pipeline, 3 runs, Azure integration runtime | pay per activity run and copy time | cents (not measured yet; check the Data Factory pricing page on the day) |
| Synapse workspace `syn-an-<suffix>`, **serverless SQL only** (no dedicated pool, no Spark pool) | serverless: billed per data processed, minimum 10 MB per query (Learn) | cents: the whole dataset is under 1 MB of Parquet |
| Power BI Desktop | free | 0 |

No Spark pool, no dedicated SQL pool, no Azure Machine Learning, no Purview, no Application Insights. Expected total for one
recording: **well under 1 EUR** (estimate; confirm in Cost Management afterwards). The budget alert `mglab-monthly` (30 EUR) stays active.
Add a Synapse cost-control limit as a belt and braces: in the endpoint, `sp_set_data_processed_limit @type = N'daily', @limit_tb = 1`
(Learn: serverless cost control).

**Microsoft Entra:** only `labadmin` (recording account, Owner of the subscription). No other lab user is needed. Lab users have no
departments set; this episode does not need them.

## Setup (off camera)

1. **Tests first**
   ```bash
   cd series/deep-dive/episodes/15-data-analytics-platform
   python -m pytest -q                         # expect 58 passed
   pwsh -NoProfile -c 'Invoke-Pester ./tests'  # expect Tests Passed: 12
   bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep
   ```
2. **Deploy** (as `labadmin`; `az login` off camera, never on screen)
   ```powershell
   az provider register -n Microsoft.Synapse; az provider register -n Microsoft.DataFactory   # first use in the subscription
   az group create -n rg-mglab-deep-dive-15 -l westeurope
   $me = az ad signed-in-user show --query "{upn:userPrincipalName,oid:id}" -o json | ConvertFrom-Json
   $ip = (Invoke-RestMethod https://api.ipify.org)
   az deployment group create -g rg-mglab-deep-dive-15 -f infra/main.bicep `
       -p adminLogin=$($me.upn) adminObjectId=$($me.oid) clientIp=$ip --query properties.outputs
   ```
   Note the outputs: storage account, SQL server FQDN, factory name, serverless endpoint. If the Synapse workspace deployment
   rejects the storage account because shared keys are off, redeploy with `-p allowSharedKey=true` and say so in the recording notes.
3. **Synapse access.** Learn: the workspace creator is the Microsoft Entra admin and Synapse Administrators get `db_owner` on the
   serverless pool. The Bicep sets the Entra admin; open Synapse Studio > Manage > Access control and confirm `labadmin` is **Synapse
   Administrator**; add it if not. Storage: `labadmin` has **Storage Blob Data Reader** from the Bicep (role assignments can take a few minutes).
4. **Source schema** (the factory's managed identity gets its database user):
   ```powershell
   Import-Module ./scripts/AnalyticsLab.psm1
   $src = Get-AnalyticsSqlPlan -Target Source -FactoryName <adf name>
   Invoke-AnalyticsSql -Server <sql fqdn> -Plan $src -WhatIf    # shows what will run
   Invoke-AnalyticsSql -Server <sql fqdn> -Plan $src
   ```
5. **Seed the source, phase 1** (1,089 rows). Do **not** run the pipeline yet: its first run is the first recorded screen.
   ```powershell
   $env:PYTHONPATH = "src"; python -m analytics seed-sql --phase 1 --out $env:TEMP\phase1.sql
   sqlcmd -S <sql fqdn> -d sourcedb -G -b -i $env:TEMP\phase1.sql        # MERGE statements, 1,089 rows
   ```
6. **Synapse objects** (as `labadmin`):
   ```powershell
   $syn = Get-AnalyticsSqlPlan -Target Synapse -StorageAccount <storage>
   Invoke-AnalyticsSql -Server <workspace>-ondemand.sql.azuresynapse.net -Plan $syn
   ```
   The views exist before any file does; querying them fails until the first pipeline run lands Parquet files: that is expected.

## Screens to capture

Capture order = script order. Every screen shows the real service; the synthetic data is stated on screen once.

| Scene | What must be on screen | Steps |
|---|---|---|
| `adf-screen` | ADF Studio Monitor: three runs of `pl_incremental_purchase_requests` with Copy details **1,089 / 145 / 0 rows read**; then the lake container with `bronze/purchase_requests/ingest_date=<day>/requests-<run id>.parquet` (three files) | (a) Author tab: show the pipeline once (four activities). (b) Trigger now (Debug is fine). Show success + rows read 1,089 (details icon on the Copy activity). (c) Off camera cut: run phase 2 (`seed-sql --phase 2`, same sqlcmd line), trigger again, show 145 rows read. (d) Trigger again with nothing new: 0 rows read. (e) Portal > storage account > Containers > lake > the folder. **Mask** the factory name, storage account name and subscription id (`pipeline/mask.js`). |
| `quality-screen` | SSMS on the serverless endpoint, database `contoso_analytics`: `SELECT * FROM quality.CheckResult`, then `SELECT * FROM sys.dm_external_data_processed` | Run phase 3 (`seed-sql --phase 3`, four bad rows) and the pipeline once more (rows read 4). Connect with Microsoft Entra MFA as `labadmin`. Expect: `bronze row versions` > `distinct requests`, four `rejected: ...` rows (NonPositiveAmount, UnknownDepartment, ApprovedBeforeSubmitted, UnknownStatus). Mask the server name in the connection dialog and tab titles. |
| `score-screen` | Terminal: `az storage blob download-batch` (Entra login), `python -m analytics train`, `export-sql`; SSMS: top 10 open requests by `BreachProbability` | `$p = Get-LakePullCommand -StorageAccount <storage> -Destination $env:TEMP\lake; Invoke-Expression $p`; `python -m analytics train --lake $env:TEMP\lake --model $env:TEMP\model.json` (prints version and metrics: `auc_test`, `brier_test` below `brier_baseline_constant`); `python -m analytics export-sql --model $env:TEMP\model.json --out sql\synapse\050-risk-score.sql`; deploy it with `Get-AnalyticsSqlPlan ... -IncludeRiskScore` (re-running everything is idempotent: `CREATE OR ALTER`). Then the SELECT TOP 10. Say on screen that the data is synthetic. Revert `050-risk-score.sql` with `git checkout` afterwards. **Run `python -m analytics drift` too** and read the PSI aloud if there is time (stable, about 0.02). |
| `powerbi-screen` | Power BI Desktop: Get data > Azure Synapse Analytics SQL, Import, Navigator with the three gold views, two visuals | Server = the `-ondemand` endpoint, database `contoso_analytics`, **Import**, sign in with the Microsoft account (labadmin). Tick `gold.FactPurchaseRequest`, `gold.DimDepartment`, `gold.RequestRiskScore`. Relationship FactPurchaseRequest[DepartmentKey] to DimDepartment[DepartmentKey] (many to one). Visuals: clustered bar, Average of CycleDays by DepartmentName; table of RequestId, Amount, BreachProbability filtered to Status = Submitted, sorted descending. No DAX is written in this episode (episode 16 does the model). Do not publish. Mask the server name in Data source settings. |

## Tear-down

1. `az group delete -n rg-mglab-deep-dive-15 --yes --no-wait` (deletes storage, factory, SQL, and the workspace with its managed resource group).
2. Confirm in the portal: the resource group is gone and no `*-managed*` resource group for the Synapse workspace is left.
3. Close Power BI Desktop **without saving** a `.pbix` (it holds the endpoint name), clear its data source credentials
   (File > Options and settings > Data source settings), delete `$env:TEMP\lake`, `model.json`, `phase*.sql`, and
   `git checkout sql/synapse/050-risk-score.sql`.
4. Check Cost Management for the day and write the real figure in the README.
