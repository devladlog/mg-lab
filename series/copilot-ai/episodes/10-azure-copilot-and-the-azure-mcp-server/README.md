# DEVLADLOG Copilot & AI #10 - Azure Copilot and the Azure MCP Server

Two ways to ask an AI to work with Azure, on the same small Contoso resource group:

- **Azure Copilot**, the chat in the Azure portal and the Azure mobile app (Learn: previously *Microsoft Copilot in Azure*, a name
  still found on older pages). It runs as the signed-in user.
- **The Azure MCP Server**, an open source Model Context Protocol server (`azmcp`) that MCP clients such as GitHub Copilot in
  VS Code connect to. It also runs as the signed-in user (Entra ID through the Azure Identity library, authorised by Azure RBAC).

The code answers the question an admin should ask before letting any client near the second one: **what exactly does this start
line expose, and can I prove the read-only flag removes the writes?** It is a small audit tool, run against the **real**
`azmcp` binary:

- `azmcp_audit report` reads the server's own tool catalog (`azmcp tools list`: tool names plus the annotations Learn documents:
  read only, destructive, secret, open world...) and a policy file (namespaces, read-only, accepted risks), predicts which tools a
  start line publishes and lists the exposed tools that carry a risk annotation;
- `azmcp_audit probe` starts the real server with the policy's arguments, speaks MCP over stdio (`initialize`, `tools/list`,
  optionally `tools/call`) and checks the prediction, in `--mode all` **and** in `--mode namespace` (the mode the generated
  `mcp.json` uses);
- `azmcp_audit config` writes the `.vscode/mcp.json` for a policy;
- `src/infra/main.bicep` is the disposable resource group content (storage account with a CanNotDelete lock, an RBAC key vault with
  a dummy secret, an optional Reader assignment) that both tools are asked about.

Series plan: [`../../README.md`](../../README.md). Shared lab: [`../../../LAB.md`](../../../LAB.md). Previous episodes in this series:
[3, Copilot Studio with SharePoint knowledge](../03-copilot-studio-your-first-agent-with-sharepoint-kn/) (same Contoso scenario) and
[9, Copilot in SharePoint](../09-copilot-in-sharepoint-and-sharepoint-agents/). Category episodes this builds on:
[Security and identity with Entra ID](../../../azure/episodes/04-security-identity-entra-id/) (RBAC) and
[Cost optimization](../../../azure/episodes/06-cost-optimization/). Next: episode 11, *Copilot for SQL: SSMS and Azure SQL*
(episode 14 returns to MCP servers from the GitHub Copilot side).

