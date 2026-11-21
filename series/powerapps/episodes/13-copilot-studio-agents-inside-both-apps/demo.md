# Demo shot list — DEVLADLOG Power Apps #13, Copilot Studio agents inside both apps

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure | none (no resource group, no Azure resource; `rg-mglab-powerapps-13` is **not** used) |
| Tenant environment | Power Platform environment **`DEV`** (Dataverse, **not** a Developer environment) with the solution *Contoso Inspections* from episodes 11 and 12 already imported and seeded (`INS-01000` to `INS-01007`). Created here: one Copilot Studio agent *Inspection Assistant*, one agent flow *CreateFinding* (in a new solution *Contoso Inspections Agent*), one SharePoint site with a library *Inspection checklists*, column descriptions on 12 columns. Part B adds the Microsoft Copilot Studio connection, one canvas screen and one model-driven command |
| Lab users | `labadmin` builds the agent and the flow. `alex.demo` runs the canvas app (Part B). `sam.demo` runs the model-driven app (Part B). Both need a Power Apps premium trial (self-service) for the apps from episodes 11 and 12 |
| Licences / trials | **Copilot Studio trial** on `labadmin` and `sam.demo` (already assigned). **A trial cannot publish an agent** (Learn: *Licensing for agents*), so **Part A runs on the trial; Part B cannot run until the owner decides** on Copilot Credits capacity or a pay-as-you-go plan (not set today, see `series/LAB.md`). Cost today: 0. Cost after the decision: see "Credits" below |
| Recording machine | Windows lab laptop: Copilot Studio, Power Apps Studio, the admin center and the running apps in the browser (run `pipeline/mask.js`; `sam.demo` and `alex.demo` in InPrivate windows); WSL terminal with Python 3, .NET 8 SDK, Node 22 and `pac` for the **offline** checks only |

Everything under `src/` and `tests/` was built and tested locally: `cd tests/python && python3 -m pytest -q` (23 passed),
`cd tests/ContosoInspections.Agent.Tests && dotnet test -m:1` (30 passed), `node --test tests/node/cin_agent.test.js` (6 passed).
**Every step below marked "needs tenant" has never been run.** In particular the topic YAML and the flow `workflow.json` were
written from Learn's documented shapes and checked offline only; nothing was imported into Copilot Studio.

Never run `pac auth` for this episode. The only script that talks to Dataverse takes a token you pass in.

## Credits (say this honestly on camera)

Rates from Learn (*Billing rates and management*): classic answer 1, generative answer 2, agent action 5, agent flow actions 13
per 100 actions (all Copilot Credits). Example for the recording: one question answered from knowledge is 2 credits; "log a finding"
is about 5 per action step plus a fraction of one flow action. A full demo of 30 questions and 5 findings is well under 300
credits (an estimate, not a measurement: read the real figure in the Power Platform admin center after the run).
Learn does not say whether test-panel turns draw credits in a trial, so do not quote a number from this file: read the real
consumption in the Power Platform admin center after the run and say what it shows.

## Prerequisites

| What | Notes | Cost |
|---|---|---|
| Episodes 11 and 12 solutions in `DEV` | the agent grounds on `cin_inspection`, `cin_inspectionitem`, `cin_site` | existing |
| Dataverse search turned on in `DEV` | admin center > Environments > DEV > Settings > Product > Features; Learn: Dataverse knowledge needs it | 0 |
| `labadmin` with System Customizer (or Admin) and the Copilot Studio trial | to create the agent, flow and descriptions | trial |
| A SharePoint site `mglab-inspections` | create it in the browser on the lab tenant (fictional name) | 0 |

## Setup (off camera)

1. **Local checks.** The three test commands above. Delete `bin`, `obj`, `__pycache__`, `.pytest_cache` afterwards.
2. **Checklists (needs tenant).** SharePoint site `mglab-inspections` > New > Document library *Inspection checklists* > build the three Word files with
   `python3 src/scripts/build_checklists.py --out /tmp/checklists` (needs `pip install python-docx`; fictional content) and upload them.
