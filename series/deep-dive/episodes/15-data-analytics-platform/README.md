# DEVLADLOG Deep Dive #15 — Data Analytics Platform (Data Factory + ADLS Gen2 + Synapse serverless SQL + a scoring model + Power BI)

Contoso's purchase requests (episodes 3, 4, 7 and 11) now have an analytics question: **which open requests will miss the
five-day approval SLA?** The episode builds the platform that answers it, small enough to run on a free database and a pay-per-query
SQL endpoint, and every rule is plain SQL so it survives a move to Fabric.

```
Azure SQL (source)        Data Factory                  ADLS Gen2 `lake`                 Synapse serverless SQL                  Power BI Desktop
dbo.PurchaseRequests ──►  Lookup old watermark   ──►    bronze/purchase_requests/  ──►   bronze  (every row version)      ──►   Import: gold.FactPurchaseRequest
etl.Watermark             Lookup new watermark          ingest_date=D/requests-<run>      silver  (latest version + reason)        gold.DimDepartment
ModifiedOn (watermark)    Copy (> old, <= new) Parquet  .parquet                          gold    (star) + quality.CheckResult      gold.RequestRiskScore
                          Stored procedure: move mark                                     gold.RequestRiskScore (model as SQL)
                                       ▲ system-assigned managed identity, no passwords anywhere
                          python -m analytics train: reads the same silver/gold rules, fits on the past, exports coefficients as a view
```

- **Incremental by watermark, with the right upper bound.** The copy takes `ModifiedOn > old AND ModifiedOn <= new`, where *new* is
  the maximum looked up *before* the copy (never "now"). A row committed during the copy is not lost: the next run takes it. An empty
  source keeps the watermark (`COALESCE`). The watermark moves only after a successful copy. Pattern: Learn, "Incrementally load data from Azure SQL Database to Azure Blob storage".
- **Bronze keeps every version, silver keeps the latest.** Each run adds files; a request approved later appears twice in bronze.
  Silver keeps the newest version by `ModifiedOn` and gives a `RejectReason` instead of deleting bad rows; gold only reads `IsValid = 1`;
  `quality.CheckResult` counts what was kept out.
- **Serverless means views.** Learn: serverless SQL pool has no tables, no materialized views, no DML; it supports views, schemas and
  `OPENROWSET`. The only file that knows where the lake is is `sql/synapse/020-bronze.sql` (`OPENROWSET ... DATA_SOURCE = 'lake'`, Entra pass-through, no credential).
- **The model is a view.** A logistic regression on features known at submission time, split by time, exported as arithmetic into
  `gold.RequestRiskScore`. No model host, nothing to keep running. A test proves the T-SQL scores equal the Python scores to six decimals.
- **No secrets.** Factory identity to SQL and to the lake; Synapse and SQL Entra-only; shared keys off by default.

| Path | What it is |
|---|---|
| [`src/analytics/synthetic.py`](src/analytics/synthetic.py) | Fictional, deterministic request history; `snapshot` and `delta` give what the source holds at a time and what an incremental copy sees; `to_merge_sql` seeds the source |
| [`src/analytics/localsql.py`](src/analytics/localsql.py) | Runs our own Synapse T-SQL views over local parquet (sqlglot T-SQL to DuckDB). **Not Synapse**: used by tests and by training |
| [`src/analytics/ml.py`](src/analytics/ml.py) | Features, time-split training, metrics vs. a constant baseline, JSON export, T-SQL export, PSI drift |
| [`src/analytics/__main__.py`](src/analytics/__main__.py) | `seed-sql`, `make-bronze`, `train`, `export-sql`, `drift` |
| [`adf/`](adf) | Pipeline (4 activities) and the two dataset definitions, embedded into the Bicep with `loadJsonContent` |
| [`infra/main.bicep`](infra/main.bicep), [`main.bicepparam`](infra/main.bicepparam) | Storage (ADLS Gen2), SQL (free offer, Entra-only), Data Factory with its linked services/datasets/pipeline, Synapse workspace (serverless only), role assignments |
| [`sql/source/001-source-schema.sql`](sql/source/001-source-schema.sql) | Source table, `etl.Watermark`, `etl.usp_write_watermark`, least-privilege user for the factory identity |
| [`sql/synapse/`](sql/synapse) | `000` database (UTF-8 collation), `010` data source + schemas, `020` bronze, `030` ref + silver, `040` gold, `050` generated risk score, `060` quality |
| [`model/sample-model.json`](model/sample-model.json) | The model the committed `050-risk-score.sql` was generated from (synthetic data) |
| [`scripts/AnalyticsLab.psm1`](scripts/AnalyticsLab.psm1) | Ordered SQL deployment plan, `sqlcmd -G` runner with `-WhatIf`, the `az` command that pulls the bronze files |
| [`tests/`](tests) | 58 pytest tests, 12 Pester tests |

