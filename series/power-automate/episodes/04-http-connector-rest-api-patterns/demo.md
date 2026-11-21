# Demo shot list: DEVLADLOG Power Automate #4, Calling a REST API that pages, throttles and fails

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | none |
| Tenant | Power Platform environment **`DEV`** (solution `Directory Checks`, environment variables incl. a Key Vault secret, one scheduled flow). **Entra**: app registration `Directory checks (lab)` with Graph `User.Read.All` (application) + a client secret (30-day expiry), deleted in tear-down |
| Lab users | `labadmin` (the recording account): maker, flow owner, grants admin consent. Directory data the flow finds (real lab users): `alex.demo` and `jordan.demo` with manager `sam.demo` (set in Entra, cleared in tear-down); **`riley.demo`** and **`taylor.demo`** without a manager (in place of "Casey Demo" / "Riley Contractor" of the mocks); a throwaway **disabled, unlicensed** user `former.demo` (created and deleted in this episode) for the "disabled is skipped" rule. Every other account without a manager also shows up (`labadmin`, `sam.demo`, the owner's own account): mask non-lab rows in run outputs and in the email |
| Recipients | Microsoft 365 groups **`purchasing-team`** (episode 2) and **`automation-admins`** (created here, member `labadmin`, deleted in tear-down) |
| Azure | Resource group **`rg-mglab-power-automate-04`** in **West Europe**: one **Key Vault** (standard, Azure RBAC) holding secret `graph-directory-checks`; pay per operation, cents. Tear-down: delete the group and purge the vault |
| Licences / trials | **Power Automate Premium** for `labadmin` (HTTP and Dataverse connectors are premium). Not in the shared lab list: use the Power Automate trial started in `DEV` if it includes premium connectors, otherwise start a Premium trial (trials run on the **Low** performance profile, see README) |
| Recording machine | The Windows lab laptop: browser (SharePoint, make.powerautomate.com, Outlook on the web for the mailboxes) with `pipeline/mask.js`; terminal with Power Platform CLI (`pac`) and Python 3 for export/unpack and the tests |

Everything in `src/` and `tests/` already runs locally (see README). This file is for the recording session in the
**lab tenant**. Everything below is **needs tenant**.

## Prerequisites

| What | Why | Cost |
|---|---|---|
| MG Lab DEV environment with Dataverse (exists) | Solution, environment variables, Dataverse unbound action | none |
| **Power Automate Premium** (Developer Plan or trial) for the maker | HTTP is a premium connector; so is Dataverse. Note: trials and the Developer Plan are on the **Low** performance profile (different default retry policy, see README) | Developer Plan: none |
| Rights to create an **app registration** and grant **admin consent** for Graph `User.Read.All` (application) | Client credentials for the HTTP action | none |
| An **Azure Key Vault** in `rg-mglab-power-automate-04` (lab subscription, West Europe), with RBAC so Power Platform can read the secret (see "Use environment variables for Azure Key Vault secrets") | Secret environment variable | minimal (pay per operation) |
| Lab users in Entra: Alex Demo and Jordan Demo (manager Sam Demo), **Riley Demo** and **Taylor Demo without a manager**, throwaway disabled `former.demo` | Something to find | none |
| `purchasing-team` and `automation-admins` test mailboxes or groups | Recipients | none |
| Power Platform CLI + Python 3 on the recording machine | Export/unpack and re-run tests | none |

## Setup (≈ 45 min)

1. **App registration** `Directory checks (lab)`: single tenant; API permissions → Microsoft Graph → Application →
   `User.Read.All` → *Grant admin consent*. Create a client secret (short expiry, e.g. 30 days). Note the
   tenant ID and client ID (never on screen unmasked).
2. **Key Vault:** store the client secret as `graph-directory-checks`. Give the Power Platform environment access
   as described on Learn (the environment variable creation fails until it can read the vault).
3. **Solution** `Directory Checks` (unique name `DirectoryChecks`, prefix `cts`). Environment variables:
   `cts_EntraAuthority` = `https://login.microsoftonline.com`, `cts_EntraTenantId`, `cts_GraphBaseUrl` =
   `https://graph.microsoft.com`, `cts_GraphClientId`, `cts_GraphPageSize` = **2** (current value, demo only;
   default 999), `cts_GraphClientSecret` of type **Secret** → Azure Key Vault → the secret from step 2.
4. **Flow** *New → Automation → Cloud flow → Scheduled* `Users without a manager`, weekly Monday 06:30, time zone
   (UTC+00:00) Dublin, Edinburgh, Lisbon, London. Build it from
   `src/solution/Workflows/Userswithoutamanager-…401.json`, renaming every action to the JSON names:
   - `Get client secret`: Microsoft Dataverse → *Perform an unbound action* → `RetrieveEnvironmentVariableSecretValue`,
     `EnvironmentVariableName` = `cts_GraphClientSecret`; Settings → **Secure outputs** on.
   - `Get users page` (HTTP inside *Do until*): Method GET, URI = `nextLink` variable, Authentication **Active
     Directory OAuth** with the environment variables and the secret token; Settings → **Secure inputs** on,
     **Retry policy** Exponential, count 4, interval PT10S, minimum PT5S, maximum PT2M. While there, confirm the
     *Asynchronous pattern* and *Pagination* settings exist on the action (README mentions both).
   - *Do until* limits: count 100, timeout PT1H.
5. **Run it** (*Test → Manually*). Expect 4 iterations with page size 2 for 7 users (more pages if the lab has more
   users), and the report email to purchasing.
6. **Failure path (lab copy only):** set `cts_GraphPageSize` to `1000` and run: Graph should answer 400 for the
   page size (expect no retries), admins get the failure email, the run ends **Failed** with `GraphCallFailed`.
   Record Graph's actual error message in the README (the mock's message is its own). Set it back to 2.
