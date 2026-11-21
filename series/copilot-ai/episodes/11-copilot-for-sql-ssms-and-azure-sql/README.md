# DEVLADLOG Copilot & AI #11 - Copilot for SQL: SSMS and Azure SQL

Two Copilots help with T-SQL: **GitHub Copilot in SQL Server Management Studio 22** (chat, completions, agent mode)
and **Azure Copilot** in the Azure portal (Azure SQL Database skills). This episode uses both on the Contoso demo data,
and then does the part most demos skip: who Copilot runs as, what it can change, and who reads its T-SQL before it
runs. What we build:

- the **permission setup** from Learn: a `GHCP_DB_User` (select only), `IMPERSONATE` for the developer, and a database
  `CONSTITUTION.md` whose `agentExecuteAsUser` makes SSMS run every Copilot query as that user;
- **`tsql_gate`**, a small tested Python review gate for T-SQL (what Copilot or anyone wrote), plus a linter and
  generator for the `CONSTITUTION.md`;
- the **demo database** (`ContosoCopilot`) with deterministic data and four **reference queries** to compare with
  whatever Copilot answers.

Nothing here fakes Copilot output. The risky samples are hand-written and labelled so; the Copilot screens are recorded
live (see `demo.md`).

Series plan: [`../../README.md`](../../README.md). Shared lab: [`../../../LAB.md`](../../../LAB.md). Previous episodes:
[Copilot in Power BI and Fabric](../07-copilot-in-power-bi-and-fabric/) (the Fabric side of Copilot) and episode 10,
*Azure Copilot and the Azure MCP Server*. Next: episode 12, [Copilot for Windows Server admins](../12-copilot-for-windows-server-admins/).
Category episodes this builds on:
[SQL Server security](../../../sql/episodes/06-sql-server-security/) (least privilege, the same `Sales` schema idea),
[T-SQL advanced queries](../../../sql/episodes/01-t-sql-advanced-queries/),
[query optimization](../../../sql/episodes/04-query-optimization/) and
[performance tuning](../../../sql/episodes/08-sql-server-performance-tuning/) (what agent mode is asked to analyse).