## Test locally (no Azure, no tenant)

```bash
pip install -r requirements.txt            # pandas 3.0.5, numpy 2.5.3, scikit-learn 1.9.1, duckdb 2.0.1, sqlglot 30.33.0, pytest 9.1.1
python -m pytest -q                        # 58 passed (about 20 s)
pwsh -NoProfile -c 'Invoke-Pester ./tests' # Tests Passed: 12, Failed: 0
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep    # no warnings
```

What the tests do (Docker is not available here, so SQL Server is not used; DuckDB and SQLite stand in, stated each time):
- **Pipeline** (9): the queries are read out of `adf/pipeline-incremental.json` and run on SQLite through the real activity order:
  first run copies everything, second only the changes, a re-run copies nothing and keeps the watermark, an empty source works,
  a row committed between lookup and copy is picked up next time, the pipeline's output path equals the path the bronze view reads.
- **Views** (22): every script parses as T-SQL (sqlglot); each view is the first statement of its batch (Learn: `CREATE VIEW` must be);
  only the bronze view contains `OPENROWSET`; no keys or secrets in SQL; the views run over real parquet written like Data Factory's
  output: bronze keeps all versions, silver equals the final state of every request (**a mutation to `ASC` fails the test**), the four
  injected defects get the right reasons, gold has the right cycle days and SLA flag, the weekday is Monday = 0, the monthly view adds
  up to the fact, no orphan departments, clean data gives zero errors.
- **ML** (11): no feature name mentions the outcome; time-ordered split; AUC above 0.7 and Brier below the constant baseline on the
  holdout (synthetic data); reproducible training; JSON alone reproduces the scores; **the generated T-SQL view equals Python to 1e-6**;
  the committed SQL is exactly what the committed model exports; PSI is 0 for identical data and above 0.25 when amounts double.
- **Synthetic data** (8): determinism, snapshot/delta properties, MERGE seed script parses and carries every row, defects are newer than the second load.
- **Infra and CLI** (8): `bicep build`/`lint` clean, no secrets, Entra-only, free offer, factory identity has Contributor on the lake and nothing wider,
  activities retry, `seed-sql` phases 1 to 3, train/export/drift round trip.
- **Pester** (12): plan order, sqlcmd variables equal the ones the scripts declare, `-G` and no user/password on the command line,
  `-WhatIf` runs nothing, stops at the first failure.

**What the tests cannot prove (needs the lab):** the Bicep deployment, that Data Factory can read the source and write the lake
with its managed identity, the Parquet column types Data Factory actually writes (the bronze view pins the types with `CAST`, but
this has not been seen on real files), `OPENROWSET` + Entra pass-through, the UTF-8 collation behaviour, `sqlcmd -G`, query cost, Power BI.

## Not verified in the lab yet

Everything in "needs the lab" above, in the order of the demo. Fill this in after the recording: ☐ Bicep deploys (is `allowSharedKey=false`
accepted by the Synapse workspace?) ☐ Synapse Administrator is in place for `labadmin` ☐ pipeline runs 1,089 / 145 / 0 / 4 rows
☐ views create and return data ☐ real cost for the day: ___ EUR.

## What we learned / gotchas

- **Fabric and Synapse.** Learn (Synapse runtimes page): Microsoft "has not announced the retirement of Azure Synapse Analytics" and calls
  Fabric "Microsoft's strategic platform for new analytics innovation"; several Synapse pages carry a tip that new data warehouse
  projects should start with Fabric Data Warehouse. The Synapse Link for SQL page says to use Fabric mirroring instead. We use Synapse
  serverless only for what it does cheaply, and keep logic in portable SQL.
