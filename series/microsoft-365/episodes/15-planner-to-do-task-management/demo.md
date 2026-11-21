# Demo shot list — DEVLADLOG Microsoft 365 #15: Planner & To Do Task Management

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure / Power Platform | none |
| Tenant | Lab tenant: Planner for the web and Microsoft To Do for the web, Microsoft Graph. Creates one plan in the existing **Project Falcon** group (episode 2) and one To Do list; both are deleted in tear-down |
| Lab users | **`labadmin`** (the recording account; creates the plan and runs the audit; must be a **member** of the group, see Setup). **`alex.demo` (Alex Demo)** for the To Do screen (own browser profile, own sign-in). `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo` are assignees |
| Licences / trials | Microsoft 365 E5 trial (Planner is included in Office 365 E3/E5: Learn, Microsoft Planner for admins). **Basic plans only**: premium plans need Planner Plan 1 or Planner and Project Plan 3 and are not in the Planner API in Graph, so nothing here needs them. Cost 0 |
| Recording machine | The Windows lab laptop: PowerShell 7.2+ with `Microsoft.Graph.Authentication`, two browser profiles (labadmin, alex.demo), `pipeline/mask.js` |

Everything in `src/` and `tests/` already ran in the build container (55 Pester tests with the real Graph PowerShell
modules present, offline audit and offline focus preview from a fictional inventory). This file lists what the
human-supervised session sets up and records in the **lab tenant**. Every Graph call below is **needs tenant**, and every
screen shows the real product. `tests/fixtures/*` and `sample/*` are for the automated tests only and never appear on screen.

## Prerequisites

| Item | Notes | Cost |
|---|---|---|
| Group **Project Falcon** (episode 2/3) | Microsoft 365 group behind the Falcon team. If tear-down of episode 2 removed it, create a Microsoft 365 group with that name as `alex.demo` | none |
| `labadmin` is a **member** of the group | Learn (Create plannerPlan): when the container is a group, the user who creates the plan must be a member. Global Administrator is not enough. Add `labadmin` and the four other demo users as members (Teams: Manage team, or Entra admin center → Groups → Members) | none |
| PowerShell 7.2+ + `Microsoft.Graph.Authentication` | `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser` | none |
| Consent | Delegated scopes asked by the runner: `Tasks.ReadWrite` + `User.ReadBasic.All` (apply), `Tasks.Read` + `User.ReadBasic.All` (audit), `Tasks.ReadWrite` (focus list). If a consent prompt asks for an administrator, approve once as `labadmin` | none |
| Browser | `pipeline/mask.js` loaded for Planner and To Do | none |

## Setup (before recording)

1. Entra admin center → Groups → **Project Falcon**: copy the **Object ID**; add `labadmin`, `sam.demo`, `jordan.demo`,
   `riley.demo`, `taylor.demo` as members (Alex is the owner).
2. Copy `src/plan.json` to an uncommitted `src/plan.lab.json` and change only:
   `plan.groupId` to the Object ID; every `@contoso.com` address to the lab users' real UPNs
   (`alex.demo@…`, `sam.demo@…`, …); for the To Do screen add `alex.demo` as assignee of
   **Draft customer announcement** and **Fix the three open blocker bugs** (so Alex has three tasks in the focus window).
   Pass `-PlanFile ./plan.lab.json` to every command below.
