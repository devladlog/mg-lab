# Demo shot list — Power BI #10 Incremental Refresh & Large Datasets

## Lab environment

Real tenant work, plus one real Azure resource (`series/LAB.md`). The lab has no on-premises data gateway yet (episode 14) and
CON-SQL01 (10.50.0.30) is only reachable from the Hyper-V network 10.50.0.0/24, not from the Power BI service. So the 2,000,000
order lines go into a **free-tier Azure SQL Database**, which the service reaches directly. CON-SQL01 is not used in this episode.

| What | Details | Cost |
|---|---|---|
| Azure resource group | `rg-mglab-powerbi-10`: one logical SQL server `contoso-lab-sql-<suffix>` and one database `ContosoBikesIR`, General Purpose serverless, **free tier** (Learn: 100,000 vCore seconds, 32 GB of data and 32 GB of backup storage per month, up to 10 free databases per subscription; it can't be restored or copied into) | free, with `AutoPause` at the monthly limit (needs Azure) |
| Fabric trial capacity | workspace `Contoso Sales (Lab)` (the workspace of episodes 6-9 can be reused). **XMLA read-write** must be switched on for the capacity by the capacity admin (Learn: read-only by default), and the tenant setting *Allow XMLA endpoints and Analyze in Excel with on-premises semantic models* must be on (needs tenant) | free (trial) |
| Users | `alex.demo` (workspace admin, capacity admin on the trial); the other lab users are not needed | — |
| Recording laptop (Windows) | Power BI Desktop (current release), SQL Server Management Studio (latest), PowerShell 7.2+, Python 3.10+ | free |
| Source | `src/sql/01-create-and-load.sql` (2,000,000 lines, four years, deterministic), `02-late-changes.sql`, `03-checks.sql` | within the free vCore seconds (not measured: record how much *Free amount remaining* drops) |

## What was verified where

| Step | Verified in the container | Needs tenant / Azure / Desktop (recording day) |
|---|---|---|
| The SQL scripts | every batch parsed as T-SQL (sqlglot); the load is plain arithmetic mirrored in Python: totals per year and in all, 2,000,000 lines, 3,060,000,980.00 | **running them on Azure SQL** (needs Azure) |
| Model and policy | TMDL loaded by the Tabular Object Model (including the refresh policy), every expression (also the policy's two M expressions) parsed by Microsoft's Power Query parser, `ir-lint` rules IR001-IR011 | **the first refresh**, whether the filter folds (View Native Query), that Desktop opens the `.pbip` and writes the same policy (needs Desktop and Azure) |
| Partitions | `ir_partitions.py` reproduces Learn's worked example (2021-02-02: 2018, 2019, 2020, 2021Q101, 2021Q10201, today, DirectQuery) and the merge rules | **the real partitions and their names in SSMS** (needs tenant) |
| Enhanced refresh calls | Pester tests (19) against mocks shaped like Learn's samples | real responses; the request id (Learn: last segment of the `Location` header; the module reads it from the history instead) (needs tenant) |
| Report | PBIR schemas, layout spec | whether Desktop opens it |

## Setup (off camera, once)

1. Azure (needs Azure; the person recording runs these, never the build). Sign in yourself, then, with a password you keep out of
   the recording:
   `az group create -n rg-mglab-powerbi-10 -l <region>`, `az sql server create -n <server> -g rg-mglab-powerbi-10 -l <region> --admin-user <login> --admin-password <password>`,
   `az sql db create -n ContosoBikesIR -s <server> -g rg-mglab-powerbi-10 --edition GeneralPurpose --family Gen5 --capacity 2 --compute-model Serverless --use-free-limit true --free-limit-exhaustion-behavior AutoPause`
   (Learn: without `--use-free-limit` the database is billable; check `useFreeLimit` is `true` in the output).
   Add a firewall rule for your own IP (`az sql server firewall-rule create`). The Power BI service also has to reach the server:
   allow Azure services in the server's networking settings (not verified here: check what the refresh needs).
2. Run `01-create-and-load.sql` in SSMS or Desktop's query tool (several minutes: record the time), then `03-checks.sql`. Expected
   (`python3 src/tools/sql_mirror.py --rows 2000000`): 2023 499,655 lines, 2024 501,020, 2025 499,660, 2026 499,665, all
   2,000,000 lines, 3,060,000,980.00 sales amount, 400,000 orders. **Close the SSMS session afterwards**: an open connection
   keeps the database from pausing and spends vCore seconds.
3. Desktop: open `src\ContosoSalesIR.pbip`, **Transform data > Edit parameters**: `SqlServer` = the server name. Refresh (one week loads),
   check *View Native Query* on the filter step, open **Incremental refresh** on the table and compare with the TMDL, then **Publish** to
   `Contoso Sales (Lab)`. **Never publish this model from Desktop again** (it would remove the partitions).
4. In the service: set the model's credentials (database authentication, the SQL login) under *Semantic model > Settings > Data source credentials*.
5. Run the first refresh by hand and note how long it takes (the initial refresh creates the partitions and loads all the history).
   Expected total rows at the end: every line up to and including the day of the refresh (`python src/tools/ir_partitions.py --model src/ContosoSalesIR.SemanticModel/definition --date <day> --rows-from expected/daily-2m.json`).
   The card *Latest Order* shows the newest order loaded; rows dated after the refresh day are not loaded.

## Steps and screens (match the `screen` scenes in script.yaml)

| Scene id | File | Steps and what must be on screen (needs Desktop / Azure / tenant) |
|---|---|---|
| `desktop` | `screens/desktop-filter.jpg` | Power Query: the four parameters and the `Sales` query. Right-click the `InPeriod` step > **View Native Query**: the SQL has both dates in the `WHERE`. If the item is greyed out, say so and show IR007 of `ir_lint.py`. Mask the server name. |
| `dialog` | `screens/policy-dialog.jpg` | **Incremental refresh and real-time data** for `Sales`: archive 3 years, refresh 10 days, detect data changes on *Modified Date*. Real time off. Check *Only refresh complete days* is what you want and write down what it does to the policy in the TMDL (the calculator does not model it). |
| `ssms` | `screens/ssms-partitions.jpg` | SSMS **Connect > Analysis Services**, server = the workspace connection string, sign in as `alex.demo`. **Databases > ContosoSalesIR > Tables > Sales > Partitions**. Expected: 28 partitions on 2026-11-21 (18 historical, 10 refresh); on another day run the calculator. **Copy every name into the README table**: month numbering (`2026Q41101` or `2026Q40201`) is the open question (`--month-style`). |
| `after` | `screens/after-changes.jpg` | Run `02-late-changes.sql`. Refresh in the service; show the report. Then `.\src\pipeline\Invoke-PartitionRefresh.ps1 -WorkspaceId ... -SemanticModelId ... -Table Sales -Partition <March 2023 partition> -SkipRefreshPolicy` (rehearse with `-WhatIf`), and show the card again. Which numbers change in which step is the point: record both. |

## Not a screen scene, but record it

- A refresh with detect data changes: after the first full refresh, refresh again without changing anything; look in SSMS at which
  partitions were processed (the *last processed* time). Say what you really see; Learn says an unchanged period is skipped.
- Run `Invoke-PartitionRefresh.ps1 ... -EffectiveDate <first day of next month> -WhatIf`, then look at `ir_partitions.py --date` for that day: the day
  partitions of the month merge into a month partition. Only run it for real if you accept that the service rolls the partitions forward.
- The initial refresh time against the two hour (Pro) and five hour (Premium) limits is not a problem at this size; do not claim it is.

## Masking

- Mask the server name, the SQL login, the workspace connection string, the tenant and capacity names, and any address except `alex.demo`.
- Never show the SQL password, the token of `Connect-PowerBIServiceAccount`, or a connection string with a password. Clear the terminal history.

## Tear-down

1. Power BI service: delete the semantic model and the report (or the workspace if it was created only for this).
2. Azure: `az group delete -n rg-mglab-powerbi-10 --yes` removes the server and the database (needs Azure). Check the resource group list afterwards.
3. Remove the SSMS connection and the saved server name; `Disconnect-PowerBIServiceAccount`.
4. If *XMLA read-write* was switched on only for this episode, set the capacity back to its previous setting.
