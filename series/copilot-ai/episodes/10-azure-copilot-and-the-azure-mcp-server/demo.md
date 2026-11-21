# Demo shot list - Copilot & AI #10 Azure Copilot and the Azure MCP Server

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Tenant | Momento Galático lab tenant, with the single pay-as-you-go Azure subscription (Owner: `labadmin`) |
| Accounts | `labadmin` (Owner on the subscription, the recording account). `sam.demo` gets the **Reader** role on the resource group only (the Bicep parameter `readerObjectId`; take his object id from the Entra admin center, never write it in the repo) |
| Azure resources | One resource group `rg-mglab-copilot-10`, **West Europe**, deployed from `src/infra/main.bicep`: **storage account** `Standard_LRS`, StorageV2, Hot (estimated a few cents per day with no data); **CanNotDelete lock** on it (free); **key vault**, Standard SKU, Azure RBAC, one dummy secret (billed per operation, estimated well under 1 cent for the whole recording); optional **Reader role assignment** (free). No compute, no network, no paid tier. **Estimated cost for the recording window (24 h): under 0.10 euro, an estimate: check the Azure pricing pages for Storage and Key Vault before deploying.** Budget `mglab-monthly` (30 euros) already alerts at 50, 80, 100 percent |
| Licences / purchases | **Azure Copilot: nothing to buy.** Learn (*What is Azure Copilot?*): the capabilities available today are included at no extra cost, except the Observability agent (usage-based charges: **do not use it**). It is on by default for all users in the tenant; if the Copilot icon shows an *unauthorized* message, a Global Administrator must enable it in the *Azure Copilot admin center > Access management* (Learn: elevate access first). **Do not elevate access without the owner's OK**; ask the owner. **GitHub Copilot** (only the `vscode` scene): the owner's GitHub account/plan; Learn lists "a GitHub Copilot subscription" as a prerequisite for the VS Code route: confirm the plan at recording and say which one |
| Network | Azure Copilot needs websocket access to `https://directline.botframework.com` (Learn): allow it on the recording laptop's network. The MCP server and the audit tool only need Azure and the npm registry |
| Recording machine | Windows lab laptop: browser profiles for `labadmin` and `sam.demo`; Azure CLI signed in with `az login` as `labadmin` (sign in on camera or off camera, never paste a password); Node 22 or later (the `@azure/mcp` package declares it); Python 3.10+; Bicep CLI (`az bicep install`); VS Code with the GitHub Copilot extension; terminal dark theme, 18 pt, window 1600x900 |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the lab tenant |
|---|---|---|
| Real `azmcp` 4.0.0-beta.9: tool catalog, `--mode` variants, `--read-only`, `--namespace`, `learn=true` | yes: started the real binary, 27 pytest tests (6 of them against it), counts in the README | - |
| MCP client (`initialize`, `tools/list`, `tools/call`) | yes: `initialize` and `tools/list` against the real server; `tools/call` only against a stand-in used for tests | **a real `tools/call`** (`group_list`) needs `az login` |
| `main.bicep` | `bicep build` and `bicep lint` clean, 5 tests check the properties the episode needs | **the deployment**, the lock, the vault secret and the Reader assignment |
| Everything Azure Copilot says or does; VS Code and GitHub Copilot behaviour | no | **record it** |
| Windows: running the tool with the npm shim | no (Linux only) | pass `--azmcp "node <path>/node_modules/@azure/mcp/index.js"` if `azmcp.cmd` does not start from Python |

Open points to confirm on the tenant (each can change a scene):
1. Whether Azure Copilot is available to `labadmin` by default, and whether the **Agents** menu shows (Learn: gradual rollout).
2. The real wording and behaviour when Azure Copilot is asked to delete the **locked** storage account, and when `sam.demo` (Reader)
   asks. Learn says it asks for confirmation and respects locks and RBAC; the exact messages are not documented.
3. Whether Advisor has any cost recommendation for a brand-new, almost empty resource group (probably none: say so).
4. Whether `azmcp.cmd` starts from Python's `subprocess` on Windows (the tool was only run on Linux). Fallback in the table above.
5. Whether the VS Code `mcp.json` route prompts for confirmation before `keyvault_secret_get`; the Learn tools page documents
   elicitation for Key Vault secrets.

## Prerequisites
- `cd series/copilot-ai/episodes/10-azure-copilot-and-the-azure-mcp-server`
- `python -m pip install -r src/requirements.txt`
- The server, installed **outside** the repo: `mkdir %TEMP%\azmcp && cd %TEMP%\azmcp && npm init -y && npm install @azure/mcp@4.0.0-beta.9` (about 160 MB unpacked per platform package).
  Set `AZMCP_BIN` to `%TEMP%\azmcp\node_modules\.bin\azmcp.cmd` (or the `node ...\index.js` form) and run `python -m pytest -q` -> `27 passed`.

