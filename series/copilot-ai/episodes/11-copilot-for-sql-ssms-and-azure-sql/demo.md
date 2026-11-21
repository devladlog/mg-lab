# Demo shot list - Copilot & AI #11 Copilot for SQL: SSMS and Azure SQL

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | The **shared `CON-SQL01`** (Windows Server 2025 Datacenter Eval, Server Core, SQL Server 2022 Developer, default instance, TCP 1433, mixed authentication, 10.50.0.30, see `series/LAB.md`). No new VM, no other VM used. The demo creates its own database `ContosoCopilot` and the login `copilot_demo_analyst` on it and removes both in tear-down; nothing else on CON-SQL01 is touched |
| Recording machine | The Windows lab laptop (host, reaches 10.50.0.30): **SSMS 22.7 or later** (Learn's release notes list 22.12.1 as current on 21 Nov 2026; install with the **AI Assistance** workload in the Visual Studio Installer), PowerShell 7 terminal, Python 3.10+ (`pip install -r src/requirements.txt`), a browser on the lab tenant for the Azure portal |
| Tenant / accounts | The Momento Galático lab tenant, `labadmin` (Owner of the Azure subscription) for the portal. SQL Server side: the lab Administrator for the setup scripts, `copilot_demo_analyst` (SQL login created by script 00, **not** sysadmin) for every Copilot screen. Passwords are typed off camera |
| GitHub account | The owner's GitHub account (the same one as the mg-lab repo), signed in inside SSMS. **Confirm the plan at the recording** (Copilot Free is enough for chat; Learn: Free is not available if the account has a Copilot licence through an organisation or an existing Pro subscription or trial). Agent mode on the free plan is allowed by Learn's wording ("alternatively use Copilot for free"), but the monthly allowance is not stated numerically: check the status in the Copilot badge menu (**Copilot Free Status**) before each take. GitHub plans on 21 Nov 2026 (docs.github.com): Pro 10 USD, Business 19 USD per seat, Enterprise 39 USD per seat per month. Re-check on the day |
| Azure | Resource group `rg-mglab-copilot-ai-11` (West Europe): one **Azure SQL Database, free offer** (General Purpose serverless, `Start free`) with the **AdventureWorksLT** sample, on a new logical server. Estimated cost for the recording window: **0 EUR** inside the free allowance (100,000 vCore seconds, 32 GB data and 32 GB backup a month per Learn); choose **auto-pause when the free limit is reached**, never "continue for additional charges". Azure Copilot itself: Learn says today's capabilities are included at no extra cost (the Observability agent is usage-based; do not use it). Delete the resource group in tear-down |
| Licences / purchases | Nothing bought. No Microsoft 365 Copilot licence involved. No Fabric capacity (Copilot in a Fabric SQL database needs paid F2/P1 and is not supported on trial SKUs: **not demoed**, mention only) |
| Network | The laptop needs outbound HTTPS to GitHub and the Azure portal. For the optional "connect SSMS to the Azure SQL database" take, add the laptop's public IP to the server firewall (delete the rule in tear-down). The Azure Copilot screens do not need it |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the lab |
|---|---|---|
| `tsql_gate` (rules, modes, constitution lint/render, CLI) | yes: 61 pytest tests | - |
| Seed data and the four reference queries | yes: executed on DuckDB (T-SQL transpiled by sqlglot), compared with expected CSVs and an independent Python calculation | **run on SQL Server**: the files have never been executed by SQL Server (no Docker here) |
| `00`-`04`, `99` scripts | parsed as T-SQL by sqlglot only | **first real run on CON-SQL01** (see "Open points") |
| `agentExecuteAsUser` honoured by SSMS | no | **record it** |
| Everything Copilot says (SSMS and Azure portal) | no | **record it**, keep wrong answers |

Open points to confirm at the first real run (each one changes the narration if different):
1. `04-verify-copilot-user.sql` must show error **229** for the UPDATE as `GHCP_DB_User`, 30 visible orders, SELECT as the only
   object permission, and `rows_changed_as_analyst = 1` (rolled back). If the error number differs, fix the `denied` scene.
2. Learn says `GRANT IMPERSONATE` is required for Copilot to work when a constitution names a user. After script 03,
   check that a user **without** the grant gets a Copilot failure (optional take: create a second login for this).
3. Whether Copilot's SQL in Ask mode returns the same five rows as `q01` (expected: Graca Mockup 5,916.00; Hugo Dummy 4,582.00;
   Carla Example 379.00; Filipe Fictional 348.00; Rita Sample 232.00). If not, show the difference and say so.
4. Where the `sql-tools` setting `READ_ONLY` / `READ_WRITE` lives (Learn says "the mcp.json file" without a path on the pages
   we read). Only needed for the optional agent write attempt; the `denied` screen does not depend on it.
5. What the Azure Copilot pane answers for a free, nearly idle sample database.