3. **Column descriptions (needs tenant).** Preferred: the script. `pwsh src/scripts/Set-ColumnDescriptions.ps1 -EnvironmentUrl https://<DEV url> -PlanOnly`
   prints the 12 GET/PUT lines (offline, safe to show). The real run needs a bearer token for the DEV Dataverse URL in
   `DATAVERSE_ACCESS_TOKEN` (for example `az account get-access-token --resource https://<DEV url>` after an `az login` on the recording
   laptop, off camera). Fallback with no token: type the descriptions from `src/data/column-descriptions.json` into each column in the maker portal.
   Mask the URL and the token. The descriptions never mention reviewer notes.
4. **Create the agent (needs tenant).** Copilot Studio > Create > New agent, name *Inspection Assistant*, environment `DEV`. Instructions: paste
   `src/agent/instructions.md`. Settings > Security > Authentication > **Authenticate with Microsoft** (Learn: required for Dataverse knowledge).
5. **Knowledge (needs tenant).** Add knowledge > Dataverse > tick `cin_inspection`, `cin_inspectionitem`, `cin_site` (not `cin_inspector`), name and
   description from `src/agent/knowledge.json`. Add knowledge > SharePoint > the library URL, name and description from the same file.
   Wait until both show *Ready*.
6. **Topic (needs tenant).** Topics > Add a topic > From blank, open the code editor, paste `src/agent/topics/log-a-finding.mcs.yml`. The
   flow action in it has a zero GUID: Copilot Studio rewrites it when you attach the flow in step 7, so re-attach the flow in the node.
7. **Agent flow (needs tenant).** Tools > Add a tool > New tool > Agent flow. Rebuild `CreateFinding` from `src/agent/workflows/CreateFinding/workflow.json`
   (the trigger inputs `text` to `text_4`, the nested guards, one *Add a new row* and five *Respond to the agent* with identical outputs). If you use the
   Copilot Studio extension for VS Code, the folder layout `workflows/CreateFinding/` matches its format. Respond asynchronously = **Off**. Publish.
   Attach the flow in the topic's flow node. The flow runs with `labadmin`'s connection in the lab: say so.
8. **Warm-up in the test panel.** Ask each demo question once so the knowledge is indexed and the answers are stable.

## Part A, on the trial: what to record

### Screen 1: `screens/agent-test-panel.jpg` (scene *testpanel*)

Copilot Studio > Inspection Assistant > Overview with the Knowledge section visible (Dataverse and SharePoint both *Ready*), then the test panel.
1. Ask "Which items are still open on INS-01003?" Expected: a short list, cites the inspection items table.
2. Ask "How do I check a fire door?" Expected: an answer from `checklist-fire-doors.docx`, names the file.
3. Ask "What did the reviewer write on INS-01003?" Expected: it refuses, the column is secured and is not a knowledge column.
4. Type "log a finding" and walk to the read-back. Answer **yes** on INS-01003, "Test finding", Housekeeping, Minor, "Recorded during the episode 13 demo."
   Expected: "Finding created: ..." Then open the item in the model-driven app to show the row, notes starting `[Agent] `.
5. Repeat step 4 with severity Major and notes "short". Expected: the flow refuses (notes under 10 characters), nothing written.
Mask the environment name and the avatar. Do not show the access token step.

## Part B, needs the owner's decision (published agent)

Do not record Part B on the trial: publishing is blocked, and the scenes *canvasscreen* and *mdscreen* must show the real product.
If the owner buys Copilot Credits capacity or sets a pay-as-you-go plan for `DEV`, do this. Until then ship the episode with Part A only
and keep the gotcha scene (it says exactly this).

9. **Publish** the agent (Publish > Publish). Channels are not needed for the connector. Copy nothing secret; the agent name is the schema name (`cin_InspectionAssistant`
   if Copilot Studio gave it that name, otherwise change `AgentName` in `src/app/Src/App.agent-formulas.pa.yaml` and the test that checks it).