3. Run the tests on the recording machine: `pwsh -NoProfile -Command 'Invoke-Pester ./tests'` →
   `Tests Passed: 55` (53 + 2 skipped if `Microsoft.Graph.Authentication` / `Microsoft.Graph.Planner` aren't installed).
4. Terminal: dark theme, font 18+, prompt `PS> `. First `./Invoke-PlannerTodo.ps1 -Audit` is **not** run yet.
5. Check the Planner limits page and the Planner for admins page are still as cited in README (they say the limits can change without notice).

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/apply.jpg` — "WhatIf, then build the plan" (**needs tenant**, creates a plan)
Signed in as `labadmin` (`Connect-MgGraph` happens inside the runner; use the browser device/interactive sign-in).
```powershell
cd src
./Invoke-PlannerTodo.ps1 -PlanFile ./plan.lab.json -ApplyPlan -WhatIf
./Invoke-PlannerTodo.ps1 -PlanFile ./plan.lab.json -ApplyPlan          # confirm each prompt, or answer A (Yes to all)
./Invoke-PlannerTodo.ps1 -PlanFile ./plan.lab.json -ApplyPlan          # second run: "Nothing to do"
```
Expected: `CreatePlan`, `SetLabels`, 3 × `CreateBucket`, 8 × `CreateTask`, all `Created`. Then **Planner for the web**
(planner.cloud.microsoft) → the plan **Project Falcon - Launch Readiness**: Board view grouped by bucket, one card
opened showing labels, assignees, due date and checklist. Mask the group Object ID and the tenant name.
**Check and note in README**: that the three buckets appear in the configured order (the chained `orderHint` is not
verified), and that each task's checklist and description are there (details PATCH right after create).

### 2. `screens/audit.jpg` — "The audit, live" (**needs tenant**, read-only)
First make the plan look like a real week, in Planner for the web as `labadmin` (about two minutes, show none of it):
- **Confirm launch date with sponsors**: set the due date to 5 days ago (stays at Not started, priority urgent).
- **Freeze the release branch**: set progress to Completed and leave its checklist items unchecked.
- **Retire the old landing page**: leave as it is (unassigned and without a due date in the file: `Unassigned` and `NoDueDate`).
- Optional, for `Overloaded`: set `audit.maxActivePerPerson` to 1 in `plan.lab.json` (Riley has two active tasks).
```powershell
./Invoke-PlannerTodo.ps1 -PlanFile ./plan.lab.json -Audit -OutFile ./planner-audit.md -SaveInventory ./inventory.lab.json
```
Expected rows: `Overdue` (High, names Alex Demo), `Unassigned`, `NoDueDate`, `CompletedWithOpenChecklist`, plus
`DueSoon` Info rows (and `NotStartedStale` only if the plan is older than 21 days). Show `planner-audit.md` in the editor (mask UPNs if they show the
real tenant domain). Rewrite the narration's specifics to match the screen.

### 3. `screens/todo.jpg` — "Your week, in To Do" (**needs tenant**)
Sign out of Graph (`Disconnect-MgGraph`), then sign in as `alex.demo` inside the runner (delegated, own To Do):
```powershell
./Invoke-PlannerTodo.ps1 -PlanFile ./plan.lab.json -FocusList -WhatIf
./Invoke-PlannerTodo.ps1 -PlanFile ./plan.lab.json -FocusList            # confirm
```
Expected: `CreateList  Falcon focus  Created`, then `CreateTodoTask` rows for the overdue task, the blocker bugs and
the announcement. Then **Microsoft To Do for the web** as `alex.demo`: the list **Falcon focus**, importance and due
dates; open one task and show the linked resource (**Microsoft Planner**). Then, in Planner as Alex, mark **Confirm
launch date with sponsors** complete, rerun the command: `CompleteTodoTask … Completed`, and the task is checked off
in To Do. Mask the tenant name and UPNs.
**Check and note in README** (not verified here): that `GET …/todo/lists/{id}/tasks` returns `linkedResources` inline
(the code falls back to one call per task if it does not), and how the due date (stored as 17:00 UTC) shows up in the To Do UI.

### Optional (not in the script): the etag conflict (the gotcha scene)
Only if you want a live 412: in PowerShell, `Invoke-MgGraphRequest GET` a task and keep its `@odata.etag`; change the
task title in Planner; PATCH the same title with the old `If-Match` using `Invoke-MgGraphRequest`. Learn says an older etag
can still succeed when the change does not conflict with newer ones, so use the **same property** to provoke it.
Whatever status the lab returns (409 or 412) is what goes on screen; do not claim one in the narration unless seen.

## Masking checklist
- Tenant name/domain, UPNs of the lab users, group Object ID, plan and task IDs, `inventory.lab.json` (contains user IDs).
- The browser address bar in Planner and To Do (it contains the tenant and plan IDs).

## Tear-down
1. Planner for the web → the plan → **… → Delete plan** (as `labadmin`). Deleting the group would also delete its plans
   (Learn), but the group is reused by other episodes.
2. To Do for the web as `alex.demo`: delete the list **Falcon focus**.
3. Remove `labadmin`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo` from the group if they were not members before.
4. Delete `plan.lab.json`, `inventory.lab.json`, `planner-audit.md`; `Disconnect-MgGraph`; clear the browser profiles' sign-ins.