## Setup (the day before)
1. `az login` as `labadmin`, then `az account set --subscription <lab subscription>`.
2. `az group create --name rg-mglab-copilot-10 --location westeurope`
3. `az deployment group create --resource-group rg-mglab-copilot-10 --template-file src/infra/main.bicep --parameters readerObjectId=<sam.demo object id>`
   Note the two output names (storage account, key vault). Roles can take a few minutes to propagate.
4. Give `labadmin` the data-plane role on the vault so a secret read works (Owner has no data-plane access on an RBAC vault):
   `az role assignment create --assignee <labadmin object id> --role "Key Vault Secrets User" --scope <key vault resource id>`
5. In the portal as `labadmin`: confirm the Copilot icon opens Azure Copilot. Ask the two prompts of the `ask` scene once off camera
   to know the real wording. Do the same as `sam.demo` for the Reader take.
6. `python -m azmcp_audit catalog --azmcp "$AZMCP_BIN" --out out/catalog.json` once, to have the full catalog next to the screens.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `ask` | `screens/azure-copilot.jpg` | Azure portal as `labadmin`, resource group `rg-mglab-copilot-10`, Copilot pane. Prompts: *List the resources in resource group rg-mglab-copilot-10 with their SKU*, then *Show me my cost recommendations from Azure Advisor*. Real answers only; if Advisor has nothing, record that. Mask subscription id and tenant |
| `guardrails` | `screens/guardrails.jpg` | Take 1, `labadmin`: *Delete the storage account stmglab10... in rg-mglab-copilot-10* (name from the deployment output). Show the confirmation Azure Copilot asks for, then whatever the lock does. **If a confirmation appears, read it before pressing anything.** Take 2, `sam.demo` (Reader): the same request; record the refusal. Do not retake for a nicer answer |
| `probe` | `screens/probe.jpg` | Terminal in `src/`: `python -m azmcp_audit report policies/contoso-dev-writer.json --azmcp "$AZMCP_BIN"` (16 findings, with the full catalog the numbers can differ slightly from the 78-tool subset: record the real ones), then `python -m azmcp_audit probe policies/contoso-ops-reader.json --azmcp "$AZMCP_BIN"` (expect `Published 36 tool(s); the catalog predicts 36`, `Match: yes`, `Namespace mode ... same set`), then the same with `--call group_list` (real resource groups of the lab subscription; **mask the subscription id and any resource group that is not `rg-mglab-*`**). If a count differs on the day (new server version), record it and say so: the script's numbers become "at the time of recording" |
| `vscode` | `screens/vscode.jpg` | VS Code on the laptop. Folder with `.vscode/mcp.json` made by `python -m azmcp_audit config policies/contoso-ops-reader.json --azmcp "$AZMCP_BIN" > .vscode/mcp.json` (check the Windows redirect does not write a BOM: save as UTF-8). Start the server from the mcp.json CodeLens, Copilot Chat in **agent mode**: *List my resource groups*; then *Create a storage account named mglabx in rg-mglab-copilot-10* (expect: no tool). Then regenerate `mcp.json` from `contoso-dev-writer.json` and ask *Get the value of the secret demo-secret in the key vault of rg-mglab-copilot-10*: record the confirmation prompt before the (dummy) value appears. Optional: the Learn "tools" list in the Copilot tool picker showing the 36 vs 74 tools difference |

Optional extra take (not in the script): `python -m azmcp_audit probe` run with `--mode single` start line typed by hand, to show the one tool `azure`.

Masking: subscription id and tenant name everywhere (portal breadcrumb, terminal output, VS Code), key vault name if it reveals the
subscription, the `sam.demo` object id, and every address bar. Never show a password or device-code prompt; the dummy secret value is
fictional but still mask it if you reuse the vault.

## Tear-down
1. Remove the lock, then delete the group:
   `az lock delete --name lock-do-not-delete --resource-group rg-mglab-copilot-10 --resource-name <storage account> --resource-type Microsoft.Storage/storageAccounts`
   `az group delete --name rg-mglab-copilot-10 --yes`
2. The key vault is soft-deleted for 7 days (the template sets 7 and no purge protection): purge it so the name is free:
   `az keyvault purge --name <key vault> --location westeurope`
3. Check the group is gone: `az group exists --name rg-mglab-copilot-10` -> `false`. The Reader assignment goes with the group.
4. Delete the scratch install (`%TEMP%\azmcp`), the `out/` folder and the `.vscode/mcp.json` you created. Sign `sam.demo` out.
5. Check Cost Management the next day for the resource group: it should show cents or nothing.
