# DEVLADLOG Microsoft 365 #15 — Planner & To Do Task Management

**A plan from one file, an audit of it, and a personal focus list.** Episode 2 created the Project Falcon team and
episode 3 gave its group a life cycle; this one gives the team a plan. One file ([`src/plan.json`](src/plan.json)) drives:

1. **Plan** — `Set-PlannerPlan` creates what is missing in the group's Planner: the plan, its labels, the buckets
   and the tasks (assignees, priority, dates, labels, checklist, description, references). Existing items are never
   touched, because people edit plans by hand. `-WhatIf` lists every object first.
2. **Audit** — `Get-PlannerInventory` + `Get-PlannerFinding`: overdue (High when urgent), unassigned, no due date,
   not started for weeks, completed with open checklist items, overloaded assignees, empty buckets, plans near the
   documented limits. Markdown report.
3. **To Do** — `Sync-PlannerFocusToTodo`: the signed-in user's Planner tasks that are overdue, due this week or
   urgent become tasks in one To Do list (a linked resource carries the Planner task id); finished Planner tasks
   complete their To Do task.
4. **Etags** — `Invoke-PlannerPatch`: every Planner PATCH sends `If-Match`; on 409/412 it re-reads and retries.

Same fictional tenant as episodes 1–3 (`contoso`, Alex Demo, the Project Falcon group).

| Path | What it is |
|---|---|
| [`src/plan.json`](src/plan.json) | Plan "Project Falcon - Launch Readiness": 3 labels, 3 buckets, 8 tasks (zero-GUID group id, `contoso.com` users), audit and focus settings |
| [`src/PlannerTodo/PlannerTodo.psm1`](src/PlannerTodo/PlannerTodo.psm1) | The module: pure config/diff/body/finding/focus functions + the few that call Graph (`Invoke-MgGraphRequest`) |
| [`src/PlannerTodo/PlannerTodo.psd1`](src/PlannerTodo/PlannerTodo.psd1) | Module manifest |
| [`src/Invoke-PlannerTodo.ps1`](src/Invoke-PlannerTodo.ps1) | Runner: `-ApplyPlan [-WhatIf]`, `-Audit` (live or `-InventoryFile`), `-FocusList` (live, or offline preview with `-FocusInventoryFile -ForUser`) |
| [`tests/PlannerTodo.Tests.ps1`](tests/PlannerTodo.Tests.ps1) | 55 Pester tests (Graph mocked; 2 check our calls against the real Microsoft Graph PowerShell modules) |
| [`tests/fixtures/inventory.json`](tests/fixtures/inventory.json) | Fictional plan inventory: 8 tasks, 3 users, 4 buckets |
| [`sample/planner-audit.md`](sample/planner-audit.md) | Audit generated offline from the fictional inventory |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and the shot list for the lab recording |

## Run the tests

```bash
cd series/microsoft-365/episodes/15-planner-to-do-task-management
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Without Microsoft.Graph.Authentication / .Planner installed: Tests Passed: 53, Failed: 0, Skipped: 2
# With both installed:                                         Tests Passed: 55, Failed: 0, Skipped: 0
```

Both results were produced in this repo's container (PowerShell 7.6, Pester 6.2.0, Microsoft.Graph.Authentication and
Microsoft.Graph.Planner saved to a temp folder on `PSModulePath`). PSScriptAnalyzer (Warning and Error, Graph module
loaded) reports 0 issues on `src/`.

## Run it

```powershell
cd src
# Offline (no tenant): audit the fictional inventory -> 9 findings (1 High / 2 Medium / 4 Low / 2 Info), sample/planner-audit.md
./Invoke-PlannerTodo.ps1 -Audit -InventoryFile ../tests/fixtures/inventory.json -Now 2026-11-20T09:30:00Z -OutFile ../sample/planner-audit.md
# Offline: what would land in Riley Demo's To Do list?
./Invoke-PlannerTodo.ps1 -FocusList -FocusInventoryFile ../tests/fixtures/inventory.json -ForUser riley.demo@contoso.com -Now 2026-11-20T09:30:00Z

# Needs tenant (copy plan.json to plan.lab.json first: real group id and UPNs, never committed)
./Invoke-PlannerTodo.ps1 -PlanFile ./plan.lab.json -ApplyPlan -WhatIf     # Tasks.ReadWrite, User.ReadBasic.All
./Invoke-PlannerTodo.ps1 -PlanFile ./plan.lab.json -ApplyPlan
./Invoke-PlannerTodo.ps1 -PlanFile ./plan.lab.json -Audit -OutFile ./planner-audit.md -SaveInventory ./inventory.json   # Tasks.Read, User.ReadBasic.All
./Invoke-PlannerTodo.ps1 -PlanFile ./plan.lab.json -FocusList -WhatIf     # sign in as the user whose To Do list it is; Tasks.ReadWrite
```

## Graph calls and permissions (delegated, least privileged, from each API page)

