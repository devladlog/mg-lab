# DEVLADLOG Deep Dive #14 — Enterprise Data Lakehouse (Databricks + Synapse + Power BI)

Series: DEVLADLOG Deep Dive. Blog guide: <https://www.devladlog.com/articles/deep-dive/2026-03-16-enterprise-data-lakehouse-azure-synapse-databricks-power-bi-purview/>.
Same fictional Contoso as the other episodes: an order system emits a change feed (insert, update, delete) and finance wants dashboards. Episode 15
(data analytics platform) covers Data Factory, Synapse SQL and ML; this one is only the Delta lake and its three consumers.

## What this episode builds

```
 landing/*.jsonl ──► Databricks (PySpark) ──► ADLS Gen2, Delta ──► Synapse serverless SQL ──► Power BI (import)
  change feed        bronze → silver → gold    bronze/ silver/ gold/   views (OPENROWSET, DELTA)   TMDL semantic model
                     quarantine for bad rows        ▲
                                                    └── lakehouse/contract.py: single source of truth for gold columns
```

| Piece | Where | Runs where |
|---|---|---|
| Medallion pipeline (CDC `MERGE`, quality rules, PII hashing, gold) | `src/lakehouse/medallion.py`, `contract.py` | **here, for real**: open-source Spark 4.0.1 + Delta 4.0.1; the same functions run in a Databricks notebook |
| Fictional data generator and local runner | `src/lakehouse/datagen.py`, `run_local.py` | here |
| Databricks notebook (calls `run_batch`) | `src/databricks/medallion_job.py` | **needs a Databricks workspace** |
| Unity Catalog row filter and column mask | `src/databricks/uc_governance.sql` | **needs a Unity Catalog workspace** (syntax parsed and checked against Learn, never executed) |
| Synapse serverless views | `src/synapse/serving.sql` | **needs a Synapse workspace** (parsed as T-SQL; columns checked against the contract) |
| Power BI semantic model (TMDL) | `src/powerbi/Contoso.SemanticModel/definition/` | **needs Power BI Desktop** (structure checked; never opened in Desktop) |
| Landing zone: ADLS Gen2, Databricks, access connector, Synapse | `infra/main.bicep` | `bicep build` and `lint` clean; **never deployed** |

Docker is not available in the build environment and none is needed: Spark and Delta run in-process, and the Synapse "reader" is emulated (see the tests).

## Test locally (no Azure, no tenant)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt            # pyspark 4.0.1, delta-spark 4.0.1, pytest, sqlglot  (needs Java 17+)
pytest                                      # expect: 23 passed (about 4 minutes on a shared 2-core box)
PYTHONPATH=src python -m lakehouse.run_local ./lake-demo     # three generated batches, prints gold and quarantine counts
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep
```

Result when written: `23 passed` (9 pipeline tests in `tests/test_medallion.py`, 14 contract/drift tests in `tests/test_contract_drift.py`);
`bicep build` and `bicep lint` clean; `run_local` finished in about 70 s. Spark runs with `local[2]`, 1 GB, 2 shuffle partitions.

What the tests prove:
- **Bronze** keeps every line, including a truncated JSON line (`_corrupt_record`), and records the file with `_metadata.file_name`.
- **Quality**: each reject reason (`unparseable_record`, `missing_order_id`, `bad_op`, `bad_currency`, `bad_amount`, `bad_timestamp`) lands in `silver/orders_quarantine`.
- **MERGE**: insert, update, delete; two updates to one order in a batch keep the highest `seq`; a late update, a stale delete and a replayed batch change nothing.
- **PII**: `customer_email` exists only in bronze; silver and gold carry `sha2(lower(trim(email)))`.
- **Synapse reader**: `delta_state()` in `tests/conftest.py` reads a table the way a Delta reader v1 does (add/remove actions, plain Parquet, deletion vectors ignored).
  With deletion vectors off it returns the same rows as Spark; with them on, after a `DELETE`, **it still returns the deleted row** (the documented failure, reproduced).
- **Drift**: serving views, the Power BI TMDL, the lifecycle rule and the notebook imports are checked against `contract.py`.

## Gotchas (what the blog got wrong or skipped)

1. **The 90-day archive rule for Bronze breaks Delta.** Learn: blobs in the archive tier cannot be read until rehydrated (up to 15 hours), and Databricks raises `DELTA_LOG_FILE_ARCHIVED`
   if `_delta_log` is archived. Databricks has an archival-support feature (preview) that needs `delta.timeUntilArchived`; this lab avoids the whole problem: the lifecycle rule in
   `infra/main.bicep` only moves `lake/landing/` to cool, and a test fails if it ever gets another prefix or a `tierToArchive`.
2. **Synapse serverless is a Delta reader version 1.** Learn: it ignores deletion vectors ("possibly wrong results") and column mappings, has no time travel, cannot write Delta,
   and cannot read V2 checkpoints. So the tables are created with `delta.enableDeletionVectors = false`, never rename columns, and Learn suggests the Fabric SQL endpoint for newer Delta features.
   Databricks may enable deletion vectors by default for new tables in your workspace: check before pointing Synapse at them.
3. **Purview cannot be deployed.** Learn: classic Microsoft Purview data governance is being retired, you can no longer create new accounts, and existing capabilities stay in maintenance mode
   through 12 November 2027. The blog's Purview snippet (which also never registered its rule) is therefore not built; there is no Purview in `main.bicep`, and a test fails if one appears.
4. **`input_file_name()` is gone.** Unsupported from Databricks Runtime 17.3 LTS and not available on Unity Catalog; the pipeline uses `_metadata.file_name`.
5. **Spark 4 is ANSI by default**: `to_timestamp("not a time")` raises. The pipeline uses `try_to_timestamp` so a bad date is a quarantined row, not a failed job.
6. **Revenue across currencies**: the lake has no exchange rates, so the DAX measure `Revenue (one currency)` is blank unless exactly one currency is in context.
7. **A delete that arrives before its insert is ignored** (there is no tombstone), so the later-arriving insert wins. Fine for a demo; production needs a tombstone or a soft-delete column.
8. **Unity Catalog row filters and masks apply to Databricks queries.** Synapse serverless reads the files in storage, so I expect them not to apply there. Not verified: protect Synapse
   with storage RBAC or by serving only data that is safe for that audience.
9. The blog's Power BI "JSON" is not a real format (TMDL is), and its Silver "quality framework" was never implemented; both are replaced by code and tests here. Its footer says "Last validated: April 2026", which is after the article date.
10. **Synapse is not retired** (Learn: no announced retirement of Synapse Analytics or Synapse Spark 3.5), but Learn calls Microsoft Fabric the strategic platform for new analytics.

## Deploy and run (needs the lab Azure subscription; see `demo.md`)

```bash
az group create -n rg-mglab-deep-dive-14 -l westeurope
az deployment group create -g rg-mglab-deep-dive-14 -f infra/main.bicep -p infra/main.bicepparam \
   -p synapseAdminObjectId=$(az ad signed-in-user show --query id -o tsv)
