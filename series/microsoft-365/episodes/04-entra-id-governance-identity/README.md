# DEVLADLOG Microsoft 365 #4 — Entra ID Governance & Identity

**Identity governance as code.** One file ([`src/governance.json`](src/governance.json)) drives the three Entra ID
Governance controls that remove standing access, plus an audit:

1. **PIM** — `New-PimEligibleAssignment`: admins become **eligible and time-bound** (`roleEligibilityScheduleRequests`,
   `adminAssign`, `afterDateTime`) instead of permanently active. The config refuses permanent eligibility and
   assignments without a justification. Skips assignments that already exist.
2. **Access reviews** — `New-GuestAccessReview`: a recurring review of **guests in every Microsoft 365 group** (one
   instance per group), decided by the group **owners** with a fallback reviewer, **deny by default**, decisions
   auto-applied (denied guests are removed from the group). Same shape as Microsoft's guest-review tutorial.
3. **Lifecycle workflows** — `New-LeaverWorkflow` creates a **leaver** workflow on `employeeLeaveDateTime`
   (revoke refresh tokens, remove from all teams, remove from all groups, disable account) with scheduling **off**;
   `Invoke-LeaverWorkflow` runs it on demand for one user **after a pre-flight** (guest? still holds an Entra role?
   sole owner of a group?).
4. **Guard** — `Get-GuestBillingTrigger` refuses settings that need the **guest governance add-on** (Azure
   subscription, MAU billing) unless `-AllowGuestBilling`.
5. **Audit** — `Get-IdentityGovernanceInventory` + `Get-IdentityGovernanceFinding`: permanent active privileged roles
   (except emergency access accounts), emergency accounts not permanent, ≥ 5 Global Administrators (active + eligible),
   no guest review, no/unscheduled leaver workflow, and **what the end of the governance licence will do to PIM**.

Same fictional tenant as episodes 1–3 (`contoso`, Alex Demo — the groups lifecycle owner from episode 3 — Megan
Sample, the guest in `TEAM_Sales_Partner Portal` from episode 2), plus Sam Leaver from Sales.

| Path | What it is |
|---|---|
| [`src/governance.json`](src/governance.json) | 4 privileged roles (built-in template IDs), 2 emergency access accounts, Alex eligible for Groups Administrator 180 days, quarterly guest review, Sales leaver workflow, licence end date |
| [`src/IdentityGovernance/IdentityGovernance.psm1`](src/IdentityGovernance/IdentityGovernance.psm1) | The module: pure body builders, billing guard, pre-flight and findings + the functions that call Graph |
| [`src/IdentityGovernance/IdentityGovernance.psd1`](src/IdentityGovernance/IdentityGovernance.psd1) | Module manifest |
| [`src/Invoke-IdentityGovernance.ps1`](src/Invoke-IdentityGovernance.ps1) | Runner: `-Audit`, `-Preview` (offline), `-AssignEligible`, `-CreateGuestReview`, `-CreateLeaverWorkflow`, `-RunLeaver` (all write modes support `-WhatIf`) |
| [`tests/IdentityGovernance.Tests.ps1`](tests/IdentityGovernance.Tests.ps1) | 53 Pester tests (Graph mocked; 2 check our calls against the real Microsoft Graph PowerShell module) |
| [`tests/fixtures/inventory.json`](tests/fixtures/inventory.json) | Fictional role assignment/eligibility instances, principals, access reviews, workflows |
| [`sample/governance-audit.md`](sample/governance-audit.md) · [`sample/request-bodies.md`](sample/request-bodies.md) | Audit and the three request bodies, generated offline |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and the shot list for the lab recording |

## Run the tests

```bash
cd series/microsoft-365/episodes/04-entra-id-governance-identity
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Without Microsoft.Graph.Authentication installed: Tests Passed: 51, Failed: 0, Skipped: 2
# With it installed:                                  Tests Passed: 53, Failed: 0, Skipped: 0
```

Both results were produced in this repo's container (PowerShell 7.6, Pester 6.2.0, Microsoft.Graph.Authentication
2.41.2 saved to a temp folder on `PSModulePath`). PSScriptAnalyzer (Warning and Error, Graph module loaded) reports
0 issues on `src/`.

## Run it

