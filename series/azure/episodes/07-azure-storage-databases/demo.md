# Demo shot list — DEVLADLOG Azure #7, Storage & Databases

Everything below **needs the lab subscription** (marked *needs tenant*) except the local checks. The episode builder
ran the local checks (47 xUnit tests incl. Azurite, Bicep lint/build, the API on SQLite with `smoke.sh`). Nothing
was deployed to Azure and no Azure sign-in was used.

## Lab environment

No VMs. Screens are recorded on the **recording laptop** (Windows): a bash terminal (Git Bash or WSL) with the
Azure CLI signed in as `labadmin`, the **.NET 10 SDK**, `curl` and `python3`; and a **browser on the lab tenant**
(Azure portal, signed in as `labadmin`).

Azure resources, all in resource group **`rg-mglab-azure-07`** (West Europe), tags `workload=contoso-orders`,
`environment=lab`. Prices: Azure Retail Prices API, EUR, list prices, West Europe, queried 21 Nov 2026.

| Resource | SKU / setting | Estimated cost for a 2-hour recording window |
|---|---|---|
| Storage account `stordersxxxx` | StorageV2, Standard_LRS, Hot, **shared key access disabled**, soft delete 7 days, lifecycle rule `invoices-age-out` | a few KB of blobs and < 100 operations: **< €0.01** (Hot LRS €0.0176/GB-month, operations €0.0039 per 10,000) |
| ↳ Role assignment | Storage Blob Data Contributor for `labadmin` on the account | €0 |
| SQL logical server `sql-orders-xxxx` | **Microsoft Entra-only authentication**, admin = `labadmin`, TLS 1.2, firewall rule `demo-client` = the laptop's public IP | €0 (the logical server isn't billed) |
| ↳ Database `sqldb-orders` | **Free tier**: General Purpose serverless `GP_S_Gen5` 2 vCores, 32 GB, `useFreeLimit: true`, **AutoPause** at the monthly limit | **€0** (100,000 vCore seconds free per month; a 2-hour session uses a few thousand) |
| **Total** | | **≈ €0.01** |

Free tier: up to 10 free databases per subscription; deleting this one frees the slot. Make sure no earlier free-tier
database in the subscription was created in another region with *Advanced configuration* (Learn: that region then
applies to all free databases in the subscription).

Permissions: Owner on the subscription (or Contributor + User Access Administrator on the group, for the role assignment).
Licences: none beyond the subscription.

**Tear-down:** `infra/teardown.sh rg-mglab-azure-07`, then `az group exists --name rg-mglab-azure-07` → `false`.

## Setup (needs tenant)

```bash
cd series/azure/episodes/07-azure-storage-databases
dotnet test tests/Contoso.Orders.Tests          # 47 passed, before anything else (needs node/npx for Azurite)
az login                                        # as labadmin
az account set --subscription "<lab subscription>"
infra/deploy.sh rg-mglab-azure-07 westeurope    # ~5 min: what-if, deploy, free-tier check, "Schema created."
```

`deploy.sh` reads your object ID and UPN from `az ad signed-in-user show` and your public IP from api.ipify.org
(set `CLIENT_IP=` yourself if the laptop's outbound IP differs, e.g. behind a VPN). If `--create-schema` fails with a
login error, wait one minute (role/admin propagation) and rerun only that step:
`Database__Provider=SqlServer Database__Server=<fqdn> Database__Database=sqldb-orders dotnet run --project src/Contoso.Orders.Api -- --create-schema`.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/deploy-free-tier.jpg` — scene `deploy_screen` (needs tenant)
Terminal, end of `infra/deploy.sh rg-mglab-azure-07 westeurope`: the **free tier check** table
(`GP_S_Gen5`, `useFreeLimit True`, `AutoPause`, status `Online`) and the line **`Schema created.`**
Mask: subscription ID, the server FQDN suffix if shown, the object ID/UPN in the what-if output (scroll so they're not visible).

### 2. `screens/smoke.jpg` — scene `smoke_screen` (needs tenant)
Second terminal: `infra/run-api.sh` running (API on http://localhost:5199). First terminal: `infra/smoke.sh`.
Capture the whole output: idempotent create (201, replay 200 with `Idempotent-Replay true`, 409), paging (two pages),
concurrency (412, 200, 412), invoice (SAS fields `sp=r sr=b spr=https skoid=<object id>`, download 200, tampered 403),
**`All checks passed.`** Mask: nothing secret is printed (the script prints `<object id>` instead of the skoid);
the storage account name is in no output line.

### 3. `screens/query-editor.jpg` — scene `query_screen` (needs tenant)
Portal → SQL database `sqldb-orders` → **Query editor (preview)** → sign in with **Microsoft Entra authentication**
(there is no SQL authentication option that works). If it asks for a firewall rule for the browser's IP, it's the same
laptop IP, already allowed. Paste `db/demo-queries.sql`, run query 1 and 2 (select them). Capture: `signed_in_as`
= the lab admin UPN, `service_objective` = `GP_S_Gen5_2`, and the order rows from the smoke test (customer
`alex-demo-<run>`, one row `Cancelled`). Then run query 4 to show the query editor's own session.
**Close the query editor** afterwards (open sessions keep the database from pausing, which screen 4 needs).
Mask: the UPN domain (lab tenant domain), server name.

### 4. `screens/resume-40613.jpg` — scene `gotcha_resume` (needs tenant)
Stop `run-api.sh` (Ctrl+C), close the query editor, wait **at least 20 minutes** (free tier auto-pauses after 15
minutes without sessions). Then:
```bash
az sql db show -g rg-mglab-azure-07 -s <server name> -n sqldb-orders --query status -o tsv    # Paused
infra/run-api.sh &  sleep 8;  curl -s localhost:5199/healthz                                  # waits, then {"status":"ok",...}
```
Capture the API console showing EF Core's retry log lines (`A transient exception occurred during execution. The
operation will be retried after …` with **`Database '…' on server '…' is not currently available`**, error number
40613) and the final `{"status":"ok"...}`. If the database had not paused (status `Online`), check query 4 for a
lingering session and wait again. If no 40613 shows (resume was faster than the first attempt), say so in the
narration rather than faking it. Mask: server and database names inside the error text.

### 5. `screens/lifecycle.jpg` — scene `lifecycle_screen` (needs tenant)
Portal → storage account → **Data management → Lifecycle management** → rule `invoices-age-out` in code view
(or list view showing Cool 30 / Cold 90 / Delete 3650 days, prefix `invoices/`). Side by side (or a second capture
composited): **Settings → Configuration** with **Allow storage account key access: Disabled**, and
**Containers → invoices** showing `2026/11/<id>.json` blobs. Mask: account name, subscription.

## Tear-down (needs tenant)
```bash
kill %1 2>/dev/null           # the API, if still running
infra/teardown.sh rg-mglab-azure-07
az group exists --name rg-mglab-azure-07     # false after a few minutes
```