| Path | What it is |
|---|---|
| [`src/tsql_gate/gate.py`](src/tsql_gate/gate.py) | The review gate: splits GO batches, masks comments/strings, keyword scan + sqlglot structure rules, modes `readonly` / `readwrite` |
| [`src/tsql_gate/constitution.py`](src/tsql_gate/constitution.py) | Parse, lint and render (`sp_addextendedproperty`) a `CONSTITUTION.md`; checks the 7,500-byte limit and privileged `agentExecuteAsUser` |
| [`src/tsql_gate/cli.py`](src/tsql_gate/cli.py) | `python -m tsql_gate check FILE... [--mode readonly\|readwrite] [--json] [-v]`, `constitution lint\|sql FILE` |
| [`src/CONSTITUTION.md`](src/CONSTITUTION.md) | The database constitution used in the demo (Learn's shape: YAML front matter + Markdown rules) |
| [`src/sql/00-create-database.sql`](src/sql/00-create-database.sql) | SQL Server only: database `ContosoCopilot` and the login `copilot_demo_analyst` (password is a sqlcmd variable) |
| [`src/sql/01-contoso-copilot.sql`](src/sql/01-contoso-copilot.sql) | Schema + 10 customers, 8 products, 30 orders, 58 order lines, view `Reporting.MonthlyRevenue`. Runs on SQL Server and Azure SQL Database |
| [`src/sql/02-copilot-user.sql`](src/sql/02-copilot-user.sql) | `GHCP_DB_User WITHOUT LOGIN`, select on `Sales` and `Reporting`, developer roles, `GRANT IMPERSONATE` |
| [`src/sql/03-constitution.sql`](src/sql/03-constitution.sql) | **Generated** by `python -m tsql_gate constitution sql src/CONSTITUTION.md --database ContosoCopilot` (a test checks it is current) |
| [`src/sql/04-verify-copilot-user.sql`](src/sql/04-verify-copilot-user.sql) | Run as the developer: `EXECUTE AS USER`, permission list, the UPDATE that must fail with error 229, a rolled-back write as the developer |
| [`src/sql/99-teardown.sql`](src/sql/99-teardown.sql) | Drops the database and the login |
| [`src/queries/q01-q04*.sql`](src/queries) | Reference answers: top customers, monthly revenue by category, customers without orders, email columns |
| [`src/reference_db.py`](src/reference_db.py) | Runs seed + reference queries locally on DuckDB (T-SQL transpiled by sqlglot); `--write-expected` |
| [`src/samples/`](src/samples) | `safe-examples.sql` (gate passes) and `risky-examples.sql` (hand-written, one risk per batch) |
| [`expected/`](expected) | Expected results of the four reference queries (header case differs from SQL Server's for `q04`: DuckDB lower-cases) |
| [`tests/`](tests) | 61 pytest tests |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (14 scenes, about 870 words) and shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/11-copilot-for-sql-ssms-and-azure-sql
python3 -m pip install --user --break-system-packages -r src/requirements.txt   # sqlglot, duckdb, pytest
python3 -m pytest -q                                                          # 61 passed
cd src
python3 -m tsql_gate check samples/risky-examples.sql --mode readwrite          # exit code 2 (BLOCK)
python3 -m tsql_gate check queries/q01-top-customers.sql                        # no findings, exit code 0
python3 -m tsql_gate constitution lint CONSTITUTION.md
python3 reference_db.py                                                         # reference query results
```

Verified here: pytest **61 passed** (Python 3.13, sqlglot 30.33, DuckDB 2.0). **Not verified here, needs SQL Server
or Azure (see `demo.md`)**: every `.sql` file against a real SQL Server (the build machine has no Docker; the files are
parsed with sqlglot's T-SQL dialect and the seed + queries are *executed* on DuckDB, which proves the data and the
queries, not SQL Server's behaviour), the `EXECUTE AS` / error 229 proof, the constitution being honoured by SSMS, and
everything Copilot says.

### What the gate reports

| Rule | Severity | Meaning |
|---|---|---|
| `TG-W001` | BLOCK (read-only) | Write, DDL, backup/restore, DBCC, KILL, SHUTDOWN, RECONFIGURE in read-only mode |
| `TG-W002` | BLOCK | UPDATE or DELETE without WHERE (also inside CTEs and IF blocks) |
| `TG-W003` | BLOCK / WARN | TRUNCATE; DROP without IF EXISTS (BLOCK) or with it (WARN): the constitution's own restricted operations |
| `TG-W004` | BLOCK (read-only) / WARN | `SELECT ... INTO` creates a table |
| `TG-S001` | BLOCK | `xp_*`, `sp_configure`, `sp_OA*`, `OPENROWSET`, `OPENDATASOURCE`, `OPENQUERY`, role-member procedures |
| `TG-S002` | BLOCK (read-only) / WARN | GRANT, DENY, REVOKE, EXECUTE AS, ADD/DROP MEMBER, CREATE/ALTER LOGIN, USER, ROLE, SERVER |
| `TG-D001` | BLOCK (read-only) / WARN | `EXEC (@variable)` or `sp_executesql @variable`; literal text is analysed recursively |
| `TG-E001` | BLOCK (read-only) / WARN | `EXEC` of a procedure that is not on the short read-only list (`sp_help*`, `sp_spaceused`, ...) |
| `TG-Q001` / `TG-Q002` | WARN | `SELECT *`; table without schema (both asked for by the constitution) |
| `TG-P001` | BLOCK | The batch cannot be parsed: the gate cannot prove it safe, so it fails closed |

Exit code of `check`: 0 nothing, 1 warnings, 2 at least one BLOCK. Limits you should know: the read-only procedure
list is a short allow list; statements are recognised by keyword, and keywords inside strings, comments and quoted identifiers are
ignored on purpose; T-SQL without semicolons is handled by a line heuristic (`INSERT ... SELECT` on two
lines is kept together) and anything that still does not parse is a BLOCK. **It is not a security boundary.**

## What we learned / gotchas

All from Microsoft Learn (read 21 November 2026) unless marked as ours.

- **The approval prompt is not security.** Learn says it three times: Agent mode asks approval before each query, but
  "the security boundary is SQL Server's permission enforcement, not Copilot's approval system". In Ask mode a
  classifier decides whether a query is read-only before running it; Learn adds that it "is not a security boundary".
- **Execution context.** All Copilot queries (Ask and Agent) run under the login you connected with. Copilot has no
  separate or elevated rights. A database `CONSTITUTION.md` with `agentExecuteAsUser` makes SSMS use `EXECUTE AS` for a
  chosen database user or SQL login (per database, highest precedence, `AGENTS.md` cannot override it). The signed-in
  user needs **`IMPERSONATE`** on that account; without it Copilot does not work for that user (no silent fallback).
  Do not use `sa`, `dbo` or another privileged account. Needs SSMS 22.7+.
- **The constitution is an extended property.** `sp_addextendedproperty` takes `@value` as `sql_variant`, at most
  **7,500 bytes** (Learn: sp_addextendedproperty), and `sql_variant` cannot hold `nvarchar(max)`. The lint reports a
  constitution above that size (ours is 1,476 bytes).
- **Agent mode is `READ_ONLY` by default.** Learn: changing it to `READ_WRITE` happens in the `mcp.json` file; Learn does
  not give the path of the `sql-tools` setting on the pages we read, so `demo.md` has the recorder find it. Even in
  `READ_WRITE`, SQL permissions still decide.
- **Agent mode does not inherit the active editor.** Name the server and database in the prompt. MCP servers need Agent
  mode and their tools are off until you enable them.
- **Allow always is persistent**; reset under Tools > Options > GitHub > Copilot > Tools. Cancel does not roll back
  queries that already ran.
- **Versions and plans.** Agent mode and the constitution need SSMS 22.7; completions need 22.2; chat needs 22. Latest
  release in Learn's notes on 21 Nov 2026: 22.12.1 (17 Nov 2026). Learn's SSMS pages disagree on the label: the release
  notes call SSMS 22 general availability, while the overview table and old release-note entries still say "AI assistance
  (Preview)". We say "check the version you run".
- **Copilot Free in SSMS** has a monthly chat allowance (Learn gives no number; GitHub's plans page gives none either,
  it speaks of AI credits; completions: 2,000 per month per Learn/GitHub). Not available with EMU accounts or a Copilot
  licence through an organisation. GitHub plans per its docs on 21 Nov 2026: Pro 10 USD, Business 19 USD per seat,
  Enterprise 39 USD per seat, per month.
- **Admin controls.** Copilot is disabled for SSMS **and Visual Studio together** through the Visual Studio ADMX
  templates (shared policy); to keep it in Visual Studio only, uninstall the AI Assistance workload from SSMS. Agent
  mode can be disabled separately (22.7+). MCP server allow lists and content exclusion are GitHub-side (content
  exclusion needs Copilot Business or Enterprise).
- **Azure Copilot** is the current name; the Azure SQL Learn pages still say "Microsoft Copilot in Azure". It answers
  from public documentation, dynamic management views, catalog views, Query Store and supportability diagnostics, and
  Learn warns that a question about a different database than the one on the page is "more likely to give a bad
  output". Capabilities listed today are included at no extra cost except the Observability agent (usage-based); Learn
  says future capabilities might be priced. It is not available in national clouds.
- **Fabric SQL database** has its own Copilot (chat, completions, quick actions; SSMS and VS Code connect to it too) but
  needs an F2/P1 or higher capacity: "Copilot in Microsoft Fabric isn't supported on trial SKUs". We do not demo it.
- **Azure SQL Database free offer** (the demo database): 100,000 vCore seconds, 32 GB data and 32 GB backup per month,
  up to 10 free General Purpose databases per subscription, no SLA, new database only (no restore or conversion),
  auto-pause after 15 minutes; **disconnect SSMS when you are done** or open connections keep it awake and use up the
  allowance. Choose "auto-pause at the free limit" (not "bill over usage").
- **Ours, not Learn:** the old Transparency Note (Azure OpenAI based preview) says Copilot "only has access to the
  database schema, not the data inside". Agent mode executes queries and works on their results, so assume result sets
  reach the model; Learn's SSMS pages we read do not describe retention, so the demo uses fictional data only.

## References

- Microsoft Learn, GitHub Copilot in SSMS: [overview](https://learn.microsoft.com/ssms/github-copilot/overview),
  [install](https://learn.microsoft.com/ssms/github-copilot/installation-state),
  [get started](https://learn.microsoft.com/ssms/github-copilot/get-started),
  [chat](https://learn.microsoft.com/ssms/github-copilot/chat),
  [agent mode](https://learn.microsoft.com/ssms/github-copilot/agent-mode),
  [execution context](https://learn.microsoft.com/ssms/github-copilot/execution-context),
  [admin controls](https://learn.microsoft.com/ssms/github-copilot/admin-controls),
  [MCP servers](https://learn.microsoft.com/ssms/github-copilot/mcp-servers),
  [Copilot Free](https://learn.microsoft.com/ssms/github-copilot/free-plan),
  [completions](https://learn.microsoft.com/ssms/github-copilot/code-completions),
  [SSMS 22 release notes](https://learn.microsoft.com/ssms/release-notes-22),
  [transparency note](https://learn.microsoft.com/legal/sql/ssms/transparency-note-copilot)
- Azure: [Copilot in Azure SQL Database](https://learn.microsoft.com/azure/azure-sql/copilot/copilot-azure-sql-overview),
  [sample prompts](https://learn.microsoft.com/azure/azure-sql/copilot/copilot-prompts-list),
  [What is Azure Copilot](https://learn.microsoft.com/azure/copilot/overview),
  [capabilities](https://learn.microsoft.com/azure/copilot/capabilities),
  [Azure SQL Database free offer](https://learn.microsoft.com/azure/azure-sql/database/free-offer)
- Fabric: [Copilot in the SQL database workload](https://learn.microsoft.com/fabric/database/sql/copilot-sql-database)
- T-SQL: [sp_addextendedproperty](https://learn.microsoft.com/sql/relational-databases/system-stored-procedures/sp-addextendedproperty-transact-sql)
- GitHub: [plans](https://docs.github.com/en/copilot/get-started/plans) (read 21 Nov 2026)
- This series has no devladlog.com Complete Guide; the category guides for the SQL series are linked from the SQL episodes.
