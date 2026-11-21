# Demo shot list: DEVLADLOG Power Automate #8, A GitHub issue becomes an IT request

Everything in `src/` and `tests/` already runs locally (see README). This file is for the recording session in the
**lab tenant** (DEV environment) and a **throwaway GitHub repository**. Everything below is **needs tenant** and has not
been run there yet. Every screen shows the real products: the real Power Automate, SharePoint and GitHub. The fake
GitHub and the modelled platform in `src/githubfake` are only for the automated tests and never appear on screen.

## Lab environment

No VMs, no Azure resources. Recorded on the recording laptop (lab Windows host), in a browser signed in as `labadmin`
(Power Automate, SharePoint) and, in a second browser profile, as the lab GitHub account; terminal on the same host
for `pac`.

| What | Detail | Cost |
|---|---|---|
| Power Platform environment `DEV` (exists) | Solution `GitHubIntake` with the connector, the flow, the connection references and variables | none |
| Licence | A flow that uses a custom connector needs a **premium or trial** licence (Learn, flow limits). There are no spare Power Automate Premium licences: **`labadmin` starts the self-service Power Automate Premium trial** the first time the flow is saved (say so on camera or cut it), before step 5 | none (trial) |
| SharePoint site **IT Helpdesk** with list **IT Requests** (from episodes 1 to 6; create it if missing) | Add a single-line text column **Source link** (internal name `SourceLink`); check that the **Category** choice column has the value **Other** and add it if not | none |
| GitHub | A **private throwaway repository** `it-automation-demo` in the lab GitHub account (the one used for the mg-lab repository); labels `urgent` and `hardware`; a **fine-grained personal access token**, 7-day expiry, **only this repository**, permissions **Webhooks: Read and write** and **Issues: Read and write** (Learn's tutorial lists the Webhooks one; the comment endpoint needs Issues write). The token is shown once: paste it into the connection dialog, never into a file | none |
| Users | `labadmin` owns the flow, the connector and the connections | none |
| Recording machine | Python 3 + pytest + jsonschema, `pac` CLI (sign-in off camera: `pac auth create`, never on camera) | none |

## Setup (about 45 min)

1. **Local tests first.** From the episode folder: `python -m pytest` (71 passed).
2. **IT Requests list and GitHub repo** as in the table. In the repo, create the labels. Open no issues yet.
3. **Solution and connector.** In Power Automate create the solution `GitHubIntake` (publisher `contoso`, prefix `cts`).
   Then, from `src/connector`:
   ```bash
   pac connector create --api-definition-file apiDefinition.swagger.json --api-properties-file apiProperties.json --solution-unique-name GitHubIntake
   pac connector list
   ```
   Open the connector in the portal (Edit): **General** (host `api.github.com`), **Security** (Basic authentication, labels
   come from the files), **Definition** (trigger, action, three policies). If the portal reports an error or a warning
   about the definition, note it in the README and fix the file. (Fallback if `pac connector create` fails: **Import an
   OpenAPI file** in the portal, then set the security labels and re-create the three policies by hand.)
4. **Connection.** On the connector's **Test** page (or when the flow asks), **New connection**: user name = the lab GitHub
   login, password = the token. Note what happens at creation (does it call `GetAuthenticatedUser`? README: "not verified").
   **If GitHub answers 401**, GitHub doesn't accept the token as a Basic password: change the connector to API key
   authentication (header `Authorization`, value typed as `Bearer <token>`), update `apiProperties.json`,
   `apiDefinition.swagger.json`, `connectorkit` and the tests, and say so in the README. On the Test page also call
   **Add a comment to an issue** once against a scratch issue (create issue #1 by hand) to see a 201 and the comment.
5. **Flow.** *New → Automation → Cloud flow → Automated*, build `GitHub issue to IT request` in the solution from
   `src/solution/Workflows/GitHubissuetoITrequest-…801.json`, renaming every action to the JSON names:
   - Trigger **When an issue is opened** (custom connector): Repository owner and name from the environment variables
     `cts_GitHubOwner` and `cts_GitHubRepo`. **Settings → Trigger conditions:**
     `@equals(triggerBody()?['action'], 'opened')`.
   - **Select** `Label names` (from `coalesce(triggerBody()?['issue']?['labels'], createArray())`, map `item()?['name']`),
     **Compose** `Is urgent` (`contains(body('Label names'), 'urgent')`).
   - SharePoint **Create item** `Create IT request` on `cts_HelpdeskSiteUrl` / IT Requests: Title, Category `Other`,
     Priority, Status `New`, Source link (expressions in the JSON).
   - Custom connector **Add a comment to an issue** `Comment on issue`: owner and repository from the payload's
     `repository.full_name`, issue number, comment text from the JSON.
   Do **not** turn it on yet. Add the connection references in the solution (SharePoint, Contoso IT GitHub).
6. **Export, compare, lint.**
   ```bash
   pac solution export --name GitHubIntake --path GitHubIntake.zip
   pac solution unpack --zipfile GitHubIntake.zip --folder src/solution --packagetype Unmanaged --allowWrite true --allowDelete true
   python -m flowkit lint src/solution/Workflows/*.json     # from src/: expects OK
   python -m pytest
   ```
   Compare with the README's "What was not verified here": the trigger `type` (`OpenApiConnectionWebhook`?), the connector
   id in the connection reference, the SharePoint parameter names. If they differ, keep the export, update
   `tools/build_solution.py`, the tests and the README. Replace real connector ids, site URLs and drive IDs with
   placeholders before committing.
7. **Film the ghost for real** (scene `hook` and `ping` claim it; if it doesn't happen, fix the narration). *Save as* a copy
   of the flow, **remove the trigger condition**, turn it on. GitHub creates the webhook and pings it: look at the copy's
   run history: a run for the ping, **Create IT request** with the title "[GitHub] ", **Comment on issue** failed. Then open
   an issue, edit it, and show the duplicate. Turn the copy off, check that its webhook is gone, delete the copy and delete
   the junk list items. Then turn on the original flow.
8. **Webhook lifecycle.** Turn the real flow on: GitHub → Settings → Webhooks shows one hook (events Issues, application/json)
   and Recent Deliveries with a ping (200). Record in the README: does the ping appear in the run history (as Skipped?)
   or not at all? Later, turn the flow **off** and refresh the page: **is the webhook gone?** (README: "not verified": if it
   stays, only delete removes it; fix the model, the tests, the `off` scene and the README.)

## Record (turn the flow on again after step 8)

- Open the issue **"Laptop won't boot before a client demo"** with labels `hardware` and `urgent`, as the lab GitHub account.
  Wait for the run (the webhook is a push: seconds), then the SharePoint item and the comment on the issue.
- Open a second issue without labels; edit its title: no new run.
- Optional, for the gotchas scene: create a token **without Webhooks permission** and show the 404 when turning a copy on;
  or turn on a copy of the connector without the User-Agent policy and call Test (403). Delete the copies afterwards.

## Screens to capture (match `screen` scenes in `script.yaml`)

| Scene id | File | What must be on screen |
|---|---|---|
| `connector` | `screens/connector.jpg` | Connector, Definition page: trigger and action, Policies with the three Set HTTP header policies; insert: Security page (Basic authentication, labels) |
| `webhook` | `screens/webhook.jpg` | GitHub, repo Settings, Webhooks after turning the flow on: one hook (Issues, application/json), Recent Deliveries with a ping, 200 |
| `run` | `screens/run.jpg` | Run details of the real run: trigger output (action opened, issue title), Create IT request and Comment on issue green |
| `result` | `screens/result.jpg` | Split: IT Requests list with the new item (High, New, Source link) and the GitHub issue with the comment |
| `off` | `screens/off.jpg` | Flow turned off; GitHub Webhooks page after a refresh: empty |

Code scenes (`files`, `trigger`, `unsubscribe`, `ping`, `flow`, `tests`) come from this folder; terminal output is recorded
locally with `python -m githubfake --no-condition` and `python -m pytest`.

## Masking

- `pipeline/mask.js` in the browser; `series_label: "POWER AUTOMATE"`.
- Mask the tenant name, environment URL and ID, site URLs, the connector id, the **GitHub account name** (repository
  owner, avatar, token owner) and the **callback URL** of the webhook (it carries a signature). Only the fictional lab
  users on screen; the repository name `it-automation-demo` can stay.
- Never show the token. The connection dialog masks it; crop the screenshot before the dialog closes.

## Tear-down

- Turn the flow off; check that the webhook is removed (repo Settings → Webhooks). Delete any copy of the flow.
- **Revoke the fine-grained token** in GitHub, then delete the connection in Power Automate.
- Delete the throwaway repository `it-automation-demo`.
- Delete the junk and demo items from IT Requests (keep the list; remove the Source link column only if no later episode
  uses it).
- Keep the solution `GitHubIntake` and the connector for episode 9 (ALM) or delete both (a connector is deleted from
  Custom connectors in the portal). Remove the exported zip from the recording machine.
- End or keep the Power Automate Premium trial (self-service, no cost).