7. **Export and test.**
   ```bash
   pac solution unpack --zipfile DirectoryChecks_1_0_0_1.zip --folder src/solution --packagetype Unmanaged --allowWrite true --allowDelete true
   python -m pytest
   ```
   Check the parameter names the designer wrote for the environment variables, the Dataverse action's parameter keys
   and `environmentvariabledefinition.xml` (README, "What was not verified here"). If they differ, keep the export
   and update `tests/conftest.py` (`Harness.params`) and the README. Make sure the export contains **no secret value**
   (`grep -ri secret src/solution` should only show names), and no real tenant or client ID: replace them with the
   zero GUIDs before committing.

## Screens to capture (match `screen` scenes in `script.yaml`)

| Scene id | File | What must be on screen |
|---|---|---|
| `app-registration` | `screens/app-registration.jpg` | API permissions: Graph `User.Read.All`, Application, granted; Certificates & secrets with the secret description and expiry only |
| `env-vars` | `screens/env-vars.jpg` | Directory Checks solution → environment variables, the six variables, the secret one showing type Secret / Azure Key Vault |
| `run-paging` | `screens/run-paging.jpg` | Run details: Do until with 4 iterations, `Get users page` with the lock and hidden inputs, `Get client secret` with hidden outputs |
| `email` | `screens/report-email.jpg` | The report in the purchasing-team mailbox: subject with the count, the Name/Mail/Department table |

Code scenes (`auth`, `loop`, `retry`, `retry-tests`, `failure`, `gotcha`, `tests`) come from this folder; the
`retry-tests` terminal output is recorded locally with `python -m mockgraph --throttle-page 2` (README).

## Masking

- `pipeline/mask.js` in the browser; `series_label: "POWER AUTOMATE"`.
- Mask the tenant name, **tenant ID, client ID, object IDs, Key Vault name and path**, and every real address;
  only the test users on screen. Never show the secret value, not even in the Key Vault portal.
- Graph returns real user IDs in run outputs: keep output panels collapsed or masked.

## Tear-down

- Delete the client secret (or the whole app registration) and the Key Vault secret after recording.
- Turn the flow off; set `cts_GraphPageSize` back to its default.
- Delete `rg-mglab-power-automate-04` and purge the vault; delete `former.demo` and the `automation-admins` group;
  clear the managers set for this episode (Alex Demo, Jordan Demo).