```

Databricks Premium (or the 14-day trial tier, which needs a pay-as-you-go subscription, not an Azure Free Trial one), Unity Catalog metastore and an external location on the `lake`
container using the access connector are set up by hand in the workspace (not in the Bicep). Then run `medallion_job.py`, `serving.sql` and open the TMDL.

## Not verified in the lab yet

Everything that needs a service: (1) the Bicep deployment (Synapse `azureADOnlyAuthentication` with no SQL admin login, Databricks `trial` SKU name, the access connector role, deployment time);
(2) the notebook on a cluster (how `lakehouse` is installed: wheel or workspace files); (3) `uc_governance.sql`; (4) the Synapse views reading what Databricks wrote, including
whether new Databricks tables get deletion vectors by default; (5) the TMDL opening in Power BI Desktop and refreshing from the serverless endpoint; (6) costs, which this
folder deliberately does not quote (Learn gives no prices; see the pricing pages).

## References

- Serverless SQL pool self-help, Delta Lake (reader v1, deletion vectors, column mapping, time travel): https://learn.microsoft.com/azure/synapse-analytics/sql/resources-self-help-sql-on-demand#delta-lake
- Query Delta Lake (v1) files with serverless SQL pool: https://learn.microsoft.com/azure/synapse-analytics/sql/query-delta-lake-format
- OPENROWSET (serverless): https://learn.microsoft.com/azure/synapse-analytics/sql/develop-openrowset
- Synapse runtimes (no retirement announced; Fabric strategic): https://learn.microsoft.com/azure/synapse-analytics/spark/apache-spark-version-support
- Purview Data Map pricing page (retirement notice, maintenance mode to 12 Nov 2027): https://learn.microsoft.com/purview/data-gov-classic-pricing-data-map
- Purview Data Map overview (capacity units): https://learn.microsoft.com/purview/data-map
- `input_file_name` (deprecated): https://learn.microsoft.com/azure/databricks/sql/language-manual/functions/input_file_name ; Databricks Runtime 17.3 LTS: https://learn.microsoft.com/azure/databricks/release-notes/runtime/17.3lts
- File metadata column: https://learn.microsoft.com/azure/databricks/ingestion/file-metadata-column
- Archival support in Azure Databricks: https://learn.microsoft.com/azure/databricks/optimizations/archive-delta
- Lifecycle management and archive tier: https://learn.microsoft.com/azure/storage/blobs/lifecycle-management-overview ; https://learn.microsoft.com/azure/storage/blobs/archive-blob
- Row filters and column masks (manual): https://learn.microsoft.com/azure/databricks/data-governance/unity-catalog/filters-and-masks/manually-apply
- Azure Databricks free trial and Free Edition: https://learn.microsoft.com/azure/databricks/getting-started/free-trial ; https://learn.microsoft.com/azure/databricks/getting-started/free-trial-vs-free-edition
- TMDL overview: https://learn.microsoft.com/analysis-services/tmdl/tmdl-overview ; TMDL view in Desktop: https://learn.microsoft.com/power-bi/transform-model/desktop-tmdl-view
- Blog Complete Guide: https://www.devladlog.com/articles/deep-dive/2026-03-16-enterprise-data-lakehouse-azure-synapse-databricks-power-bi-purview/
