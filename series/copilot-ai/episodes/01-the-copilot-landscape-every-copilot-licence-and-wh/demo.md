# Demo shot list - Copilot & AI #1 The Copilot Landscape

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** Nothing from the Hyper-V lab (10.50.0.0/24) is used |
| Tenant | The Momento Galático lab tenant: Microsoft 365 E5 trial (25 licences, until 20 Dec 2026), Microsoft 365 Business Standard, Copilot Studio trial on `labadmin` and `sam.demo` (see `series/LAB.md`) |
| Accounts | `labadmin` (Global Administrator, the recording account) for the admin centre and the audit export; `alex.demo` (E5, **no Copilot add-on**) for the Copilot Chat screen. Passwords are typed off camera |
| Licences / purchases | **Microsoft 365 Copilot (add-on) is NOT licensed and must not be bought for this episode.** Cost of the recording: 0 |
| Azure | none; no resource group |
| Recording machine | The Windows lab laptop: Edge/Chrome (browser on the lab tenant) for the two portal screens, PowerShell 7 terminal for the audit, Python 3.10+ for Windows, `pip install -r src/requirements.txt` |
| PowerShell modules | `Install-Module Microsoft.Graph.Identity.DirectoryManagement -Scope CurrentUser` (Graph PowerShell SDK; read-only use) |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the lab tenant |
|---|---|---|
| Catalog structure, official-source rule, free/area filters | yes: 21 pytest tests | - |
| Every catalog source URL exists | yes: HTTP 200 for all Learn/GitHub URLs on 21 Nov 2026 (the microsoft.com pricing page was read with a web fetch, curl is blocked there) | - |
| Licence audit logic (add-on by part number and by service plans, suspended SKU, PascalCase and BOM input) | yes: unit tests on fixtures | - |
| Graph call `GET /subscribedSkus` with a bearer token | yes: request path and header checked against a local HTTP server (test only) | **first real call** on the lab tenant |
| `Export-SubscribedSkus.ps1` | syntax check only (PowerShell parser, 0 errors) | **run it**: `Connect-MgGraph` and `Get-MgSubscribedSku` need the tenant |
| Copilot Chat behaviour, admin centre pages | no | **record them** |

If the real tenant returns something the audit does not recognise (a new SKU part number, a renamed plan), the verdict
says "check the SKU list by hand". Note it in README "gotchas"; do not edit the fixtures to hide it.

## Prerequisites
- Lab tenant reachable; `labadmin` can sign in. Terminal: dark theme, 18 pt, window 1600x900, short prompt
  (`function prompt { 'PS> ' }`). Browser: dark theme, zoom 125 %.
- `labadmin` must be able to consent to the delegated permission `LicenseAssignment.Read.All` for Microsoft Graph
  PowerShell (Global Administrator can).
- Before recording check, as `alex.demo`, that `copilot.cloud.microsoft` opens Copilot Chat. If it shows a block page,
  something in the tenant turned it off: fix that first (admin centre, Copilot, Settings) and note it.
- Re-check every non-null price in `src/data/copilot-catalog.yaml` against its `price_source` on the recording day and
  update the file and the narration if a figure changed (Microsoft 365 Copilot add-on, GitHub plans, Security Copilot).

## Setup
1. `cd` into the episode folder, `python -m pip install -r src/requirements.txt`.
2. `python -m pytest -q` -> `21 passed` (this is also screen 4).
3. In a PowerShell terminal: `./src/scripts/Export-SubscribedSkus.ps1 -OutFile $HOME/skus.json` (the file goes to the
   home folder, **never into the repo**). Sign in as `labadmin` when the browser opens, consent when asked.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `chat-screen` | `screens/copilot-chat-work.jpg` | `copilot.cloud.microsoft` as `alex.demo`: the **Work** label under the profile, the green data protection shield, one web-grounded question (for example "What is the difference between a Copilot Studio agent and a declarative agent?") answered with source links. Mask the tenant name and the email domain |
| `licences-screen` | `screens/admin-licences.jpg` | Microsoft 365 admin center, **Billing > Licenses** as `labadmin`: Microsoft 365 E5 (trial), Microsoft 365 Business Standard, Copilot Studio trial and **no** Microsoft 365 Copilot row. Mask the tenant name |
| `audit-screen` | `screens/audit-run.jpg` | Terminal: the export line, then `python -m copilot_landscape audit --skus $HOME/skus.json` from `src/`. Must show `Microsoft 365 Copilot add-on: none`, the eligible base plans, the Copilot Studio trial line and `Verdict:`. If the real SKU list contains extra products the audit ignores, that is fine |
| `tests-screen` | `screens/tests-catalog.jpg` | Terminal in the episode folder: `python -m pytest -q` ends in `21 passed`; `cd src; python -m copilot_landscape catalog --free` lists Copilot Chat (Basic), Microsoft 365 Copilot (Basic), Azure Copilot |

## Masking notes
- Tenant name, `*.onmicrosoft.com` domain, tenant ID and the Graph token never on screen. `skus.json` contains
  `accountId` and `subscriptionIds` of the real tenant: do not `cat` it on camera, show only the audit output.
- Lab users appear only as "Alex Demo" / "Lab Admin".

## Tear-down
1. Delete `$HOME/skus.json`.
2. `Disconnect-MgGraph` (the script already does it in `finally`).
3. Optional: in Entra admin center, Enterprise applications, **Microsoft Graph Command Line Tools**, Permissions, remove
   the consent for `LicenseAssignment.Read.All` if you do not want to keep it for other episodes.
4. Nothing else was created: no Azure resources, no licence assigned, no setting changed.
