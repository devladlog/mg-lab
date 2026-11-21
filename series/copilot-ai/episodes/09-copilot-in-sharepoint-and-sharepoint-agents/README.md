# DEVLADLOG Copilot & AI #9 - Copilot in SharePoint and SharePoint Agents

Copilot in SharePoint reached general availability (rollout from 30 September 2026), and the agents that came before it,
`.agent` files, are being retired. Learn says existing `.agent` files **stop responding after March 2027**, and since
mid-November 2026 agents created from SharePoint are built with Copilot Agent Builder and no longer saved as a file. So this
episode is less "how to create an agent" and more "what each thing is, what it costs, and how to move your agents". It
ships a small tool for the move, on the same Contoso Vendor Management Office site as episode 3:

- `Get-AgentFileInventory.ps1` finds the `.agent` files the signed-in user can see (search, read-only) and writes a CSV;
- `agentfiles inventory` summarises it; `triage-template` writes the sheet the owners fill in; `plan` applies Learn's table of
  upgrade paths and Learn's seven prioritisation factors and counts the days left;
- `agentfiles skill-lint` checks a site skill (`SKILL.md`) before you upload it; `src/skills/vendor-intake-check/SKILL.md` is the
  sample skill (it checks vendor requests against the onboarding policy of episode 3).

Series plan: [`../../README.md`](../../README.md). Shared lab: [`../../../LAB.md`](../../../LAB.md). Previous episodes in this
series: [3, the Copilot Studio agent with SharePoint knowledge](../03-copilot-studio-your-first-agent-with-sharepoint-kn/)
(same site and policies). Category episodes this builds on:
[SharePoint permissions and governance](../../../sharepoint/episodes/05-permissions-governance/) and
[SharePoint Syntex](../../../sharepoint/episodes/10-sharepoint-syntex/). Next: episode 10, *Azure Copilot and the Azure MCP Server*.

