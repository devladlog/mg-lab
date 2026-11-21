# DEVLADLOG Dynamics 365 #6 — Integration with Power Platform

The **Project Request** table from episodes 1–5 meets Power Automate and Microsoft Teams. A solution cloud flow,
*Notify high-risk project requests*, built in the designer (no code):

```
Dataverse: row modified, Select columns mgl_riskscore, Filter rows mgl_riskscore ge 70
  └─ Perform a bound action: mgl_AssessProjectRequest (the custom API from episode 5) -> RiskScore, RiskLevel, Reasons
       └─ Teams: Post message in a chat or channel (Flow bot), team + channel from environment variables
```

The score comes from episode 5's asynchronous plug-in, which writes `mgl_riskscore` only when it changes; the
threshold 70 is where its rules call a request *High*. And **flowkit**, a Python tool for the parts the designer
doesn't give you:

- **envvars**: creates the environment variable definitions *in* the solution and sets values *outside* it
- **pull**: reads the flow's `clientdata` from the `workflow` table and saves it as pretty JSON for source control
- **lint**: checks the definition for the mistakes that bite Dataverse flows (self-triggering updates, lookup or
  primary-key columns in *Select columns*, direct connections instead of connection references, undeclared parameters,
  hard-coded Teams ids, a threshold that disagrees with the plug-in)
