# 13 · Copilot Studio agents inside both apps

One Copilot Studio agent, *Inspection Assistant*, grounded on the ContosoInspections Dataverse tables and a SharePoint library of inspection
checklists, with one topic and one agent flow that creates a finding, wired into the field app (canvas, episode 11) and the back-office app
(model-driven, episode 12). Authentication is Microsoft Entra ("Authenticate with Microsoft"): every answer runs as the signed-in person.

**Honest status.** Everything under `src/` is written from Learn's documented shapes and tested **offline** (the agent itself is a test double in the
tests). Nothing was imported into Copilot Studio or run against a tenant. The lab only has the Copilot Studio **trial**, which can build and test an
agent in the test panel but **cannot publish** it, so the two embeddings (canvas and model-driven) cannot be recorded until the owner decides on
Copilot Credits or a pay-as-you-go plan. `demo.md` Part A is what the trial can show, Part B is what waits for that decision.

## What we build

| Piece | File |
|---|---|
| Agent instructions (answer only from sources, never repeat reviewer notes, confirm before writing) | [`src/agent/instructions.md`](src/agent/instructions.md) |
| Knowledge: Dataverse tables, one excluded table and column, SharePoint library (own summary format) | [`src/agent/knowledge.json`](src/agent/knowledge.json), [`src/data/column-descriptions.json`](src/data/column-descriptions.json) |
| Topic *Log a finding* (AdaptiveDialog YAML, 5 trigger phrases, yes before the write) | [`src/agent/topics/log-a-finding.mcs.yml`](src/agent/topics/log-a-finding.mcs.yml) |
| Agent flow *CreateFinding* (generated, reads option values from the shared schema) | [`src/agent/workflows/CreateFinding/`](src/agent/workflows/CreateFinding), [`src/scripts/build_workflow.py`](src/scripts/build_workflow.py) |
| Column descriptions into Dataverse (PUT full definition, `MSCRM.MergeLabels`, PublishXml; never signs in) | [`src/scripts/Set-ColumnDescriptions.ps1`](src/scripts/Set-ColumnDescriptions.ps1) |
| Three checklists for the SharePoint library: text source plus a script that builds the real Word files (no binaries in the repo) | [`src/checklists/checklists.json`](src/checklists/checklists.json), [`src/scripts/build_checklists.py`](src/scripts/build_checklists.py) |
| Canvas: formulas + *Ask the assistant* screen using the Microsoft Copilot Studio connector | [`src/app/Src/`](src/app/Src) |
| Model-driven: web resource calling `Xrm.Copilot.executeEvent` | [`src/webresource/cin_agent.js`](src/webresource/cin_agent.js) |
| The base schema, byte for byte (never redefined) | `src/schema/contosoinspections.schema.json` (copy of episode 12's) |
| Empty solution shell for the agent flow and connection references | [`src/solution/ContosoInspectionsAgent/`](src/solution/ContosoInspectionsAgent) |

## How the agent is embedded (documented routes only)

**Canvas.** Learn lists four ways. The *Copilot control* (preview) accepts Dataverse tables only and cannot use an existing agent; the custom *App Copilot*
is discontinued for new apps from 2 February 2026; *Microsoft Copilot in canvas apps* needs a Microsoft 365 Copilot licence. We use the
**Microsoft Copilot Studio connector**, action *Execute Agent and wait* (`ExecuteCopilotAsyncV2`, returns `lastResponse`), so the app controls the context it
sends: only the inspection number, the site code and the question. The connection is OAuth and per user (not shareable).

**Model-driven.** The **app assistant agent** (preview) is selected in the app designer; client scripts call `Xrm.Copilot.executeEvent(eventName, params)` (preview),
which runs a topic that listens for that event name. *Copilot chat* is a separate setting: **off by default** in Power Apps environments, On enables it. Learn calls it
a preview in Power Apps, says it is being deprecated for environments that are not enabled for Dynamics 365 apps from January 2026, and names *Microsoft Copilot* as the
replacement, which needs a Power Apps premium **and** a Microsoft 365 Copilot licence. Learn states no extra licence for the older chat but does not say whether it uses credits.

## What it costs

Rates (Learn, *Billing rates and management*), all in Copilot Credits: classic answer 1, generative answer 2, agent action 5, tenant graph grounding 10,
agent flow actions 13 per 100 actions, AI tools basic/standard/premium 0.1/1.5/10 per 1,000 tokens. Our lab: Copilot Studio **trial** on `labadmin` and `sam.demo`,
no credits, no pay-as-you-go plan. No cost figure here is measured.

## Run the tests

```bash
cd tests/python && python3 -m pytest -q                                   # 23 passed
cd tests/ContosoInspections.Agent.Tests && dotnet test -m:1               # 30 passed (Power Fx, Microsoft.PowerFx.Interpreter 1.8.1)
node --test tests/node/cin_agent.test.js                                  # 6 passed
```

Clean up afterwards: delete `bin`, `obj`, `__pycache__` and `.pytest_cache`.

What the tests prove: the topic is a valid dialog with a yes before the flow call and bindings that match the flow trigger; `workflow.json` is exactly what the generator
writes; the flow writes only real schema columns with the schema's option values and refuses closed inspections; knowledge follows Learn's limits (at most 15 tables,
Authenticate with Microsoft); the checklists build into real Word files (python-docx); the formulas and screen run on the Power Fx interpreter with a test double for the connector; the pa.yaml
files validate against Microsoft's official schema; a `pac solution pack`/`unpack` round trip of the shell works; the web resource handles short questions, missing API
and errors. What they do **not** prove: any real answer from the agent, that Copilot Studio accepts the YAML or the flow file, or the connector call shape.

## Gotchas

- **A trial cannot publish an agent** (Learn, *Licensing for agents*). Both embeddings call a published agent.
- **Dataverse knowledge needs Authenticate with Microsoft** and Dataverse search turned on; up to 15 tables; the agent uses column descriptions to match rows (Learn).
- **An agent flow used as a tool** needs the *When an agent calls the flow* trigger and *Respond to the agent*, synchronous, answering within 100 seconds, with the same outputs in every Respond.
- **The finding written by the agent has no photo.** The canvas rule asks for a photo on a failed Major or Critical item, so the flow writes `Passed = false`, prefixes the notes
  with `[Agent] ` and tells the user to add the photo in the field app.
- **Power Fx engine quirks found while testing:** `Set` inside `IfError` is swallowed (use `With` + `IfError`); `IfError(value, fallback)` takes two arguments; `Min(1, Blank())` is 1, so test `IsBlank` first.
- **YAML:** a `: ` inside a plain scalar (for example in a `HintText`) breaks the whole `pa.yaml` file; the unit tests catch it.

## Unverified

- The topic YAML and the flow JSON being accepted by Copilot Studio (shape follows Learn's VS Code extension layout; the flow GUID is a zero placeholder).
- The Power Fx call shape of `MicrosoftCopilotStudio.ExecuteCopilotAsyncV2` in Power Apps Studio (and whether `notificationUrl` must be passed).
- The event topic for `Xrm.Copilot.executeEvent` and the command-designer parameters; the API is a preview.
- Whether the trial can run the Dataverse and SharePoint knowledge sources and the agent flow at all in `DEV` (it should; not tried).
- Any credit consumption figure.

## References

- Billing rates and management (Copilot Credits): https://learn.microsoft.com/microsoft-copilot-studio/requirements-messages-management
- Licensing and the trial that cannot publish: https://learn.microsoft.com/microsoft-copilot-studio/billing-licensing
- Add Dataverse tables as a knowledge source: https://learn.microsoft.com/microsoft-copilot-studio/knowledge-add-dataverse
- Available knowledge sources (SharePoint): https://learn.microsoft.com/microsoft-copilot-studio/agents-experience/knowledge-sources-overview
- Create an agent flow as a tool: https://learn.microsoft.com/microsoft-copilot-studio/advanced-flow-create
- Agent flows FAQ: https://learn.microsoft.com/microsoft-copilot-studio/flows-faqs
- Call Copilot Studio agents from Power Automate (Execute Agent and wait): https://learn.microsoft.com/power-automate/call-copilot-studio-agent
- Connect a code app to Copilot Studio agents (`ExecuteCopilotAsyncV2` parameters and response): https://learn.microsoft.com/power-apps/developer/code-apps/how-to/connect-to-copilot-studio
- Add a Copilot control to a canvas app (preview): https://learn.microsoft.com/power-apps/maker/canvas-apps/add-ai-copilot
- Microsoft Copilot in canvas apps (preview): https://learn.microsoft.com/power-apps/maker/canvas-apps/microsoft-365-copilot-canvas-app
- Add an app assistant agent to a model-driven app (preview): https://learn.microsoft.com/power-apps/maker/model-driven-apps/add-app-assistant-agent
- Agent Xrm APIs (preview): https://learn.microsoft.com/power-apps/developer/model-driven-apps/clientapi/bring-intelligence-using-agent-apis
- executeEvent: https://learn.microsoft.com/power-apps/developer/model-driven-apps/clientapi/reference/xrm-copilot/executeevent
- Copilot chat in model-driven apps: https://learn.microsoft.com/power-apps/maker/model-driven-apps/add-ai-copilot
- Microsoft Copilot in model-driven apps: https://learn.microsoft.com/power-apps/user/use-microsoft-365-copilot-model-driven-apps
- Blog Complete Guide (model-driven apps): https://www.devladlog.com/articles/powerapps/2026-02-10-model-driven-apps-complete-guide-2026/
