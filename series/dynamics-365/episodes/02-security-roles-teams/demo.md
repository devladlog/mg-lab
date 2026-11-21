# Demo shot list — DEVLADLOG Dynamics 365 #2: Security Roles & Teams

`explain`, `who` and `audit` on the fictional Contoso model already ran in the build container (33 pytest tests).
`export` and `verify` were only tested against a stub API: **the four `screen` scenes need the lab tenant**, and the
verify narration must be rewritten to whatever Dataverse really answers.

## Prerequisites

| Item | Notes | Cost |
|---|---|---|
| Episode 1 done in MG Lab DEV | The `mgl_projectrequest` table exists (`python -m dvlab provision` + `import` from episode 1) | none |
| Two lab test users with Dataverse access | e.g. "Test User 1/2" in the lab tenant, licensed with existing lab licences or trials; no real people | none if trial |
| Recording account | System Administrator **in the lab environment** (to create BUs/roles/teams and use Check access) | none |
| Optional: one Microsoft Entra security group | For the "Sales Approvers" group team; skip if not allowed in the lab — the owner/access teams are enough | none |
| Python 3.10+ with `pip install --user -r requirements.txt` | requests, msal, pytest | none |
| Browser with `pipeline/mask.js` | For the admin center and app shots | none |

## Setup in the lab environment (before recording)

1. **Business units:** Power Platform admin center → environment → Settings → Users + permissions → Business units:
   create **Sales** (parent: root) and **Sales Portugal** (parent: Sales).
2. **Roles** (copy *Basic User* as a starting point so the app opens, then set the Project Request row):
   - **Project Requester** — Create/Read/Write/Append/Append To = User; inheritance default.
   - **Project Approver** — Read = Parent: Child BU, Write/Append/Append To = Business Unit;
     Member's privilege inheritance = *Direct User (Basic) access level and Team privileges*.
   - **PMO Team Member** — Create/Read/Write/Append/Append To/Assign = User;
     Member's privilege inheritance = **Team privileges only**.
3. **Users:** Test User 1 → business unit Sales Portugal, role Project Requester. Test User 2 → Sales Portugal,
   **no direct role**.
4. **Teams:** owner team **PMO Lisbon** (BU Sales Portugal, role PMO Team Member, member Test User 2); access team
   **PR-0004 deal room** (BU Sales Portugal, members Test User 1 and 2); optional Entra group team **Sales Approvers**
   (BU Sales, role Project Approver).
5. **Records:** assign PR-0001 to Test User 1, PR-0002 to team PMO Lisbon; share PR-0004 with the deal room access
   team (Read, Write, Append). Note the GUIDs of PR-0001 and PR-0004 (from the record URL).
6. Terminal: dark theme, font 18+, short prompt. `export DATAVERSE_URL=...`.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/role-editor.jpg` — "The same role in the security role editor" (**needs tenant**)
Security roles → **Project Approver** → Project Request row (Read = Parent: Child Business Unit, Write/Append/
Append To = Business Unit), plus the role Settings panel showing *Member's privilege inheritance*.

### 2. `screens/teams.jpg` — "Owner, access and Entra group teams" (**needs tenant**)
Users + permissions → Teams with the **Team type** column visible for PMO Lisbon (Owner), PR-0004 deal room (Access)
and Sales Approvers (Microsoft Entra Security group, if created). If no group team, drop it from the narration.

### 3. `screens/verify.jpg` — "Model versus Dataverse, live" (**needs tenant**)
```bash
cd src
python3 -m rolecheck export --table mgl_projectrequest --out ../lab.json > /dev/null   # capture only the summary line
python3 -m rolecheck verify --model ../lab.json --user "Test User 1" --record <PR-0001 guid>
python3 -m rolecheck verify --model ../lab.json --user "Test User 2" --record <PR-0004 guid>
```
Expected for Test User 2 on PR-0004: **Read = no** on both sides if Test User 2 really has no role granting Read
(the Eva gotcha, live). Record whatever Dataverse says; if a row differs, keep it in the video and explain it
(and add it to README "What we learned"). **Verify and note:** that `RetrieveRolePrivilegesRole` returns
`PrivilegeName` (otherwise the exporter falls back to the `privileges` table — check the warning output) and the
real `Depth` strings (`Basic`/`Local`/`Deep`/`Global`).

### 4. `screens/check-access.jpg` — "Check access, in the app" (**needs tenant**)
Sign in **as Test User 1** (private browser window), open PR-0004 in a model-driven app that includes the Project
Request table → command bar → **Check access**: shows how the user was granted access (expected: shared, through
the access team). Seeing *other* users' access ("who has access") needs the `IsAccessCheckerAllUsersEnabled`
environment database setting — don't change it just for the video; if it's already on, it can be shown as an admin.
Update the script's `demo` field if the capture is done this way.

## Masking checklist
- Environment URL/name, tenant name, admin account UPN and avatar.
- Only lab test users on screen; never real colleagues' names. GUIDs are environment-specific: blur if preferred.
- Never show or commit `lab.json` (real names and IDs).

## Tear-down
1. Delete `lab.json`.
2. Remove the share on PR-0004; delete the teams PR-0004 deal room, PMO Lisbon (reassign PR-0002 first) and Sales
   Approvers.
3. Remove the roles from the test users; delete the three custom roles.
4. Move the test users (and any remaining teams) back to the root business unit; **disable** Sales (this also disables
   Sales Portugal), then delete Sales Portugal first and Sales second — a business unit must be disabled before it
   can be deleted, child units go first, and deletion is irreversible
   ([Disable and delete a business unit](https://learn.microsoft.com/power-platform/admin/delete-business-unit)).
5. Delete the optional Entra group if it was created only for the recording.