| Path | What it is |
|---|---|
| [`src/azmcp_audit/catalog.py`](src/azmcp_audit/catalog.py) | Parses `azmcp tools list` (or runs it); tool name = command with underscores |
| [`src/azmcp_audit/policy.py`](src/azmcp_audit/policy.py) | Policy, prediction of what a start line publishes, risk findings, start arguments, `mcp.json` |
| [`src/azmcp_audit/probe.py`](src/azmcp_audit/probe.py) | A minimal MCP stdio client (stdlib only), plus `namespace_surface` that uses `learn=true` to list commands behind namespace tools |
| [`src/azmcp_audit/cli.py`](src/azmcp_audit/cli.py) | `catalog`, `report`, `config`, `probe` |
| [`src/policies/`](src/policies) | `contoso-ops-reader.json` (7 namespaces, read-only) and `contoso-dev-writer.json` (storage, key vault, SQL, writes allowed: 16 findings) |
| [`src/samples/azmcp-4.0.0-beta.9-catalog-subset.json`](src/samples) | 78 tools (11 namespaces) cut from the real `azmcp tools list` of 4.0.0-beta.9, for offline tests |
| [`src/infra/main.bicep`](src/infra/main.bicep) | The demo resources. `bicep build` and `bicep lint` clean (Bicep CLI 0.49.2) |
| [`tests/`](tests) | 27 pytest tests: 16 offline (13 policy and catalog, 3 client), 6 against the real server, 5 for the Bicep file; a stand-in stdio server is used **only** to test the client |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (15 scenes, about 850 words) and shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/10-azure-copilot-and-the-azure-mcp-server
python3 -m pip install -r src/requirements.txt            # pytest only: the tool is standard library
# the real server, installed OUTSIDE this folder (the package is about 160 MB unpacked):
mkdir -p /tmp/azmcp && (cd /tmp/azmcp && npm init -y >/dev/null && npm install @azure/mcp@4.0.0-beta.9 --no-audit --no-fund)
export AZMCP_BIN=/tmp/azmcp/node_modules/.bin/azmcp
python3 -m pytest -q                                       # 27 passed with AZMCP_BIN; 21 passed, 6 skipped without it
cd src
python3 -m azmcp_audit report policies/contoso-ops-reader.json --catalog samples/azmcp-4.0.0-beta.9-catalog-subset.json
python3 -m azmcp_audit probe  policies/contoso-ops-reader.json --azmcp "$AZMCP_BIN"
python3 -m azmcp_audit config policies/contoso-ops-reader.json --azmcp "$AZMCP_BIN"
```

Against the tenant (needs the tenant: sign in with `az login` first; the audit tool never signs in by itself):

```bash
python3 -m azmcp_audit probe policies/contoso-ops-reader.json --azmcp "$AZMCP_BIN" --call group_list
```

Verified here (Linux container, Python 3.13, Node 22, Bicep 0.49.2, Azure MCP Server 4.0.0-beta.9, 21 November 2026): pytest
27 passed (21 passed, 6 skipped without the binary); `bicep build` and `bicep lint` clean. Starting the server and listing its
tools needs **no Azure sign-in**. Not verified without the tenant: any tool **call** against Azure, what Azure Copilot says, the
Bicep deployment itself (built, not deployed), and the VS Code and GitHub Copilot behaviour.

Measured on that build (tools published over MCP): `--mode all` 451 (448 commands plus 3 proxied Microsoft Learn tools); `--mode all
--read-only` 257 (254 read-only commands plus the 3); `--mode namespace` (the default) 74, with `--read-only` 71; `--mode
consolidated` 177 (86 with `--read-only`); `--mode single` 1 (`azure`). For the read-only policy: 36 tools in `--mode all`, and 8 namespace-level tools
publishing the same 36 commands in `--mode namespace`. `--read-only` removes `advisor_recommendation_update` in both. These are
measurements of one beta build, not documentation: re-run `catalog` and `probe` after every upgrade.

## What we learned / gotchas (Learn unless marked "measured")

- **Names.** Learn's current article is *What is Azure Copilot?*; some pages still say *Microsoft Copilot in Azure* (for example the
  Azure SQL page). Same product.
- **Azure Copilot access.** On by default for all users in a tenant; Global Administrators manage it in the *Azure Copilot admin
  center > Access management* (after elevating access): available to all, or restricted to users and groups holding the **Copilot
  for Azure User** role. Agents are enabled per agent there: GA are Troubleshooting, Deployment, Catalyst and Observability;
  Optimization and Resiliency are preview. Needs websocket access to `directline.botframework.com`; not available in Azure
  Government or 21Vianet.
- **Azure Copilot cost.** Learn: capabilities available today are included at no extra cost, except the Observability agent
  (usage-based charges); future capabilities might be priced.
- **Azure Copilot guardrails.** It sees only what the user can see, acts only with the user's permissions, and "requires confirmation
  before making changes"; it honours Azure RBAC, Privileged Identity Management, Azure Policy and resource locks. Limits: a
  conversation cannot continue beyond 24 hours; actions on more than 10 resources must be done outside Copilot; some lists show
  only the top five; sometimes a resource ID or the **Add** icon is needed instead of a name; heavy use can throttle you. Agents
  support all resource types only partly and are fully supported in English only.
- **Azure MCP Server auth and scope.** Entra ID through Azure Identity (Azure CLI, VS Code, azd, managed identity...), RBAC decides what a
  call can do. Learn: the local server is "intended strictly for developer use within your organization". The server's README warns
  that autonomous or misconfigured clients may perform destructive actions and that flags to prevent destructive operations are
  not standardised across clients: `--read-only` is enforced **in the server**, so it does not depend on the client.
- **Start options** (Learn, and `azmcp server start --help` for the extra ones): `--mode`, `--namespace` (repeatable), `--tool`,
  `--read-only`, `--transport`, `--debug`, `--disable-proxy-tools`; the `--dangerously-*` family (disable elicitation, disable HTTP
  incoming auth, disable SSRF protections...) exists and Learn says never to disable user confirmation in production.
- **Measured: Learn and `--help` disagree on modes.** Learn lists `namespace`, `consolidated`, `all`, `single`; the `--help` of
  4.0.0-beta.9 describes three, but `--mode consolidated` works (177 tools).
- **Measured: `destructive` is conservative.** In the catalog, `keyvault_secret_create`, `keyvault_key_create`,
  `storage_account_create` and other *create* tools carry `destructive=true`. Treat the annotation as "writes", not as "deletes".
- **Measured: three tools you did not ask for.** In every mode except `single` the server adds three proxied Microsoft Learn
  documentation tools (`microsoft_docs_search`, `microsoft_code_sample_search`, `microsoft_docs_fetch`) unless started with
  `--disable-proxy-tools`. The audit's `probe` passes that flag so the comparison is exact.
- **`--tool` cannot be combined with `--namespace`** (`--help`), and it switches the server to `all` mode (Learn).
- **Beta.** The npm package `@azure/mcp` is at 4.0.0-beta.9 and that is also the `latest` tag today; Learn's `mcp.json` example uses
  `@latest`, ours pins the version. Packages: npm `@azure/mcp`, NuGet `Azure.Mcp`, PyPI `msmcp-azure` (Learn).
- **Telemetry.** The server's README says telemetry can be turned off with `AZURE_MCP_COLLECT_TELEMETRY=false`. We did not change it
  in the build container and did not test the effect: decide per organisation.
- **VS Code.** Learn: the Azure MCP tools are disabled by default in supported hosts, the VS Code route needs the GitHub Copilot
  extension (a GitHub Copilot subscription), and an Azure account with RBAC roles for the resources.

## References

- What is Azure Copilot?: https://learn.microsoft.com/azure/copilot/overview
- Azure Copilot capabilities (and current limitations): https://learn.microsoft.com/azure/copilot/capabilities
- Agents in Azure Copilot: https://learn.microsoft.com/azure/copilot/agents
- Manage access to Azure Copilot: https://learn.microsoft.com/azure/copilot/manage-access
- What is the Azure MCP Server?: https://learn.microsoft.com/azure/developer/azure-mcp-server/overview
- Azure MCP Server tools (start parameters, annotations, elicitation): https://learn.microsoft.com/azure/developer/azure-mcp-server/tools/
- Get started with the Azure MCP Server: https://learn.microsoft.com/azure/developer/azure-mcp-server/get-started
- Azure MCP Server with Visual Studio Code: https://learn.microsoft.com/azure/developer/azure-mcp-server/get-started/tools/visual-studio-code
- Azure MCP Server README (vendor, GitHub): https://github.com/microsoft/mcp/blob/main/servers/Azure.Mcp.Server/README.md
- Azure built-in roles (Reader id): https://learn.microsoft.com/azure/role-based-access-control/built-in-roles
- Model Context Protocol, tool annotations: https://modelcontextprotocol.io/specification/2025-06-18/schema#toolannotations
- No devladlog.com Complete Guide exists for this series: facts above were read on Microsoft Learn on 21 November 2026.