```powershell
cd src
# Offline (no tenant): audit the fictional inventory -> 6 findings (3 High / 1 Medium / 2 Info), sample/governance-audit.md
./Invoke-IdentityGovernance.ps1 -Audit -InventoryFile ../tests/fixtures/inventory.json -Now 2026-11-20T09:30:00Z -OutFile ../sample/governance-audit.md

# Offline: the PIM, access review and workflow bodies + "Guest governance add-on needed: no"
./Invoke-IdentityGovernance.ps1 -Preview -Now 2026-11-20T09:30:00Z -StartDate 2026-12-01

# Needs tenant
./Invoke-IdentityGovernance.ps1 -Audit -OutFile ./governance-audit.md -SaveInventory ./inventory.json
./Invoke-IdentityGovernance.ps1 -AssignEligible -WhatIf
./Invoke-IdentityGovernance.ps1 -CreateGuestReview -StartDate 2026-12-01 -WhatIf
./Invoke-IdentityGovernance.ps1 -CreateLeaverWorkflow -WhatIf
./Invoke-IdentityGovernance.ps1 -RunLeaver -WorkflowId <id> -UserId <id> -WhatIf
```

## Licensing (Learn)

| Feature | Needs |
|---|---|
| PIM (Entra roles, PIM for Groups) | Entra ID P2 or Entra ID Governance — Microsoft 365 E5 includes P2 |
| Access reviews (capabilities previously in P2, e.g. guest review of groups) | P2 or Governance; members reviewing / being reviewed need licences |
| Lifecycle workflows | Entra ID Governance or Entra Suite (not P2) |
| Governance-only features on **guests** (inactive-guest reviews, user-to-group affiliation, workflows for guests, sponsor approvals…) | Guest governance add-on: Azure subscription linked, billed per monthly active guest, no free tier |

Licences must cover every member in scope; they don't have to be assigned to users.

## Permissions (least privileged, from each API page)

| Operation | API | Permission | Least privileged role (delegated) |
|---|---|---|---|
| Active assignments | `GET /roleManagement/directory/roleAssignmentScheduleInstances` | `RoleAssignmentSchedule.Read.Directory` | Global Reader / Security Reader |
| Eligible assignments | `GET /roleManagement/directory/roleEligibilityScheduleInstances` | `RoleEligibilitySchedule.Read.Directory` | Global Reader / Security Reader |
| Make eligible | `POST /roleManagement/directory/roleEligibilityScheduleRequests` | `RoleEligibilitySchedule.ReadWrite.Directory` | Privileged Role Administrator |
| List / create access reviews | `GET/POST /identityGovernance/accessReviews/definitions` | `AccessReview.Read.All` / `AccessReview.ReadWrite.All` | Identity Governance Administrator |
| List / create workflows | `GET/POST /identityGovernance/lifecycleWorkflows/workflows` | `LifecycleWorkflows-Workflow.ReadBasic.All` / `LifecycleWorkflows-Workflow.ReadWrite.All` | Lifecycle Workflows Administrator |
| Workflow tasks | `GET …/workflows/{id}/tasks` | `LifecycleWorkflows-Workflow.Read.All` | Lifecycle Workflows Administrator |
| Run on demand | `POST …/workflows/{id}/activate` (204) | `LifecycleWorkflows-Workflow.Activate` | Lifecycle Workflows Administrator |
| Pre-flight | `GET /users/{id}`, `GET /users/{id}/ownedObjects`, `GET /groups/{id}/owners` | `User.Read.All`, `GroupMember.Read.All` | |

## What we learned / gotchas

- **When the licence or trial ends, PIM unwinds.** Learn (licensing FAQ): eligible role assignments are **removed**,
  time-bound active assignments become **permanent**, permanent assignments are unaffected, ongoing role access
  reviews end. The lab's governance trial ends 20 Dec 2026, so the audit has a `LicenceEnding` rule that counts
  exactly what will change, 30 days ahead.
- **On-demand runs ignore the scope.** Learn: when you run a workflow on demand, the tasks execute regardless of
  whether the user matches the scope and trigger. The scope rule doesn't protect an on-demand run, so
  `Invoke-LeaverWorkflow` checks the user first.
- **Disable user account doesn't support users with Entra role assignments** (nor members/owners of role-assignable
  groups). Pre-flight blocks a leaver who still holds an active role when the workflow contains that task, and warns
  about eligible roles. Whether eligible-only assignments also make the task fail isn't spelled out in Learn — we
  warn, we don't block; see [demo.md](demo.md).
- **Removing a leaver from all groups can leave groups ownerless** (episode 3's `OwnerlessExpiring`). The pre-flight
  lists groups where the leaver is the only owner.
- **Guest billing is enforced.** Since January 2026, without the guest add-on you can't create guest-scoped reviews
  with the inactive-user scope or the user-to-group affiliation helper, or workflows whose rule includes
  `userType eq 'Guest'`; a workflow *run* for a guest is itself a billable action. P2 features (our basic guest
  review with `recommendationsEnabled`) aren't billed. The guard keeps the lab off the meter.
- **PIM rules from Learn we encoded:** zero permanent active assignments except emergency access accounts; two
  cloud-only emergency access accounts with Global Administrator **permanent active, not eligible**; activation is
  time-bound, **8 hours max**; fewer than five Global Administrators (we count active + eligible principals).
  You can't remove the last active Global Administrator assignment.
- **Role IDs are template IDs**, the same in every tenant (Global Administrator `62e90394-…`, Groups Administrator
  `fdd7a751-…`, User Administrator `fe930be7-…`, Privileged Role Administrator `e8611ab8-…`) — not tenant identifiers,
  so they're safe in the config. Task definition IDs for lifecycle workflows are fixed too.
- **Access review recurrence**: we kept the exact `recurrence` shape of Microsoft's tutorial (`absoluteMonthly`,
  `interval` 3, `month`/`dayOfMonth` 0, range `endDate`). Each group with guests becomes its own instance.