- **Cost model.** Serverless SQL is billed on data processed; every query has a minimum of 10 MB; Parquet reads only the needed columns;
  `SELECT *` over compressed Parquet can still be expensive because intermediate results count (Learn: cost management for serverless SQL pool).
  The cost-control stored procedure `sp_set_data_processed_limit` exists (daily, weekly, monthly, in TB).
- **Owner is not data access.** Learn (access control model in ADLS): Owner, Contributor and Reader manage the account but do not give
  data access (Owner and Contributor can fetch the keys). The Bicep gives the analyst Storage Blob Data Reader and the factory Storage Blob Data Contributor.
- **Entra pass-through.** In `OPENROWSET` without a credential, an Entra user reads the files with their own identity (Learn): the person
  who queries a gold view needs a blob data role too, not just SQL permission.
- **The free database pauses.** Learn: the first connection to a paused serverless database resumes it and fails with error 40613;
  databases generally resume in under a minute. Every Lookup and the stored procedure retry 3 times a minute apart. (Not yet seen in the lab.)
- **`CREATE VIEW` must be the first statement in a batch** (Learn), so the scripts use `GO` and `sqlcmd`; Synapse Studio is for looking, not for deploying these files.
- **Weekday numbers depend on the server.** `DATEPART(weekday)` follows `DATEFIRST`; the fact computes Monday = 0 from 1 January 1900.
- **Right-censoring (our observation, visible in the tests).** Only decided requests can be labelled, so the newest weeks look better than
  reality: slow requests are still open. In the synthetic data the holdout breach rate is 16.9 % against 19.2 % in training. Leave a maturity gap in real projects.
- **PSI thresholds** (0.1 and 0.25) are an industry rule of thumb, not a Microsoft number.
- **Not built, deliberately:** Azure Machine Learning, Spark, a dedicated SQL pool and Purview (the blog's article uses them; they cost
  money and are not needed for this question), and a DAX model (episode 16).

## References

- Serverless SQL pool overview and T-SQL support: https://learn.microsoft.com/azure/synapse-analytics/sql/on-demand-workspace-overview
- Cost management for serverless SQL pool (data processed, rounding, cost control): https://learn.microsoft.com/azure/synapse-analytics/sql/data-processed
- OPENROWSET: https://learn.microsoft.com/azure/synapse-analytics/sql/develop-openrowset · Query Parquet: https://learn.microsoft.com/azure/synapse-analytics/sql/query-parquet-files
- External storage access (Entra pass-through): https://learn.microsoft.com/azure/synapse-analytics/sql/develop-storage-files-overview
- T-SQL features supported in Synapse SQL: https://learn.microsoft.com/azure/synapse-analytics/sql/overview-features
- Synapse access control: https://learn.microsoft.com/azure/synapse-analytics/security/synapse-workspace-access-control-overview · https://learn.microsoft.com/azure/synapse-analytics/security/how-to-set-up-access-control
- Synapse runtimes (no retirement announced, Fabric strategic): https://learn.microsoft.com/azure/synapse-analytics/spark/apache-spark-version-support
- Incremental load tutorial: https://learn.microsoft.com/azure/data-factory/tutorial-incremental-copy-portal
- Data Factory Azure SQL connector (managed identity): https://learn.microsoft.com/azure/data-factory/connector-azure-sql-database · ADLS Gen2: https://learn.microsoft.com/azure/data-factory/connector-azure-data-lake-storage · Parquet: https://learn.microsoft.com/azure/data-factory/format-parquet
- Serverless Azure SQL auto-pause: https://learn.microsoft.com/azure/azure-sql/database/serverless-tier-auto-pause-resume
- ADLS access control model: https://learn.microsoft.com/azure/storage/blobs/data-lake-storage-access-control-model · Built-in roles: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles
- Best practices for serverless SQL pool (import mode in Power BI): https://learn.microsoft.com/azure/synapse-analytics/sql/best-practices-serverless-sql-pool
- Power Query Azure Synapse Analytics (SQL DW) connector: https://learn.microsoft.com/power-query/connectors/azure-sql-data-warehouse
- Bicep reference, Microsoft.Synapse/workspaces: https://learn.microsoft.com/azure/templates/microsoft.synapse/workspaces
- Blog Complete Guide: https://www.devladlog.com/articles/deep-dive/2025-06-23-data-analytics-platform-synapse-power-bi-data-factory-ml/