- **runs**: run history from the Dataverse `FlowRun` table (status, duration, error codes)
- **settings**: the deployment settings file (Learn's shape, same as `pac solution create-settings`) and a check that
  refuses empty values before an unattended import
- **connrefs** and **restart** (turn the flow off and on after an environment variable value changes)

| Path | What it is |
|---|---|
| [`flow.json`](flow.json) | Flow name, table, lookup columns, watched column and threshold, custom API, connectors, environment variables |
| [`src/flowkit/definition.py`](src/flowkit/definition.py) | `clientdata` parser (walks into If/Switch/Scope/Foreach), summary, the lint rules F001–F071 |
| [`src/flowkit/envvars.py`](src/flowkit/envvars.py) | Definitions with `MSCRM.SolutionUniqueName`, values without; type codes from the Learn table reference |
| [`src/flowkit/runs.py`](src/flowkit/runs.py) | Find the flow (`category eq 5`), query `flowruns` by `_workflow_value`, summarize |
| [`src/flowkit/settings.py`](src/flowkit/settings.py) | Deployment settings build + check |
| [`src/flowkit/cli.py`](src/flowkit/cli.py) | `python -m flowkit envvars | pull | lint | runs | settings | connrefs | restart` |
| [`src/flowkit/webapi.py`](src/flowkit/webapi.py), [`auth.py`](src/flowkit/auth.py) | Web API client and MSAL token provider, as in episodes 1–5 |
| [`sample/notify-high-risk.clientdata.json`](sample/notify-high-risk.clientdata.json) | **Hand-written** clientdata of the flow, in Learn's `clientdata` shape (see note) |
| [`tests/fixtures/bad-flow.clientdata.json`](tests/fixtures/bad-flow.clientdata.json) | The same flow broken on purpose: trips every lint rule |
| [`sample/flowruns.json`](sample/flowruns.json) | 5 fictional FlowRun rows for the offline `runs` |
| [`tests/`](tests/) | 23 pytest tests; the Web API is a recording stub |

> **About the sample flow.** Its overall shape (`properties.connectionReferences`, `properties.definition` with
> `OpenApiConnection` actions, `host.operationId`, `parameters`) follows Learn's *Work with cloud flows using code*
> example and the connector reference operation ids (`SubscribeWebhookTrigger`, `PerformBoundAction`,
> `UpdateOnlyRecord`, `PostMessageToConversation`). The exact parameter keys the designer writes (for example
> `subscriptionRequest/filteringattributes`, `body/recipient/groupId`) and the way environment variables appear in
> `definition.parameters` are **not documented on Learn**; the linter matches trigger keys by their last segment and
> environment variables by `metadata.schemaName` or a `(schema)` suffix to be tolerant. demo.md pulls the real flow
> and lints it; if anything differs, the sample and the rules get fixed from the real export.

## Run and test (no tenant)

```bash
cd series/dynamics-365/episodes/06-integration-with-power-platform
python3 -m pip install --user -r requirements.txt
python3 -m pytest -q tests                                                   # 23 passed
cd src
python3 -m flowkit lint --file ../sample/notify-high-risk.clientdata.json    # 0 error(s), 0 warning(s)
python3 -m flowkit lint --file ../tests/fixtures/bad-flow.clientdata.json    # exit 1
python3 -m flowkit runs --from-json ../sample/flowruns.json
python3 -m flowkit settings --file ../sample/notify-high-risk.clientdata.json --out /tmp/test-settings.json
python3 -m flowkit settings --file ../sample/notify-high-risk.clientdata.json --check /tmp/test-settings.json   # 4 problem(s)
```
```
ERROR   F011  lookup columns in Select columns never trigger the flow: mgl_customeraccountid
WARNING F012  mgl_projectrequestid is in every update: Select columns would match all updates
WARNING F030  filter rows uses mgl_riskscore ge 60 but the plug-in calls a score High from 70
WARNING F060  Post_to_the_risk_channel: groupId is a literal; use an environment variable so test and production post to their own channel
ERROR   F020  Condition/else/Mark_as_notified updates mgl_riskscore on mgl_projectrequests, which the trigger watches: the flow triggers itself
ERROR   F040  connection shared_teams is not a connection reference: the solution won't carry it to another environment
ERROR   F050  parameters('Alert Channel (mgl_AlertChannel)') is used but not declared in the definition
INFO    F051  environment variable mgl_AlertTeamId isn't used by this flow
4 error(s), 3 warning(s)
```

## Against an environment (needs tenant)

Prerequisites: episode 5 deployed in `DEV` (custom API, async step, `mgl_riskscore` backfilled), the flow built as in
[demo.md](demo.md). The identity needs System Customizer (env vars, workflow read) and read on `flowrun`.

```bash
export DATAVERSE_URL=https://<org>.crm4.dynamics.com
cd src
python3 -m flowkit envvars --set mgl_AlertTeamId=<team id> --set mgl_AlertChannelId=<channel id>
python3 -m flowkit pull                     # -> ../flows/notify-high-risk-project-requests.json
python3 -m flowkit lint                     # pull + lint
python3 -m flowkit connrefs
python3 -m flowkit runs --days 7
python3 -m flowkit settings --out ../flows/test-settings.json     # fill values, then:
python3 -m flowkit settings --file ../flows/notify-high-risk-project-requests.json --check ../flows/test-settings.json
python3 -m flowkit restart                  # after changing an env var value in place
```

## What we learned / gotchas

- **Select columns fire even when the value is the same.** Learn: the flow triggers when any listed column is part of
  the update, regardless of whether data changed. Episode 5's plug-in compares with a post-image and writes the score
  only when it moves; otherwise every budget edit would re-send the same Teams message.
- **Lookup columns in Select columns never trigger the flow**, and the primary key is in every update (Learn). Lint
  rules F011 and F012.
- **The Dataverse connector only performs actions** (Learn: custom APIs). A custom API meant for flows must be an
  Action; ours is, by design, since episode 5.
- **Flows are Dataverse rows.** Solution flows are in the `workflow` table (`category` 5) with the definition in
  `clientdata`; flows under *My Flows* can't be managed with code (Learn). `pull` + `lint` work only for solution flows.
- **Environment variable values stay out of the solution.** Learn's FAQ: include the definition, provide the value for
  each environment at deployment. `envvars` creates definitions with `MSCRM.SolutionUniqueName` and values without it
  (a test checks the header), and the values travel in the deployment settings file.
- **Changing a value in place doesn't reach running flows.** Learn: flows keep the previous value until the flow is
  saved or turned off and on (and publishing can take up to an hour). `envvars` says so when it changes a value;
  `restart` PATCHes `statecode` 0 then 1, as in Learn's update example.
- **Deployment settings file**: `EnvironmentVariables` (`SchemaName`, `Value`) and `ConnectionReferences`
  (`LogicalName`, `ConnectionId`, `ConnectorId`), as Learn shows; empty values have to be filled for the target
  environment. During import, connections must be owned by (or shared with) the owner of the connection references.
- **Run history in Dataverse is for solution flows only**, kept 28 days by default (`FlowRunTimeToLiveInSeconds` on the
  organization); writing it doesn't count against request limits, reading it does (Learn). If the environment ran
  short of storage, ingestion may be off (TTL 0); `runs` says where to look when it finds nothing.
- **Limits:** the Microsoft Dataverse connector is *Premium* in Power Automate and the Microsoft Teams connector is
  *Standard* (connector reference). Teams allows 25 non-GET requests per connection per 300 seconds for Flow bot
  operations: a bulk import that pushes many requests over 70 at once would be throttled. Batch or summarize instead.
- **Not verified yet** (marked in demo.md): the exact trigger parameter keys and `message` value the designer writes,
  how environment variables appear in `definition.parameters`, whether the designer creates connection references
  automatically in the solution (lint F040 tells), and the `_workflow_value` filter on `flowruns` (the table also has a
  `workflowid` text column).

## References
- [Work with cloud flows using code](https://learn.microsoft.com/power-automate/manage-flows-with-code) (workflow table, category 5, clientdata, update statecode, My Flows not supported)
- [Trigger flows when a row is added, modified, or deleted](https://learn.microsoft.com/power-automate/dataverse/create-update-delete-trigger) (select columns, lookups, primary key, filter rows)
- [Microsoft Dataverse connector reference](https://learn.microsoft.com/connectors/commondataserviceforapps/) (SubscribeWebhookTrigger, PerformBoundAction, UpdateOnlyRecord; Premium)
- [Microsoft Teams connector reference](https://learn.microsoft.com/connectors/teams/) (PostMessageToConversation; Flow bot throttling; Standard)
- [Create and use custom APIs](https://learn.microsoft.com/power-apps/developer/data-platform/custom-api) (the Dataverse connector only performs actions)
- [Use environment variables in Power Automate solution cloud flows](https://learn.microsoft.com/power-apps/maker/data-platform/environmentvariables-power-automate) (limitation: old value until saved or turned off and on)
- [Environment variables overview](https://learn.microsoft.com/power-apps/maker/data-platform/environmentvariables) (definition vs value, don't ship the value, up to an hour)
- [Environment variable definition](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/environmentvariabledefinition) and [value](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/environmentvariablevalue) table references (type codes, EnvironmentVariableDefinitionId)
- [Pre-populate connection references and environment variables for automated deployments](https://learn.microsoft.com/power-platform/alm/conn-ref-env-variables-build-tools) (deployment settings file)
- [pac solution create-settings](https://learn.microsoft.com/power-platform/developer/cli/reference/solution#pac-solution-create-settings)
- [Manage cloud flow run history in Dataverse](https://learn.microsoft.com/power-automate/dataverse/cloud-flow-run-metadata) and [FlowRun table](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/flowrun)
- [Connection reference table](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/connectionreference)
- [Replace classic Microsoft Dataverse workflows with flows](https://learn.microsoft.com/power-automate/replace-workflows-with-flows) (every Dynamics 365 user is entitled to use Power Automate — FAQ)
- Blog: [Integration with Power Platform — Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-11-06-integration-with-power-platform-complete-guide-2025/)
