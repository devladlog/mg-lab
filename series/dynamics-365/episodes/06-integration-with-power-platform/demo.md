# Demo shot list — DEVLADLOG Dynamics 365 #6: Integration with Power Platform

Already run in the build container: `python3 -m pytest -q tests` (23 passed, Web API stubbed) and the offline
`lint`, `runs --from-json` and `settings` commands on the hand-written sample. **Nothing has run against Dataverse,
Power Automate or Teams yet: all four `screen` scenes need the lab tenant.**

## Lab environment

No VMs and no Azure resources: cloud tenant only, recorded from the browser (Power Automate, model-driven app, Teams)
and a terminal on the recording laptop.

| Item | Notes | Cost |
|---|---|---|
| Power Platform environment **`DEV`** (Dataverse, exists) | **Why DEV:** the Project Request table, the episode 5 custom API, async plug-in and `mgl_riskscore` live there, in solution `MGLabDataverse`. The Sales trial isn't needed (custom table, no Dynamics 365 app) and ends ~21 Dec 2026 | none |
| **Episode 5 deployed in DEV** | `apikit deploy` done, `apikit backfill --apply` done, Risk Score on the form. Don't run episode 5's tear-down before this episode is recorded | none |
| Microsoft Teams (E5 trial) | A team **MG Lab Finance** with a standard channel **Finance Risk**; members `labadmin`, `sam.demo` (created in setup, deleted in tear-down) | none (trial) |
| Flow owner `labadmin` with a licence covering **premium** connectors | The Microsoft Dataverse connector is Premium in Power Automate (connector reference); Teams is Standard. Learn's FAQ says every Dynamics 365 user is entitled to use Power Automate, and the lab users have the Dynamics 365 Sales trial licence; if the designer still flags the flow as premium, start the self-service **Power Automate Premium trial** for `labadmin` (LAB.md: no spare Power Apps Premium licences) | none (trial) |
| `alex.demo` | Edits PR-0004 in the app (episode 2's *Project Requester* role or equivalent read/write on Project Request) | none |
| Recording laptop | Python 3.10+ with `pip install --user -r requirements.txt`, terminal (dark, font 18+), browser with `pipeline/mask.js`, Teams web or desktop | none |

## Setup (before recording)

1. **Teams:** as `labadmin`, create team *MG Lab Finance* (private, from scratch), channel *Finance Risk*, add
   `sam.demo`. From the channel's *Get link to channel*, copy the team id (`groupId=` in the link) and the channel id
   (the `19:...@thread.tacv2` part, URL-decoded). **Verify** the two values work in the flow (step 4); note in README
   if the designer expects a different format.
2. `export DATAVERSE_URL=https://<lab DEV>.crm4.dynamics.com`, then
   `cd src && python3 -m flowkit envvars --set mgl_AlertTeamId=<team id> --set mgl_AlertChannelId=<channel id>`.
   Expected: two `+ definition ... in MGLabDataverse` and two `+ value ... (not in the solution)` lines. Check in the
   solution that the definitions are there and the values are **not** (they show in the Default Solution).
3. **Build the flow (recorded as screen 1):** make.powerautomate.com → Solutions → MGLabDataverse → New → Automation →
   Cloud flow → Automated. Name **Notify high-risk project requests**.
   - Trigger *Microsoft Dataverse — When a row is added, modified or deleted*: Change type **Added or Modified**,
     Table **Project Requests**, Scope **Organization**, Select columns **mgl_riskscore**, Filter rows
     **mgl_riskscore ge 70**.
   - *Microsoft Dataverse — Perform a bound action*: Table **Project Requests**, Action **mgl_AssessProjectRequest**,
     Row ID = *Project Request* (unique identifier) from the trigger.
   - *Microsoft Teams — Post message in a chat or channel*: Post as **Flow bot**, Post in **Channel**, Team and Channel:
     *Enter custom value* → pick the environment variables **Alert Team Id** / **Alert Channel Id** from dynamic content
     (Learn: Use environment variables in solution cloud flows). Message:
     `<request code> <name> is <RiskLevel> risk (<RiskScore>).` and a second line with `Reasons`, all from dynamic
     content.
   - Save, turn on. Check the solution now lists two **connection references** (Dataverse, Teams). If it doesn't,
     `flowkit lint` will report F040: switch the actions to connection references before going on.
4. **Smoke test off camera:** set PR-0002's budget to 80,000 with no justification, wait for the score and the Teams
   post. If the post fails (wrong ids), fix the env var value with `flowkit envvars --set ...` and run
   `flowkit restart` — and keep the failed run: it makes screen 4 more useful.
5. Reset PR-0004 to budget 42,000 (score low) so screen 3 shows the jump.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/flow-designer.jpg` — "Built in the designer, inside the solution" (**needs tenant**)
The whole flow in the designer, trigger card expanded (Select columns `mgl_riskscore`, Filter rows
`mgl_riskscore ge 70`), the bound action showing `mgl_AssessProjectRequest`, the Teams action showing the two
environment variables as Team and Channel. Mask tenant, environment, user.

### 2. `screens/flowkit-pull-lint.jpg` — "Pull and lint the real flow" (**needs tenant** for the first part)
```bash
python3 -m flowkit pull
python3 -m flowkit lint --file ../flows/notify-high-risk-project-requests.json
python3 -m flowkit lint --file ../tests/fixtures/bad-flow.clientdata.json
```
**Verify and note in README** (section "Not verified yet"), by opening the pulled JSON:
- the trigger parameter keys (with or without `subscriptionRequest/`) and the `message` value for *Added or Modified*;
- how the environment variables appear in `definition.parameters` (name format, `metadata.schemaName`?) and in the
  Teams action;
- the Teams action parameter keys for team and channel.
If lint reports anything on the real flow, show it and explain it (or fix the rule if it's a false positive, then
replace `sample/notify-high-risk.clientdata.json` with a masked copy of the real export and rerun the tests).

### 3. `screens/teams-alert.jpg` — "End to end: from a save to a Teams message" (**needs tenant**)
As **Alex Demo** in the Project Requests app: PR-0004, Budget 42,000 → 75,000, Business Justification empty, save.
Then Teams as Lab Admin or Sam Demo: the Flow bot post in *Finance Risk* — "PR-0004 ... is High risk (NN)." and the
reasons line. Expect a delay: async plug-in, then the flow trigger. Main image: the Teams message; optional inset: the
form after the save. Use the real score in the narration.

### 4. `screens/flowkit-runs.jpg` — "The lab's run history" (**needs tenant**)
```bash
python3 -m flowkit runs --days 7
```
Expected: the runs from setup step 4 and screen 3 (Success, maybe one Failed with its error code). **Verify** that
`_workflow_value eq <id>` returns rows; if not, switch to `workflowid eq '<id>'` and note it. If nothing comes back
at all, check `FlowRunTimeToLiveInSeconds` on the organization (0 = ingestion off).
Off camera, for the ALM scene: `python3 -m flowkit settings --out ../flows/test-settings.json` then `--check` on it
(expected: 4 problems until a test environment's values are filled in). Don't commit that file if it contains real ids.

## Masking checklist
- Environment URL, org name, tenant name, user UPNs and avatars (terminal, Power Automate, app, Teams).
- Team and channel ids in the terminal (`envvars --set` line and pulled JSON): blur them. The Teams channel link also
  contains the tenant id: never paste it into a file in the repo.
- Only fictional data (episode 1 records) and lab users on screen.

## Tear-down
1. Turn off and delete the flow *Notify high-risk project requests* from the solution; delete its two connection
   references (and the connections, if created only for this demo).
2. Delete the environment variable values (Default Solution) and definitions (MGLabDataverse).
3. Delete the Teams team *MG Lab Finance*.
4. If no later episode uses them: episode 5's `python3 -m apikit remove` (and its other tear-down steps), and delete
   the `mgl_riskscore` column.
5. Restore PR-0002 and PR-0004 budgets (episode 1 values).
6. If the Power Automate Premium trial was started only for this, let it expire (no action needed).
