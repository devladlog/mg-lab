# Demo shot list — DEVLADLOG Deep Dive #14, Enterprise Data Lakehouse

Code and test scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs tenant + Azure subscription** for everything on screen. Offline (container, no Azure): 23 pytest tests pass (PySpark 4.0.1 + Delta 4.0.1),
`bicep build` and `bicep lint` are clean, `run_local` runs three generated batches. **Not yet run against Azure:** the Bicep deployment, the notebook,
Unity Catalog filters, the Synapse views over Databricks-written tables, Power BI. Record each outcome in the README ("Not verified in the lab yet").

## Lab environment

Recorded on the **lab Windows laptop** (host): Edge (Azure portal, Databricks workspace, Synapse Studio), Windows Terminal with PowerShell 7, **Power BI Desktop**.
No Hyper-V VM and nothing from `series/LAB.md` (10.50.0.0/24) is used: everything lives in Azure.
Local tools: Azure CLI, Bicep CLI, Python 3.13 with Java 17+ (`pip install -r requirements.txt`), Power BI Desktop with the TMDL view enabled, the repo checked out.

**Azure** (lab subscription, one resource group `rg-mglab-deep-dive-14`, West Europe; check Databricks and Synapse availability in the region first)

| Resource | SKU | Estimated cost for a recording day |
|---|---|---|
| Storage account `stmglab14...` (ADLS Gen2, shared keys off) | Standard LRS, Hot | cents (a few MB) |
| Azure Databricks workspace `dbw-mglab14-...` + access connector | **Trial (Premium, 14 days of free DBUs)** via `databricksSku = trial`; needs a pay-as-you-go subscription, not an Azure Free Trial one (Learn) | DBUs free; the cluster VMs are billed to the subscription: use the smallest single-node job cluster, auto-terminate in 10 minutes. **Check the VM cost in Cost Management after the first run and write it in the README** |
| Synapse workspace `syn-mglab14-...` (Entra-only) | serverless SQL pool only, **no dedicated pool, no Spark pool** | billed per data processed by queries: a few MB, cents |
| Power BI | Desktop (free) import model; no Pro/Premium workspace needed for the recording | 0 |
| Microsoft Purview | **not deployed**: new accounts cannot be created (Learn) | 0 |

Roles: the recording identity (`labadmin`) is Owner of the resource group, Synapse Entra admin and Storage Blob Data Reader (the Bicep assigns the last two). The access connector
gets Storage Blob Data Contributor. Total: a few euros at most if the group is deleted the same day. Budget `mglab-monthly` (€30) is not at risk.
Premium Power Platform is not used. Credentials: none in the repo; sign in interactively (off camera).

## Setup (off camera)

1. **Tests first**
   ```bash
   cd series/deep-dive/episodes/14-enterprise-data-lakehouse-synapse-databricks-pow
   python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
   pytest                                  # expect: 23 passed
   bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep
   ```
2. **Deploy**
   ```bash
   az login                                # off camera
   az group create -n rg-mglab-deep-dive-14 -l westeurope
   az deployment group create -g rg-mglab-deep-dive-14 -f infra/main.bicep -p infra/main.bicepparam \
      -p synapseAdminObjectId=$(az ad signed-in-user show --query id -o tsv) --query properties.outputs
   ```
   **Check on first deploy and write the result into the README:** Synapse accepted Entra-only with no SQL admin login; `trial` is a valid Databricks SKU name; deployment time.
3. **Databricks** (by hand, off camera): create the Unity Catalog metastore if the account has none, an external location on `abfss://lake@<storage>.dfs.core.windows.net/`
   using the access connector, catalog `lakehouse`. Upload the `lakehouse` package (wheel or workspace files) and `medallion_job.py`.
4. **Data**: `PYTHONPATH=src python -c "from lakehouse.datagen import make_batch; make_batch('/tmp/landing/b1', 1)"` then
   `az storage blob upload-batch --auth-mode login -d lake -s /tmp/landing/b1 --destination-path landing/orders` (the generated file includes one truncated line and one bad currency on purpose).

## Screens to capture

1920x1080, save as `screens/<name>.jpg` (names match `script.yaml`).

| Screen | What must be on it | Masking |
|---|---|---|
| `portal.jpg` | Azure portal, resource group: storage, Databricks workspace, access connector, Synapse workspace. Then the storage lifecycle rule showing prefix `lake/landing/` only | subscription id |
| `databricks.jpg` | Notebook `medallion_job` run with `batch_id = b1`: printed dict with `ingested`, `rejected`, `applied`; Catalog Explorer on `lakehouse.gold.daily_sales` (or the abfss path if no catalog) | workspace URL, user email |
| `synapse.jpg` | Synapse Studio: run `serving.sql`, then `SELECT TOP 10 * FROM gold.daily_sales` and `SELECT COUNT(*)` equal to the Databricks count | storage account name |
| `powerbi.jpg` | Power BI Desktop: model from the TMDL (paste in TMDL view or open as a PBIP), card Orders, table Revenue (one currency) by region with a currency slicer on one value | server name |

Optional take: run `ALTER TABLE ... SET TBLPROPERTIES ('delta.enableDeletionVectors' = 'true')` on a copy of silver, `DELETE` a row in Databricks, and show Synapse still returning it
(the reader-v1 failure, live). Do this on a copy; **record the real behaviour in the README** (the tests reproduce it with a local reader, not with Synapse).

## Tear-down

```bash
az group delete -n rg-mglab-deep-dive-14 --yes --no-wait     # removes storage, Databricks (and its managed resource group), access connector, Synapse
```
Then confirm in the portal that the Databricks managed resource group `rg-mglab14-dbw-managed-...` is gone, and in Cost Management that nothing is still accruing.
Locally: `rm -rf .venv lake-demo spark-warehouse` (the folder must stay under 5 MB).