## Prerequisites
- Terminal: dark theme, 18 pt, 1600x900, short prompt. SSMS dark theme, font 14 pt, 125 % zoom. Browser dark theme, 125 %.
- `python -m pip install -r src/requirements.txt` and `python -m pytest -q` -> `61 passed`.
- SSMS: sign in to GitHub from the Copilot badge (**Open Chat Window to Sign In**, Ctrl+\\, Ctrl+C). Model picker on default.
- The CON-SQL01 SQL Server accepts connections from the laptop (the lab already does for the SQL series).

## Setup
1. **SQL Server (off camera).** From the repo folder, in PowerShell:
   `sqlcmd -S 10.50.0.30 -E -i src/sql/00-create-database.sql -v AnalystPassword="<typed>"`, then
   `sqlcmd -S 10.50.0.30 -E -d ContosoCopilot -i src/sql/01-contoso-copilot.sql`, `...02-copilot-user.sql`.
   Check: `SELECT COUNT(*) FROM Sales.Orders` = 30. Run `python -m tsql_gate check src/queries/*.sql` -> exit 0.
   Do **not** run `03-constitution.sql` yet: it is part of the recording (screen 3 shows before/after).
2. **Azure (off camera).** In the portal create resource group `rg-mglab-copilot-ai-11` and, from the Azure SQL hub, **Start free**
   in that group: new logical server (authentication: Microsoft Entra-only with `labadmin` as admin if the portal offers it,
   otherwise SQL authentication with a password typed off camera), database `sqldb-copilot-demo`, **Additional settings >
   Use existing data > Sample** (AdventureWorksLT), behaviour at the free limit **auto-pause**. Wait until it is online and
   check the **Free monthly vCore amount** on the Overview.
3. Clear SSMS Copilot approvals first: Tools > Options > GitHub > Copilot > Tools (reset), so "Allow always" is not set.
4. In SSMS connect to `10.50.0.30` as `copilot_demo_analyst` (SQL authentication, trust the lab certificate), open a query
   window on `ContosoCopilot`. Save the generated answers next to `src/queries/` so the comparison is quick.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `ssms-ask` | `screens/ssms-ask.jpg` | Copilot Chat, **Ask** mode, active editor on `ContosoCopilot`. Prompt: *Top 5 customers by revenue in September 2026, revenue is quantity times unit price, cancelled orders excluded*. Copilot's T-SQL, **Apply** into the editor (diff view, Tab), run it, result grid beside `q01-top-customers.sql` results. Say whether they match; keep a wrong answer |
| `ssms-agent` | `screens/ssms-agent.jpg` | Chat in **Agent** mode, the Tools panel showing `sql-tools` (open it for one take). Prompt: *In the ContosoCopilot database on the CON-SQL01 server, which customers have never placed an order?* Capture the approval pause with the **Allow** dropdown open (Allow once / Allow for this session / Allow always), pick **Allow once**, then the answer (expected: Eva Newcustomer, customer 6). Never select Allow always |
| `denied` | `screens/denied.jpg` | Before: run `src/sql/03-constitution.sql` as the lab Administrator (a second query window, Windows authentication) and, in Copilot Chat, ask *Does this database have a constitution set?* (Learn's own check). Then, as `copilot_demo_analyst`, run `src/sql/04-verify-copilot-user.sql`: show the grids `running_as = GHCP_DB_User`, `visible_orders = 30`, the permission list, the error 229 grid, and `rows_changed_as_analyst = 1`. Optional take: switch `sql-tools` to `READ_WRITE` and ask Agent mode *Cancel order 1 in ContosoCopilot on CON-SQL01*; record what Copilot reports, then switch back to `READ_ONLY` |
| `azure-copilot` | `screens/azure-copilot.jpg` | Azure portal, `sqldb-copilot-demo` page, Copilot icon in the page header. Two prompts (Learn's sample list): *What's the size of this database?* and *What are the most expensive queries in my workload?* Capture the answers. Mask subscription ID, server name, tenant name. Do not use the Observability agent |
| terminal (code scenes `gate`, `gate-tests`) | no screen file | Optional extra take for the `gate` scene: terminal in `src`, `python -m tsql_gate check samples/risky-examples.sql --mode readwrite`, then `python -m tsql_gate check queries/q01-top-customers.sql` (no findings) and `python -m pytest -q` in the episode folder (61 passed) |

Masking: tenant domain, subscription ID, logical server name, the lab laptop's public IP, GitHub account name and avatar if
it is a personal one (use a crop). SQL Server is internal (10.50.0.30) and fictional: no masking needed.

## Tear-down
1. SSMS: Tools > Options > GitHub > Copilot > Tools: reset approvals. Disconnect every connection to the Azure SQL database
   (open connections keep a free-tier database awake and use the allowance, per Learn). Sign out of GitHub in SSMS if the account is personal.
   If you edited the `sql-tools` setting, restore `READ_ONLY`.
2. `sqlcmd -S 10.50.0.30 -E -i src/sql/99-teardown.sql` (drops `ContosoCopilot` and the login).
3. Azure: delete the resource group `rg-mglab-copilot-ai-11` (database, logical server, firewall rule). Confirm in Cost Management that nothing is accruing.
4. Delete the saved screenshots with real names from the working folder; keep only the masked JPEGs in `screens/`.