- **Learn disagrees with itself on the workflow limit** (licensing page: 50 workflows; Create workflow API page: 100),
  so the module doesn't enforce a number.
- Not verified here (needs tenant, see [demo.md](demo.md)): the `status` returned by the eligibility request in the
  lab (Learn shows `Provisioned`; role settings requiring approval change it), whether `$expand=principal` on the
  schedule instances returns `displayName`/`userType` for every principal type, and how quickly a removed role
  assignment disappears from `roleAssignmentScheduleInstances`.

Not covered in code (on purpose, to keep the episode to 6 minutes): **entitlement management** access packages
(P2 basics, Governance extras) — a natural next step for the partner guests: request, approval and expiry instead of
direct invitation.

## References

- [Microsoft Entra ID Governance licensing fundamentals](https://learn.microsoft.com/entra/id-governance/licensing-fundamentals) · [Licensing for guest users](https://learn.microsoft.com/entra/id-governance/microsoft-entra-id-governance-licensing-for-guest-users)
- [Plan a PIM deployment](https://learn.microsoft.com/entra/id-governance/privileged-identity-management/pim-deployment-plan) · [Manage emergency access accounts](https://learn.microsoft.com/entra/identity/role-based-access-control/security-emergency-access) · [Assign Entra roles in PIM (API)](https://learn.microsoft.com/entra/id-governance/privileged-identity-management/pim-how-to-add-role-to-user)
- [PIM APIs overview (activation max 8 hours)](https://learn.microsoft.com/graph/api/resources/privilegedidentitymanagementv3-overview?view=graph-rest-1.0) · [Create roleEligibilityScheduleRequest](https://learn.microsoft.com/graph/api/rbacapplication-post-roleeligibilityschedulerequests?view=graph-rest-1.0) · [List roleAssignmentScheduleInstances](https://learn.microsoft.com/graph/api/rbacapplication-list-roleassignmentscheduleinstances?view=graph-rest-1.0) · [unifiedRoleAssignmentScheduleInstance](https://learn.microsoft.com/graph/api/resources/unifiedroleassignmentscheduleinstance?view=graph-rest-1.0)
- [Microsoft Entra built-in roles (template IDs, fewer than five Global Administrators)](https://learn.microsoft.com/entra/identity/role-based-access-control/permissions-reference)
- [Review guest access to groups using access reviews APIs](https://learn.microsoft.com/graph/tutorial-accessreviews-m365group) · [Configure access review scope](https://learn.microsoft.com/graph/accessreviews-scope-concept) · [accessReviewScheduleDefinition](https://learn.microsoft.com/graph/api/resources/accessreviewscheduledefinition?view=graph-rest-1.0) · [List definitions](https://learn.microsoft.com/graph/api/accessreviewset-list-definitions?view=graph-rest-1.0)
- [Lifecycle Workflow built-in tasks](https://learn.microsoft.com/entra/id-governance/lifecycle-workflow-tasks) · [Create workflow](https://learn.microsoft.com/graph/api/identitygovernance-lifecycleworkflowscontainer-post-workflows?view=graph-rest-1.0) · [workflow: activate](https://learn.microsoft.com/graph/api/identitygovernance-workflow-activate?view=graph-rest-1.0) · [Scheduled leaver tutorial](https://learn.microsoft.com/graph/tutorial-lifecycle-workflows-scheduled-leaver) · [List workflows](https://learn.microsoft.com/graph/api/identitygovernance-lifecycleworkflowscontainer-list-workflows?view=graph-rest-1.0)
- [List ownedObjects](https://learn.microsoft.com/graph/api/user-list-ownedobjects?view=graph-rest-1.0) · [List group owners](https://learn.microsoft.com/graph/api/group-list-owners?view=graph-rest-1.0)
- Blog: [Entra ID Governance & Identity — Complete Guide](https://www.devladlog.com/articles/office-365/2026-03-31-entra-id-governance-complete-guide-2026/)
  (note: the current article is a generic template with placeholder cmdlets such as `Set-Configuration`; this
  folder's code is meant to replace them)
