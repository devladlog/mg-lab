# Demo shot list — DEVLADLOG .NET #3 Entity Framework Core

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Power Platform | none |
| Lab users | `labadmin` (the recording account): `az login` off camera, becomes the SQL server's **Microsoft Entra admin** (read from `az ad signed-in-user show`) and signs in to the Query editor. Sample data uses fictional `@contoso.com` names only |
| Azure | Resource group **`rg-mglab-net-03`** in **West Europe** (the deploy script's default region), created by the deploy script with `RG=rg-mglab-net-03` exported (the script's built-in default is `rg-mglab-net03`): **Azure SQL Database free offer** (`--use-free-limit true`, auto-pause at the monthly limit: €0) + App Service plan **Free F1, Linux** + web app with a system-assigned managed identity (€0). Tear-down: `az group delete --name rg-mglab-net-03` |
| Local screens | `sql-log` and `lost-update` run the real API on the laptop with the SQLite provider the app ships with; they show EF Core's own SQL and concurrency check, not a stand-in for Azure SQL (the two Azure screens show Azure SQL) |
| Licences / trials | none beyond the subscription |
| Recording machine | The Windows lab laptop: WSL (Ubuntu) bash with .NET SDK 10.0.1xx, Azure CLI, `curl`, `jq`, `zip` (the `deploy/*.sh` scripts are bash); browser on the host for the portal and `localhost` screens (WSL forwards localhost ports) |

Code and tests were built and run in the container (`dotnet test -m:1`: 26 passed). `deploy/local-demo.sh` was run
against the local API on SQLite; its output is in [`deploy/local-demo.output.txt`](deploy/local-demo.output.txt) and
the SQL EF Core logged meanwhile in [`deploy/local-demo.sql-log.txt`](deploy/local-demo.sql-log.txt).
`PACKAGE_ONLY=1 ./deploy/deploy-azure.sh` was run (18 MB zip; the published app started and `/healthz` was Healthy).
**Needs tenant:** `azure-sql`, `azure-demo` (Azure subscription + Microsoft Entra). `sql-log` and `lost-update` don't.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| .NET SDK 10.0.1xx, `curl`, `jq`, `zip` | `dotnet tool restore` installs `dotnet-ef` 10.0.15 locally | free |
| Azure subscription (lab) with the €10 budget alert | **Azure SQL Database free offer** (`--use-free-limit true`, `AutoPause`: pauses at the monthly limit, never bills) + App Service **Free F1, Linux** | €0 |
| Lab account that can create resources and be the SQL **Microsoft Entra admin** | the script reads it from `az ad signed-in-user show` | free |
| Free-offer eligibility | up to 10 free databases per subscription; check none of the 10 is already used up | — |
| Masking | `pipeline/mask.js` in the portal; blur server name, app host, subscription, tenant, signed-in account | — |

## Setup

### Local (screens 1 and 2) — no tenant
```bash
cd series/net/episodes/03-entity-framework-core
dotnet tool restore
dotnet test -m:1                                                       # expect Passed: 26
cd src/ProjectRequests.Api
rm -f requests.db
dotnet dotnet-ef database update --context SqliteRequestsDbContext     # 2 migrations applied
dotnet run --launch-profile http                                       # http://localhost:5207, leave running
```

### Azure (before screen 3) — needs tenant
```bash
az login                                    # not on camera
az account set --subscription <lab subscription>
export RG=rg-mglab-net-03
APP=contoso-requests-<4 digits> SQL=contoso-sql-<4 digits> ./deploy/deploy-azure.sh infra    # ~5-8 min
```
The script prints the next steps. In the portal: **SQL databases → requests → Query editor (preview)** → sign in with
Microsoft Entra (the account the script made Entra admin) → open and **Run** `deploy/sqlserver-migrations.sql` →
then open and **Run** `deploy/out/grant-app-identity.sql` (generated with the app name filled in). Do the grant
**before** the app's first request: managed identity tokens are cached, new permissions only show up when the
cached token expires.

```bash
APP=contoso-requests-<4 digits> SQL=contoso-sql-<4 digits> ./deploy/deploy-azure.sh app      # zip deploy + /healthz
```
If the query editor can't connect from your network, add your client IP on the server's **Networking** page (Learn's
free-tier article shows `az sql server firewall-rule create` for one IP), and remove it at the end.

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/sql-log.jpg`** — *The SQL EF Core actually sends* (no tenant)
   - Split terminal, dark theme, font ≥ 18 pt. Left: the `dotnet run` console. Right: `./deploy/local-demo.sh`.
   - In frame on the left: the list `SELECT ... FROM "ProjectRequests" AS "p" INNER JOIN "Departments" AS "d"` and the
     `UPDATE "ProjectRequests" SET "Budget" = @p0, ... "Version" = @p3 WHERE "Id" = @p4 AND "Version" = @p5`.
     Scroll back if needed; `deploy/local-demo.sql-log.txt` shows what to expect. Parameter values print as `?`.

2. **`screens/lost-update.jpg`** — *The lost update that didn't happen* (no tenant)
   - `./deploy/local-demo.sh` on a fresh `requests.db` (stop the app, `rm requests.db`, `database update`, run).
   - In frame: step 2 "Sam sees budget 40000.0, version …", step 3 "priority High", step 4 `<- HTTP 409` +
     "The request changed since you read it.", step 5 GET (400000.0, Submitted) then `<- HTTP 200` "Approved".
   - Nothing to mask (fictional `@contoso.com` names, random GUIDs).

3. **`screens/azure-sql.jpg`** — *The reviewed script, applied* (**needs tenant**)
   - Query editor after running `sqlserver-migrations.sql`: "Query succeeded".
   - Then run and capture: `SELECT MigrationId FROM __EFMigrationsHistory;` (two rows) and `SELECT * FROM Departments;`
     (FIN, IT, OPS). Optional: run the script a second time to show it changes nothing.
   - **Mask** server name, subscription, signed-in account in the portal header.

4. **`screens/azure-demo.jpg`** — *Same story, Azure SQL behind it* (**needs tenant**)
   - `curl https://<host>/healthz` → `Healthy` (the first call can take a while if the database auto-paused:
     free-offer databases pause after 15 minutes idle).
   - `./deploy/local-demo.sh https://<host>` → 201, 200, 200, **409**, 200, 200 (Approved), summary.
   - Then `az webapp restart -g rg-mglab-net-03 -n <app>` and `curl https://<host>/api/requests/<id>` → the approved
     request is still there (second capture or a cut).
   - **Mask** the host name.

## Tear-down
```bash
az group delete --name rg-mglab-net-03 --yes --no-wait     # web app, plan, SQL server, database
rm -f src/ProjectRequests.Api/requests.db
rm -rf deploy/out
```
Confirm in the portal that the resource group is gone (the free database counts against the 10 per subscription
until it's deleted). The managed identity is deleted with the web app.