10. **Canvas (needs tenant).** Open the episode 11 app > Data > Add data > *Microsoft Copilot Studio* connector (Standard class; sign in as `alex.demo`,
    the connection is per user and cannot be shared, Learn). Paste the formulas from `src/app/Src/App.agent-formulas.pa.yaml` into App > Formulas and add
    the screen from `src/app/Src/AgentScreen.pa.yaml` (Insert > paste code). Add a button on the inspection screen: `Navigate(AgentScreen)`.
    **Unverified:** the exact Power Fx shape of the connector call (`MicrosoftCopilotStudio.ExecuteCopilotAsyncV2(agent, {message: ...}).lastResponse`).
    Learn's code-app page lists `agentName`, `message` and a placeholder `notificationUrl` for the action; if Studio asks for `notificationUrl`, add
    `notificationUrl: "https://notificationurlplaceholder"`, and re-run the three test suites after any change to the file.
11. **Model-driven (needs tenant).** App designer > the *Inspection Back Office* app > Agents > **App assistant agent** > select *Inspection Assistant* (preview).
    In the agent add a topic that starts on the event **`Contoso.Inspections.AskAboutInspection`** (event trigger), reads `Activity.Value.question` and
    the record from `Global.PA__Copilot_Model_PageContext.pageContext.id.guid` (Learn: executeEvent), and answers from knowledge.
    Upload `src/webresource/cin_agent.js` as a web resource, then in the command designer add a command *Ask the assistant* to the Inspection main
    form, action JavaScript: library the web resource, function `cin.Agent.ask`, first parameter *PrimaryControl*, second parameter the text
    "Which items are still open on this inspection?". **Unverified:** the event topic and the exact Studio steps were never run, and `Xrm.Copilot.executeEvent`
    is a preview API.
12. **Copilot chat in the app (optional, needs the admin).** Learn (*Add Copilot for app users in model-driven apps*): the setting *Allow users to analyze data using an
    AI-powered chat experience in canvas and model-driven apps* is Off for Power Apps environments by default, and **On** enables it. The page calls it a preview in Power Apps
    and says it is being deprecated for environments not enabled for Dynamics 365 apps from January 2026, with Microsoft Copilot as the replacement; that replacement
    needs a Power Apps premium **and** a Microsoft 365 Copilot licence. The page states no extra licence for the older chat but does not say whether it uses credits:
    check the admin center before you claim it is free. Skip it if `DEV` is not Dynamics 365 enabled.

### Screen 2: `screens/canvas-agent.jpg` (scene *canvasscreen*)
Play the canvas app as `alex.demo` in an InPrivate window. Open INS-01003 > Ask the assistant. Type "Which items are still open?" > Ask. Expected: a reply.
Then type "log a finding", answer the five questions, confirm with yes: the reply starts "Finding created", the items list refreshes and the new row has notes `[Agent] ...`.
Mask the environment name and the avatar.

### Screen 3: `screens/model-driven-agent.jpg` (scene *mdscreen*)
Open the back-office app as `sam.demo` (InPrivate), open INS-01003, press **Ask the assistant**. Expected: a dialog with the answer. Mask the environment name.

## Masking notes

Environment name and URL, tenant domain, avatars, the SharePoint site URL (use `pipeline/mask.js`), bearer tokens, any connection id in the connection dialog.
The agent name `cin_InspectionAssistant` is fictional and may stay. Use only the fictional users (Alex Demo, Sam Demo).

## Tear-down

1. Unpublish or delete the agent *Inspection Assistant* and the solution *Contoso Inspections Agent* (flow, topic, connection reference).
2. Remove the *Microsoft Copilot Studio* connection (maker portal > Connections) and, in the canvas app, the data source, the `AgentScreen` screen and the added formulas.
3. In the model-driven app: remove the command, the web resource and the app assistant agent selection.
4. Delete the SharePoint site `mglab-inspections` (and empty its recycle bin).
5. Delete the finding rows created during the recording (items starting `[Agent] `) from `DEV`.
6. If you changed the Copilot setting in the admin center, set it back. Column descriptions may stay: they are harmless and also help the make portal.
7. Delete local `bin`, `obj`, `__pycache__`, `.pytest_cache`.
