# Demo shot list: DEVLADLOG Power Automate #11, Security and data loss prevention

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | none (the Hyper-V lab is not used) |
| Power Platform | Environment **`DEV`** (exists, Dataverse). The data policy is scoped to DEV only (*Add multiple environments*). **It also applies to every other flow in DEV while it exists** (see "Before you create the policy") |
| SharePoint | Site `IT Helpdesk` with list **IT Requests** from episode 1 (Title, Category, Priority, Status). Create it from episode 1's setup if it is missing |
| Lab users | `labadmin` (Global Administrator, so it can use the Power Platform admin center and the admin PowerShell module): creates the policy, runs the scripts. `alex.demo` (Alex Demo): the maker who builds and saves the flows. Give Alex the **Environment Maker** role in DEV (PPAC → Environments → DEV → Settings → Users + permissions → Users) and membership of the IT Helpdesk site |
| Licences | **Standard connectors only** in the designer (SharePoint, MSN Weather): covered by the lab E5 licences, no premium trial. The HTTP flow (`request-asset-lookup.json`) is shown through `dlpkit` only, never built in the designer, because the HTTP action is premium. Cost 0 |
| Azure | none |
| Recording machine | The Windows lab laptop: browser with `pipeline/mask.js` (make.powerautomate.com, Power Platform admin center), **Windows PowerShell 5.1** (the admin module doesn't run on PowerShell 7, Learn), a terminal with Python 3.10+ and `pac` for the `dlpkit` captures |

Everything in `src/` and `tests/` runs locally (see README). **Needs tenant**: everything below.

## Before you create the policy (read this first)

A data policy scoped to DEV is evaluated against **every** flow in DEV. With SharePoint in Business and everything else Non-business, any flow in DEV that combines SharePoint with the **HTTP** connector (episodes 4 and 8 build such flows) or with any other non-Business connector is suspended by the background job, usually within the hour (Learn: up to 24 hours in the worst case).
- Record this episode in one session, and delete the policy in the tear-down the same day.
- Afterwards check that the flows of the other episodes are **On**. Learn: active cloud flows suspended in the previous 7 days are re-activated automatically once they no longer violate any policy; if one stays suspended, open it and save it again.
- If you prefer zero risk, create a **Trial** environment (30 days, free) and use it instead of DEV: change `scope.environments` in `src/policy/it-dev.json` and the `--environment` value in the captures.

## Setup (≈ 30 min) **needs tenant**

1. **Modules, off camera.** In Windows PowerShell 5.1 as `labadmin`'s session: `Install-Module Microsoft.PowerApps.Administration.PowerShell -Scope CurrentUser`, then `Add-PowerAppsAccount` (interactive sign-in). Nothing with credentials is typed on camera or stored in a file.
2. **Policy.** Power Platform admin center → **Security → Data and privacy → Data policy → New policy** (Learn, *Manage data policies*; the menu has moved before, search for *Data policy* if it differs). Name `MG Lab IT DEV`.
   - *Assign connectors*: move **SharePoint, Microsoft 365 Outlook, Microsoft 365 Users, Microsoft Teams, Approvals, Dataverse** to **Business** (all of them are unblockable, so there is no Block action on them). Leave everything else, including **MSN Weather** and **HTTP**, in **Non-business** (the default group stays Non-business).
   - *Define scope*: **Add multiple environments**, add **DEV** only.
   - Create the policy and note the policy GUID (the URL of the policy page, or `Get-DlpPolicy`). Never show it.
3. **Flow `IT request with weather note` (the one the scene `suspended` builds live).** As `alex.demo` in DEV: new cloud flow inside a solution `IT Guardrails` (publisher `contoso`, prefix `cts`), trigger **SharePoint → When an item is created** on IT Requests; action **MSN Weather → Get current weather** (Location `Lisbon`, Units `Metric`; creating the MSN Weather connection needs no credentials). Build it **after** the policy exists, on camera. A copy of the same flow, saved before the policy existed, is the alternative for the background-job case (not recorded).
4. **A compliant flow.** In the same solution: `Acknowledge IT request` (SharePoint trigger + Outlook *Send an email (V2)*), saved and turned **On**. It is the control: it passes with the policy in place.
5. **Export the solution for the comparison** (scene `reality`):
   ```bash
   pac auth create --name dev --environment <DEV url>      # off camera
   pac solution export --name ITGuardrails --path out/ITGuardrails.zip --overwrite
   pac solution unpack --zipfile out/ITGuardrails.zip --folder out/ITGuardrails
   ```
6. **Export the real policy** (Windows PowerShell 5.1): `.\Export-DlpPolicy.ps1 -OutFile ..\policy\exported.json -DisplayName 'MG Lab IT DEV' -ScopeMode only -ScopeEnvironments dev`. Open the file: check the field names `name`, `displayName`, `defaultConnectorsClassification`, `connectorGroups[].classification`, `connectors[].id` (the README says what we assumed), and note the id Learn doesn't give us for **HTTP**.

## Recording flow and screens (match the `screen` scenes in `script.yaml`)

| Scene id | File | What must be on screen |
|---|---|---|
| `policy` | `screens/policy.jpg` | PPAC, policy **MG Lab IT DEV**: *Assign connectors* with the six Business connectors, MSN Weather and HTTP in Non-business; then the scope step showing DEV only. Mask tenant name, environment IDs, policy GUID |
| `suspended` | `screens/suspended.jpg` | Three captures in one scene. (1) `alex.demo` in the designer with the flow `trigger → Get current weather`. (2) **Save**: the flow checker panel with the data policy message (record the exact text; README says what Learn shows). (3) *My flows* / solution view: the flow **Suspended**. Mask environment name, address bar, tenant |
| `apply` | `screens/apply.jpg` | Windows PowerShell 5.1 in `src\scripts`. Before the take, off camera, **move two connectors in the admin center** (e.g. Teams to Non-business, Approvals to Non-business) so there is something to fix. On camera: `.\Apply-DlpPolicy.ps1 -PolicyFile ..\policy\it-dev.json -WhatIf` (two `MOVE` lines and the *What if* lines), the same without `-WhatIf`, then a third run printing `Nothing to change`. Mask nothing needed unless the tenant name shows |
| `reality` | `screens/fixed.jpg` | (1) The flow fixed: delete the MSN Weather action (or, as `labadmin`, run the Apply script with a policy file that moves `shared_msnweather` to Confidential), **Save** in the designer: flow checker clean, flow turned **On**. (2) Terminal: `python -m dlpkit check out\ITGuardrails\Workflows --policy ..\policy\exported.json --environment dev` before the fix (the weather flow `SUSPENDED`, the acknowledgement `OK`), the same result the service gave |

Code scenes (`predict`, `multi`, `http`, `script`, `exfil`) are terminal and editor captures of this repo; run the commands exactly as in `script.yaml` from `src/`.
Capture `predict`, `multi`, `http` and `exfil` as the last thing, after everything above, so the outputs match the final repo.

## What to check after recording (and fix the README and script if it differs)

- The **exact flow checker message** and whether the flow is saved and marked Suspended immediately (Learn says the flow is saved and marked Suspended; the narration of `suspended` repeats it).
- Whether `Export-DlpPolicy.ps1` output has the shape `dlpkit` expects (`value[]`, `connectorGroups`, `classification` values `Confidential`/`General`/`Blocked`, `connectors[].id` like `/providers/Microsoft.PowerApps/apis/shared_...`), and whether connectors that were never moved are absent (Learn says so; `Apply-DlpPolicy.ps1` depends on it).
- The connector **ids of HTTP, HTTP Webhook and When an HTTP request is received** as `Get-DlpPolicy` returns them after you move them in the UI (README: `dlpkit` assumes `http` for the HTTP action, from Learn's endpoint-filtering example). If different, fix `connectors.py` and the test.
- That `dlpkit`'s verdicts equal the service's for the flows in `ITGuardrails` (scene `reality`, capture 2).
- Whether `Add-ConnectorsToPolicy` / `Set-DlpPolicy` run clean from the script (the Pester tests use stand-ins).

## Masking

- Run `pipeline/mask.js` in the browser; `series_label: "POWER AUTOMATE"`.
- Hide: tenant name, environment URLs and IDs, SharePoint site URLs, mailbox domains, policy GUIDs, user principal names. Terminal captures: only commands from this file; never print the output of `Get-DlpPolicy` unfiltered (it has the policy and environment IDs).

## Tear-down (same day)

1. **Delete the policy** `MG Lab IT DEV` (PPAC → Data policy → select → Delete). Check that the flows of the other episodes in DEV are On (see above).
2. Delete the solution `IT Guardrails` in DEV and its connections (MSN Weather).
3. Remove `alex.demo`'s Environment Maker role in DEV if no other episode needs it.
4. Delete `src/policy/exported.json`, `out/`, and the `pac` auth profile (`pac auth clear`). In PowerShell: `Disconnect-PowerAppsAccount` is not needed beyond closing the session.
