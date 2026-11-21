# Demo shot list - Copilot & AI #14 GitHub Copilot with MCP Servers (Learn, Azure, GitHub)

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Azure | The lab pay-as-you-go subscription. Resource group **`rg-mglab-copilot-ai-14`** (West Europe), created **empty** (no resources, no SKU, cost 0) so the Azure MCP Server has something to list; deleted in tear-down. The signed-in account needs at least Reader on the subscription (Azure RBAC decides what the server can do). Azure MCP Server runs **read only** |
| GitHub | The owner's GitHub account (same as the mg-lab repo), signed in to VS Code with a Copilot plan (**confirm the plan on the day**; no price is quoted). A throwaway repo `mglab-mcp-demo` (private is fine) with **two seeded issues**, created before and **deleted after**. The GitHub MCP server uses OAuth sign-in in the browser (no PAT, nothing typed on camera). If the account belongs to an organization with Copilot Business/Enterprise, the "MCP servers in Copilot" policy must be on |
| Microsoft Learn MCP | Public, no sign-in, no cost |
| Licences / purchases | Nothing bought. Azure: no billable resources are created. Copilot usage consumes the owner's plan allowance |
| Recording machine | Windows lab laptop: VS Code (stable, current) with GitHub Copilot, **Node.js LTS** (for `npx`), **Python 3.11+ with `python` on PATH**, Azure CLI (`az login` done before recording, off camera), Git. Terminal dark theme 18 pt, window 1600x900 |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the recording machine |
|---|---|---|
| Our server over real stdio (list tools, call tools, error paths), config checker, converter, committed `.mcp.json` equals converter output | yes: 25 passed, 1 skipped | - |
| Learn MCP endpoint lists its three read-only tools | yes: `MCP_LIVE=1` live test passed | - |
| GitHub remote endpoint exists and demands OAuth | yes: unauthenticated request returned 401 with OAuth metadata | sign in |
| Azure MCP Server start, tool list, a real call | **no** (not started; package is ~160 MB and needs Azure sign-in) | **first real run** |
| Everything in VS Code (MCP Servers page, tool approvals, answers) | no | **record it** |
| Whether VS Code discovers a workspace-root `.mcp.json` as laid out here, and whether `tools` may be omitted | no (docs say existing workspace-root `.mcp.json` files remain available) | **check first; the script assumes it works** |

## Prerequisites
- `python -m pip install -r src/requirements.txt` in the episode folder; `python -m pytest -q` -> `25 passed, 1 skipped`.
- Copy `src/` (including the hidden `.vscode`, `.github` and `.mcp.json`) to `C:\demo\mcp-demo`; do **not** copy `tests`.
  Then in that folder: `python -m pip install "mcp>=2.3,<3"` (the server needs the SDK; use a venv and start VS Code from
  it, or set the interpreter path in `.mcp.json` for the recording only).
- `python -m mcpconf check .mcp.json` -> `0 errors`, 4 notes (`tools ["*"]`).
- `az login` (labadmin or the Azure owner account), `az account show` to confirm the subscription; `az group create -n rg-mglab-copilot-ai-14 -l westeurope`.
- Throwaway repo: `gh repo create mglab-mcp-demo --private` (owner's account), two issues: "Renewal report shows wrong total" and
  "Add notice deadline to the report". Nothing else.
- Open `C:\demo\mcp-demo` in VS Code and **trust the workspace** (the docs: trusted workspace servers start without a separate prompt).
- Permission level: leave on the default **Manual**; do not use *Allow all* on camera.

## Setup
1. Chat view, new chat, Session Target **Copilot**. **Chat: Open Customizations** > **MCP Servers**: do the four servers from
   `.mcp.json` appear? If not, try enabling the Experimental setting `chat.mcp.workspaceRootConfig.enabled` and note that on
   screen; if still not, use **Add Server** (Global > Copilot Global) for the three remote/local official ones and say so in the narration.
2. Authenticate **github** (browser), start **azure** (first start downloads the npm package: do this before recording).
3. Dry run the four prompts below off camera and write down the answers, then start a fresh chat for each take.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `servers-screen` | `screens/mcp-servers.jpg` | **MCP Servers** page listing `microsoftLearn`, `azure`, `github`, `contosoVendors` with state and tool counts (the server output view for `contosoVendors` can be shown briefly). Mask GitHub account and Azure details |
| `learn-screen` | `screens/learn-call.jpg` | Agent: *Use the Microsoft Learn MCP tools to find the official documentation for the Kusto Query Language where operator. Summarize its syntax and link to the documentation. Do not change files.* Expand the tool call (name, query, result) and the final answer with its link. If there is no tool call, record that and rewrite the scene |
| `vendors-screen` | `screens/vendors-call.jpg` | Agent: *Which Contoso vendors have a notice deadline that has already passed, and what is the total yearly cost of the vendors renewing in the next 400 days? Use today's date.* Expand `list_renewals` and `total_cost` calls with arguments and JSON. Then terminal `python -m pytest tests/test_vendor_mcp_stdio.py -q` run from the episode folder in the repo (not the demo copy). Compare the answer with the tool JSON on screen |
| `azure-github-screen` | `screens/azure-github.jpg` | (1) *List my Azure resource groups.* with the tool approval prompt and its options visible, result shows `rg-mglab-copilot-ai-14`; (2) *List the open issues in mglab-mcp-demo and summarise them.* Mask subscription id, tenant id, account names |
| `readonly-gotcha` | `screens/readonly.jpg` | `github` on the `/readonly` URL: prompt *Create an issue titled mcp write test in mglab-mcp-demo.*; record what the agent does and the server's tool list. Then temporarily point the same server at `https://api.githubcopilot.com/mcp/` and show that write tools appear in the tool list (do **not** run a write; restore the file afterwards). If the agent claims it created something, stop and check the repo |

Optional extra take (not in the script): `python -m mcpconf check examples/azure-learn-sample.vscode-mcp.json` to show the warnings
on the sample printed on Learn, and `convert examples/bad.vscode-mcp.json` refusing the literal token (the `secrets` code scene shows the real output).

## Masking notes
- GitHub account/org name, avatar and email; Azure subscription id, tenant id and UPN; any path with a Windows user name (record from `C:\demo`).
- The `ghp_...` string in `examples/bad.vscode-mcp.json` is a fake pattern, not a credential; still keep it off screen if a scanner would flag it.

## Tear-down
- `az group delete -n rg-mglab-copilot-ai-14 --yes`.
- `gh repo delete mglab-mcp-demo --yes`. Revoke the GitHub OAuth authorization for VS Code MCP if it was only for the recording (GitHub Settings, Applications).
- In VS Code: **MCP: Reset Trust** (docs) and remove the demo folder `C:\demo\mcp-demo`; stop the servers.
- Confirm in the Azure cost view that nothing was billed.
