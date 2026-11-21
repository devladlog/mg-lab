# Demo shot list - Copilot & AI #17 Extending Microsoft 365 Copilot: Declarative Agents and API Plugins

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab is not used. The API runs on the recording laptop |
| Tenant | **Needs tenant.** The lab Microsoft 365 tenant, with the Teams setup policy **Upload custom apps** turned on for `alex.demo` (admin: Teams admin center > Teams apps > Setup policies > Global or a custom policy > *Upload custom apps*). Learn: it can take up to 24 hours to apply, so do it a day before recording |
| Accounts | `alex.demo` (member, uploads the app and chats) and the lab admin for the policy. No other user. No credentials are written in this repo: the API key is typed at the prompt off camera |
| Licences | **Nothing bought for the main path.** Learn (Microsoft 365 Copilot extensibility prerequisites): custom actions and custom instructions work in **Copilot Chat without usage-based billing**. That is what `dakit licence` reports for this agent. **NEEDS COPILOT LICENCE (optional insert):** the variant in `src/samples/declarativeAgent.with-knowledge.json` (SharePoint, email, code interpreter) needs a Microsoft 365 Copilot licence, US$30 per user per month on the Microsoft price page at the time of writing (re-check <https://www.microsoft.com/microsoft-365/copilot/business> before recording). Do not buy it for this episode; show the `licence` command output instead and say what it would unlock |
| Azure | none. No resource group, no App Service: the API is exposed by a dev tunnel |
| Recording machine | Windows or macOS laptop: Python 3.11+, `pip install -r src/requirements.txt`, the Dev Tunnels CLI (`devtunnel`, Microsoft download, user-level install), Edge or Chrome as `alex.demo`. Never run `pac auth` and do not use the Teams CLI for this episode |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the lab tenant |
|---|---|---|
| Manifests, OpenAPI, package contents | yes: `python3 -m pytest -q` -> `78 passed`; `dakit validate` 0 errors, 0 warnings | Teams accepting the zip |
| The API and its contract with `openapi.yaml` | yes: run for real (`curl` returned the Fabrikam Cloud renewal; 401 without the key) | calls arriving through the dev tunnel from Microsoft 365 |
| Licence tier of the agent | yes, from the Learn capability table via `dakit licence` | confirm that Copilot Chat (no licence) really runs the action |
| Dev Portal API key registration, upload, chat, card, confirmation | no | **record it** |

Open points to confirm on the tenant (each can change a scene):
1. That the *Upload custom apps* path is available to `alex.demo` and the zip uploads without validation errors. If the
   upload shows an error, copy the text into the script gotcha scene and fix the package.
2. Whether the Developer Portal API key page asks for a domain/base URL that matches the tunnel host, and which
   **registration id** it shows (that value goes into `--auth-id`).
3. Wording of the confirmation dialog for `createDecisionReminder` and whether the card renders in Copilot Chat.
4. Whether Copilot Chat (unlicensed) lists the agent in the agent list right after upload; if the agent only appears
   with a licence, record that as the licence finding and use the NEEDS COPILOT LICENCE insert.

## Prerequisites
- Terminal dark theme, 18 pt, window 1600x900, short prompt. Browser dark theme, 125 %.
- `cd series/copilot-ai/episodes/17-extending-microsoft-365-copilot-declarative-agents`
- `python3 -m pytest -q` -> `78 passed`.

## Setup
1. **API key registration** (Teams Developer Portal, dev.teams.microsoft.com/tools, signed in as `alex.demo`): *API key
   registration* > New. Name `Contoso Vendor API`, base URL = the tunnel URL from step 2, primary key = a random string
   you generate off camera (`python3 -c "import secrets;print(secrets.token_urlsafe(24))"`). Save and note the
   **registration id**. Never show the key.
2. **API and tunnel** (two terminals):
   ```bash
   cd src
   export VENDOR_API_KEY=<the same key>        # typed off camera, never shown
   python3 -m vendor_api --today 2026-11-21 --port 8080
   ```
   ```bash
   devtunnel user login                         # device code or browser: do this off camera
   devtunnel host -p 8080 --allow-anonymous
   ```
   Learn: the dev tunnel must allow anonymous access; that is separate from the API key, which the API still checks.
   Test: `curl https://<tunnel>/renewals` returns `401`; with the header it returns JSON.
3. **Package** with a new GUID:
   ```bash
   python3 -m dakit package agent/appPackage --out ../vendor-desk.zip \
       --app-id $(python3 -c "import uuid;print(uuid.uuid4())") \
       --api-url https://<tunnel> --auth-id <registration id> --version 1.0.0
   ```
4. **Upload:** Teams (web) > Apps > Manage your apps > *Upload an app* > *Upload a custom app* > `vendor-desk.zip`.
   Then Microsoft 365 Copilot (Copilot Chat) > Agents > *Contoso Vendor Desk*.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `tests-screen` | `screens/tests.jpg` | Terminal: `python3 -m pytest -q` -> `78 passed`, then `python3 -m dakit validate agent/appPackage` -> `0 error(s), 0 warning(s)`. Then break it on purpose (change `manifestVersion` to `1.19`) and show the error, then undo |
| `portal-screen` | `screens/portal.jpg` | Developer Portal API key registration page with the name and registration id visible; the key field blank or masked |
| `chat-screen` | `screens/chat.jpg` | Copilot Chat with the agent: *Which renewals need a decision in the next 60 days?* Expected from the real API today (2026-11-21 with `--today`): Fabrikam Cloud, decide by 2026-12-31. Keep the real wording and the card |
| `reminder-screen` | `screens/reminder.jpg` | *Remind Jordan Demo to decide on Fabrikam Cloud on 1 December 2026.* The confirmation prompt, then the answer with a reminder id like `rem-0001`; the API terminal shows the request |

Never fake the Copilot answer. If Copilot answers differently from the narration, change the narration.

Masking: tunnel hostname, tenant name in the address bar and the profile menu, the registration id if you prefer, never the
API key. The `--today 2026-11-21` flag keeps the demo dates stable.

## Tear-down
1. Stop the API and `devtunnel host` (Ctrl+C), then `devtunnel delete <tunnel id>` and `devtunnel user logout`.
2. Developer Portal: delete the API key registration.
3. Teams: Apps > Manage your apps > remove *Contoso Vendor Desk*.
4. Admin: switch the *Upload custom apps* policy back if it was not on before.
5. Delete `vendor-desk.zip` and the shell history entry with the key. Azure: nothing to delete.