| Path | What it is |
|---|---|
| [`src/scripts/Get-AgentFileInventory.ps1`](src/scripts/Get-AgentFileInventory.ps1) | `Submit-PnPSearchQuery -Query "FileExtension:agent" -All`, optionally limited to one site, to CSV. Needs PnP.PowerShell 3.x and your own Entra app id. Read-only |
| [`src/agentfiles/inventory.py`](src/agentfiles/inventory.py) | Reads the CSV (case-insensitive columns, several date formats), keeps only `.agent` rows, summarises by site, never viewed, no owner, stale |
| [`src/agentfiles/plan.py`](src/agentfiles/plan.py) | Triage sheet + plan: four roles to four Learn upgrade paths, seven priority factors, archive candidates, days to 31 March 2027 |
| [`src/agentfiles/skilllint.py`](src/agentfiles/skilllint.py) | Lints `SKILL.md`: front matter, name, description, encoding, lengths. Every finding names the Learn page it comes from |
| [`src/skills/vendor-intake-check/SKILL.md`](src/skills/vendor-intake-check/SKILL.md) | Sample site skill for the VMO site |
| [`src/samples/`](src/samples) | Fictional search export and triage sheet (tests and the `plan` scene only) |
| [`tests/`](tests) | 29 pytest tests, 5 of which run the PowerShell script under `pwsh` with stand-ins for the PnP cmdlets |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (16 scenes, about 850 words) and shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/09-copilot-in-sharepoint-and-sharepoint-agents
python3 -m pip install -r src/requirements.txt     # PyYAML + pytest
python3 -m pytest -q                                # 29 passed (needs pwsh for the 5 collector tests)
cd src
python3 -m agentfiles inventory samples/agent-files-export.csv
python3 -m agentfiles triage-template samples/agent-files-export.csv --out triage.csv
python3 -m agentfiles plan samples/agent-files-export.csv --triage samples/triage.csv --today 2026-11-21
python3 -m agentfiles skill-lint skills/vendor-intake-check/SKILL.md
```

Against the tenant (needs the tenant, read-only):

```powershell
./src/scripts/Get-AgentFileInventory.ps1 -TenantUrl https://<tenant>.sharepoint.com -ClientId <app id> -OutFile ./agent-files.csv
python -m agentfiles inventory agent-files.csv
```

Verified here: pytest 29 passed (Python 3.13, PowerShell 7.6). Not verified without the tenant: the first real search (that
every selected managed property is retrievable and what `Submit-PnPSearchQuery -All` returns in your PnP version: the script
accepts both `.ResultRows` and a plain list), whether Upload on the Site skills page accepts our `SKILL.md`, and anything
Copilot says or does. The lab has **no Microsoft 365 Copilot licence**, so every Copilot screen is marked in `demo.md`.

## What we learned / gotchas (all from Learn unless marked)

- **Three different things.** *Copilot in SharePoint* needs a Microsoft 365 Copilot licence; everyday capabilities are included,
  *advanced work* uses Copilot Credits through a spending policy (Microsoft 365 admin center > Copilot > Cost management >
  Add spending policy > Advanced work in SharePoint). *SharePoint agents* are `.agent` files. *Agents built with Copilot Agent
  Builder* replace them and are shared through the Copilot app.
- **Retirement.** `.agent` files work until the end of March 2027, then stop responding in SharePoint, Teams and the Copilot
  app; the Agent Link web part and the immersive viewer stop giving access. Microsoft does not upgrade them for you. The
  preview PowerShell availability controls (`KnowledgeAgentScope` and friends) were honoured only until 1 November 2026.
- **Four upgrade paths**, chosen by what the agent does: answers questions about the site (use Copilot in SharePoint), repeatable
  task (convert to a skill with `convert-agent-file-to-skill`, rolling out from mid-November 2026), named Q and A used elsewhere
  (Agent Builder: Upgrade to Microsoft 365 agent), Copilot Studio custom engine agent (publish to the Copilot app, do not rebuild).
  The Agent Chat web part is announced on the roadmap as "coming soon": do not promise it.
- **Permissions do not transfer.** A `.agent` file uses SharePoint file permissions; an upgraded agent is shared at agent level
  (people, groups, email addresses, not SharePoint groups) and is private unless the file was shared with everyone in the
  organisation. Access to an agent never grants access to its knowledge sources.
- **Pay as you go for SharePoint agents applies to `.agent` files only**: one complex prompt is 12 messages (10 for tenant graph
  grounding, 2 for the generative answer), billed under the Copilot Studio meter. It does not apply to Copilot in SharePoint.
- **Inventory limits.** Search finds only the agents the signed-in user can open. The admin-wide view is the *Agent Insights*
  report (needs SharePoint Advanced Management or a Microsoft Copilot licence; built from `FileCreated` and `FileRenamed` audit
  events, up to 100 records in the admin center, 1 million downloaded) and the agent registry. We do not have either in the lab.
- **Restricted Content Discovery** on a site removes the Agent icon, Copilot in SharePoint and AI actions from it.
  Blocking an agent in the admin center currently affects only Copilot Chat, not OneDrive, SharePoint or Teams.
- **Skills.** Site skills are Markdown at `/Agent Assets/Skills/<skill-name>/SKILL.md`; the library is created when the first
  skill is created; by default Edit permission creates a skill and View permission runs it; skills cannot call external systems or
  run code and never widen permissions. Learn gives **no SharePoint-specific file schema**, which is why `skill-lint` borrows the
  documented rules of the same format from Copilot Studio, Agent Builder and Visual Studio, and says so in every message.
- **Ours, not Learn's:** the thresholds in `plan.py` (50 lifetime views is "high usage", 90 days is "no recent use", three of the
  seven factors is "high" priority) and treating 31 March 2027 as the planning date. They are parameters.

## References

- Get started with Copilot in SharePoint: https://learn.microsoft.com/sharepoint/copilot-in-sharepoint-get-started
- Upgrade agents in SharePoint and OneDrive: https://learn.microsoft.com/sharepoint/upgrade-sharepoint-agents
- Extend Copilot in SharePoint with skills: https://learn.microsoft.com/sharepoint/copilot-in-sharepoint-skills
- Manage access to agents in SharePoint: https://learn.microsoft.com/sharepoint/manage-access-agents-in-sharepoint
- Use agents with pay-as-you-go billing: https://learn.microsoft.com/sharepoint/sharepoint-agents-azure-billing
- Monitor agent usage in SharePoint: https://learn.microsoft.com/sharepoint/monitor-agent-usage
- Insights report on agents in SharePoint: https://learn.microsoft.com/sharepoint/insights-on-sharepoint-agents
- Copilot Studio, add and manage an uploaded skill (rules reused by `skill-lint`): https://learn.microsoft.com/microsoft-copilot-studio/agents-experience/skills-add-existing
- Agent Builder, add skills: https://learn.microsoft.com/plugins/agent-builder-add-skills
- Agent Skills in Visual Studio (name and description limits): https://learn.microsoft.com/visualstudio/ide/copilot-agent-skills
- Managed properties (ViewsLifeTime, ViewsRecent, CreatedBy; SharePoint Server reference): https://learn.microsoft.com/sharepoint/technical-reference/crawled-and-managed-properties-overview
- PnP PowerShell `Submit-PnPSearchQuery`: https://pnp.github.io/powershell/cmdlets/Submit-PnPSearchQuery.html
- No devladlog.com Complete Guide exists for this series: every fact above was read on Microsoft Learn on 21 November 2026.
