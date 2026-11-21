# Demo shot list — DEVLADLOG Dynamics 365 #1: Dataverse Deep Dive

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure | none |
| Tenant environment | Power Platform environment **`DEV`** (Dataverse; Dynamics 365 apps not required, so not the Sales trial). Solution `MGLabDataverse`, publisher prefix `mgl`, option value prefix `72700` (created in setup); table `mgl_projectrequest` with 18 imported records (deleted in tear-down unless episodes 2–4 are next) |
| Lab users | `labadmin` (the recording account) with **System Customizer** in `DEV`, interactive sign-in. Optional: an app registration + application user with System Customizer for the scripted runs (deleted in tear-down) |
| Licences / trials | none beyond the lab licences; cost 0 |
| Recording machine | The Windows lab laptop: maker portal / model-driven app in the browser with `pipeline/mask.js`; WSL (Ubuntu) bash with Python 3.10+ (`pip install --user -r requirements.txt`) |

Everything in `src/` and `tests/` already ran in the build container against the in-memory stand-in
(`pytest`: 41 passed; `python -m dvlab all --fake`). Nothing has run against a real environment yet:
**every `screen` scene below needs the lab tenant**, and its narration must be checked against what really appears.

## Prerequisites

| Item | Notes | Cost |
|---|---|---|
| MG Lab DEV environment with Dataverse (exists) | Any Dataverse environment works; Dynamics 365 apps not required | none |
| Solution `MGLabDataverse`, publisher prefix `mgl`, option value prefix `72700` | Create in make.powerapps.com → Solutions → New solution (new publisher if `mgl` doesn't exist) | none |
| Identity | Either `labadmin` with System Customizer + the right to create tables, or an app registration + **application user** in the environment with System Customizer. Don't record with a Global Administrator account | none |
| Python 3.10+ with `pip install --user -r requirements.txt` | requests, msal, pytest | none |
| Browser with `pipeline/mask.js` | For the maker portal shot | none |

## Setup (before recording)

1. `cd series/dynamics-365/episodes/01-dataverse-deep-dive && python3 -m pytest -q tests` → `41 passed`.
2. `export DATAVERSE_URL=https://<lab-env>.crm4.dynamics.com` (and the three `AZURE_*` variables if using the app user).
3. Terminal: dark theme, font 18+, ~1600×900, short prompt (`PS1='$ '`). Don't `echo` the environment URL.
4. Make sure the table **doesn't exist yet** (fresh run shows the key status polling). If it exists from a rehearsal,
   delete the table in the solution first (see tear-down).

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/provision.jpg` — "Provisioned in the lab, inside a solution" (**needs tenant**)
```bash
cd src && python3 -m dvlab provision --solution MGLabDataverse
```
Capture the full output: created table, 4 columns, the lookup, the alternate key, the `key index status:` lines
(note how many polls it took and whether `Pending` or `InProgress` appeared — put the real values in the narration),
`ready: upsert by mgl_requestcode is safe now`.
**Verify and note in README if different:** the key status values the real API returns (`Pending`/`InProgress`/
`Active` strings), and whether `POST .../Keys` returns 204 with `OData-EntityId` (it's what the Python SDK expects).

### 2. `screens/maker-keys.jpg` — "Same table in the maker portal" (**needs tenant**)
make.powerapps.com → Solutions → MGLabDataverse → Project Request → **Keys**: "Request Code", status Active.
Optional B-roll: Columns page (Budget, Due Date, Priority, Request Code, Customer Account).
Mask tenant/environment name in the header and the account menu.

### 3. `screens/import.jpg` — "Run it twice: still eighteen records" (**needs tenant**)
```bash
python3 -m dvlab import
python3 -m dvlab import
```
Capture both summaries. Expected: `SKIPPED 'PR/0019'`, `FAILED PR-0018: HTTP 400 <server message>`,
`19/21 rows upserted into 18 records`. **Replace the server message in narration/README with the real one.**
Then the Project Requests list (model-driven app or the table's data view in the maker portal) with 18 rows.
**Verify:** that the real service rejects the negative budget because of the money column's `MinValue: 0`.
If it doesn't, change the sample row or the narration — don't claim it.

### 4. `screens/report.jpg` — "The paged report against the lab" (**needs tenant**)
```bash
python3 -m dvlab report --page-size 5
```
Expected `page 1: 5 rows`, `page 2: 5 rows`, `10 requests with budget >= 50,000`, priority labels High/Normal.

Optional (not in the script): `python3 -m dvlab all --fake --throttle-every 7` shows the 429 handling offline.
Real 429s are not provoked against the lab on purpose (it would degrade a shared environment).

## Masking checklist
- Environment URL / org name in the terminal and the browser address bar.
- Tenant name, user UPN and avatar in the maker portal header.
- Never print tokens or the `AZURE_CLIENT_SECRET`; don't show `env` output.
- All data in the CSV is fictional.

## Tear-down
1. In the solution: delete the **Project Request** table (this removes the columns, the lookup relationship and the
   alternate key with it). Deleting the key first while its index job is pending cancels the job.
2. Optionally delete the `MGLabDataverse` solution (it's unmanaged; deleting it doesn't delete components already removed).
3. If an app registration/application user was created only for the recording, remove the application user from the
   environment and delete the client secret.