| Operation | API | Permission |
|---|---|---|
| Find the plan in the group | `GET /groups/{id}/planner/plans` | `Tasks.Read` |
| Create the plan | `POST /planner/plans` (`container`: `containerId` + `type: group`) | `Tasks.ReadWrite`; the caller must be a **member** of the group |
| Create a bucket | `POST /planner/buckets` | `Tasks.ReadWrite` |
| List tasks of a plan / of the signed-in user | `GET /planner/plans/{id}/tasks`, `GET /me/planner/tasks` | `Tasks.Read` |
| Create a task | `POST /planner/tasks` | `Tasks.ReadWrite` |
| Description, checklist, references | `PATCH /planner/tasks/{id}/details` with `If-Match` (204, or 200 with `Prefer: return=representation`) | `Tasks.ReadWrite` |
| Labels | `PATCH /planner/plans/{id}/details` (`categoryDescriptions`) | not looked up individually; the script asks for `Tasks.ReadWrite` |
| Resolve assignees | `GET /users/{upn}?$select=id,displayName,userPrincipalName` | `User.Read` is the least privileged; the script asks for `User.ReadBasic.All` (other users, no admin consent needed per the permissions reference) |
| To Do list | `GET/POST /me/todo/lists` | `Tasks.ReadWrite` |
| To Do task | `POST /me/todo/lists/{id}/tasks`, `PATCH …/tasks/{id}` | `Tasks.ReadWrite`, **delegated only** (application: not supported) |

Application permissions exist for the Planner calls (`Tasks.ReadWrite.All`), not for creating To Do tasks.

## What we learned / gotchas

- **Every Planner POST/PATCH/DELETE wants an etag.** Learn: `PATCH` and `DELETE` need `If-Match` with the last known
  etag (`@odata.etag`); a stale or missing one is a **412**, a conflicting change a **409**, and clients are expected to
  re-read and resolve. Planner accepts an *older* etag if the change doesn't conflict with newer ones, so a retry
  after re-reading is the safe pattern; `Invoke-PlannerPatch` does it (2 retries, then it rethrows). We have **not**
  provoked a real 412 in a tenant yet (see [demo.md](demo.md)).
- **Open types are fussy.** `assignments` is keyed by the **user id** and each value needs `@odata.type`
  (`#microsoft.graph.plannerAssignment`) and `orderHint` or the API answers 400. Checklist items are keyed by a
  **GUID** (we derive it from the task title, position and text so runs are repeatable). Reference keys are URLs and
  **`.` `:` `%` `@` `#` are not allowed in a property name**, so `https://contoso.sharepoint.com/a.pptx` is sent as
  `https%3A//contoso%2Esharepoint%2Ecom/a%2Epptx`.
- **Labels are `category1`…`category25`**, defined once in the plan details (`categoryDescriptions`); a task applies
  up to **6** of them as `appliedCategories: { category1: true }`. The config uses label names and the script maps
  them to positions. Empty label slots are filled; a label somebody renamed is left alone.
- **Priority is a number**: Learn says 0–1 urgent, 2–4 important, 5–7 medium, 8–10 low, and Planner itself sets 1, 3,
  5 or 9. The config uses the names. To Do has only low / normal / high, so the focus list maps 1–4 to high.
- **Limits** (Learn, Planner limits, "can be raised or lowered without notice"): per plan 3,000 active tasks, 9,000
  tasks, 200 buckets; per task 20 assignees, 20 checklist items, 15 references; 9,000 tasks assigned to a user. The
  config loader rejects what it can know up front; the audit warns at 80 percent of the plan limits. **Learn is
  inconsistent about plans per group:** the limits page says 400, the Planner REST API page says 200 in the
  `MaximumPlannerPlans` error row. We don't rely on either number.
- **Start after due is a 400** (Learn lists it as "logically inconsistent data"), so the loader rejects it.
- **Basic plans only.** Learn: "Premium plans and tasks aren't available on the Planner API in Microsoft Graph". A
  premium plan needs Planner Plan 1 or Planner and Project Plan 3 (the lab's E5 has neither and doesn't need them).
  The Planner for admins article lists Planner in Microsoft 365 Business Basic, Business Standard and Premium (the latter two named "with Copilot"), Office 365 E1, E3 and E5, and Microsoft 365 A1.
  The Planner service description footnotes that **some Planner APIs in Graph are metered**; we call only the basic
  plan endpoints.
- **To Do is personal, and delegated.** The create-task page says application permissions are "Not supported"; the
  create-list page says `Tasks.ReadWrite.All` works. So the focus list signs in as the user whose list it is. A
  To Do task has no assignees property in Graph, which is why Planner is the place for assignment.
- **Tasks assigned in Planner already appear in To Do** (Learn, Project for the web sync page: the *Assigned to me*
  view in Planner and To Do shows all Microsoft 365 tasks assigned to the user). The focus list is a *selection*
  (overdue, this week, urgent) that the user owns and can reorder, not a copy of everything.
- **Bug we hit while testing:** an empty collection from Graph is `{ "value": [] }`. Our first `Invoke-PLGraphGet` tested
  `$null -ne $value`, but a function that returns an empty array yields `$null`, so an empty plan list was treated as
  one item and failed with *property 'title' cannot be found*. It now tests for the `value` property instead (covered
  by the mocked `Set-PlannerPlan` test).
- **Pester/PowerShell:** `ForEach-Object <propName>` under `-WhatIf` prints "What if: Retrieve…" and returns nothing;
  all pipelines in functions that support `-WhatIf` use script blocks.
- **Due dates are UTC timestamps.** Tasks get `T17:00:00Z` due and `T08:00:00Z` start, the same calendar day for users
  in Portugal. Users far from UTC may see another day; the config's `dueInDays` is relative to the run date.
- **Not verified here (needs tenant, see [demo.md](demo.md)):** a real 409/412; that chained bucket `orderHint`
  values (`"<previous hint> !"`, the documented "after the previous item" form) give the configured order; that the
  details PATCH works right after creating a task; that the To Do task list returns `linkedResources` inline (the
  code falls back to one call per task); permissions for the plan-details PATCH; whether a plan created by
  `labadmin` is immediately visible on the group's Planner tab; the per-task deep link of the new Planner (the linked
  resource points to the Planner home, `https://planner.cloud.microsoft/`, because Learn documents no per-task URL).

Related, no code needed: the Planner app in Teams shows *My Day*, *My Tasks* (with *Assigned to me*) and *My Plans*;
Teams admins manage it in the Teams admin center.

## References

- [Use the Planner REST API](https://learn.microsoft.com/graph/api/resources/planner-overview?view=graph-rest-1.0) · [Planner order hints](https://learn.microsoft.com/graph/api/resources/planner-order-hint-format?view=graph-rest-1.0)
- [Microsoft Planner limits](https://learn.microsoft.com/office365/planner/planner-limits)
- [Microsoft Planner for admins](https://learn.microsoft.com/planner/planner-for-admins) · [Planner service description](https://learn.microsoft.com/office365/servicedescriptions/microsoft-planner-service-description) · [Planner licensing](https://learn.microsoft.com/planner/licensing)
- [Create plannerPlan](https://learn.microsoft.com/graph/api/planner-post-plans?view=graph-rest-1.0) · [List plans of a group](https://learn.microsoft.com/graph/api/plannergroup-list-plans?view=graph-rest-1.0) · [plannerPlanDetails](https://learn.microsoft.com/graph/api/resources/plannerplandetails?view=graph-rest-1.0) · [plannerCategoryDescriptions](https://learn.microsoft.com/graph/api/resources/plannercategorydescriptions?view=graph-rest-1.0)
- [Create plannerBucket](https://learn.microsoft.com/graph/api/planner-post-buckets?view=graph-rest-1.0) · [plannerTask](https://learn.microsoft.com/graph/api/resources/plannertask?view=graph-rest-1.0) · [Create plannerTask](https://learn.microsoft.com/graph/api/planner-post-tasks?view=graph-rest-1.0) · [List plan tasks](https://learn.microsoft.com/graph/api/plannerplan-list-tasks?view=graph-rest-1.0) · [List user tasks](https://learn.microsoft.com/graph/api/planneruser-list-tasks?view=graph-rest-1.0)
- [plannerAssignment](https://learn.microsoft.com/graph/api/resources/plannerassignment?view=graph-rest-1.0) · [plannerAppliedCategories](https://learn.microsoft.com/graph/api/resources/plannerappliedcategories?view=graph-rest-1.0)
- [plannerTaskDetails](https://learn.microsoft.com/graph/api/resources/plannertaskdetails?view=graph-rest-1.0) · [Update plannerTaskDetails](https://learn.microsoft.com/graph/api/plannertaskdetails-update?view=graph-rest-1.0) · [plannerChecklistItem](https://learn.microsoft.com/graph/api/resources/plannerchecklistitem?view=graph-rest-1.0) · [plannerExternalReferences](https://learn.microsoft.com/graph/api/resources/plannerexternalreferences?view=graph-rest-1.0)
- [To Do API overview](https://learn.microsoft.com/graph/todo-concept-overview) · [todoTask](https://learn.microsoft.com/graph/api/resources/todotask?view=graph-rest-1.0) · [Create todoTask](https://learn.microsoft.com/graph/api/todotasklist-post-tasks?view=graph-rest-1.0) · [Create todoTaskList](https://learn.microsoft.com/graph/api/todo-post-lists?view=graph-rest-1.0) · [linkedResource](https://learn.microsoft.com/graph/api/resources/linkedresource?view=graph-rest-1.0) · [List tasks](https://learn.microsoft.com/graph/api/todotasklist-list-tasks?view=graph-rest-1.0)
- [Manage the Planner app in Teams](https://learn.microsoft.com/microsoftteams/manage-planner-app) · [Project for the web task sync with Planner and To Do](https://learn.microsoft.com/project-for-the-web/synchronize-project-web-tasks-with-planner-todo)
- Blog: [Planner & To Do Task Management — Complete Guide](https://www.devladlog.com/articles/office-365/2025-05-07-planner-todo-complete-guide-2025/)
