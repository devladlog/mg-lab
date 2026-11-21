# DEVLADLOG Microsoft 365 #9 — Licensing Optimization

**Find the licences nobody uses, reclaim them safely, keep a way back.** One config file ([`src/licensing.json`](src/licensing.json)) and one
module read the tenant through Microsoft Graph and answer the questions the admin center leaves apart: *who holds which licence, how was it
assigned, and when did they last sign in?* The audit is read-only; the reclaim is the only thing that writes, and it is off until you name a SKU.

1. **Audit** — `Get-LOSku`, `Get-LOUser`, `Get-LOProtectedUserId`, `Get-LOLicenceFinding`: one `GET /users` with `assignedLicenses`,
   `licenseAssignmentStates` and `signInActivity`, plus the subscriptions and the members of activated admin roles. Rules:
   `DisabledAccountLicensed`, `InactiveLicensed`, `NeverSignedIn` (after a grace period), `RedundantLicence` (a licence another held licence supersedes,
   per your config, e.g. Business Standard next to E5), `DuplicateDirectAndGroup`, `OverlappingPlans`, `AssignmentError` (group licensing errors with the fix) and
   `NoSignInData` (the tenant returned no sign-in data, so the inactivity rules are skipped instead of calling everybody inactive).
2. **Money** — `Get-LOSavingSummary`, `Get-LOSeatSummary`: one seat per user and licence however many rules hit it, and seats paid for but not assigned.
   **Prices are yours** (`prices.perUserPerMonth`): the Graph subscription resource has no price. With none configured the report shows no money.
3. **Plan** — `Get-LOReclaimPlan`: only direct assignments, only SKUs in `reclaim.allowedSkuPartNumbers` (empty by default = nothing), only rules in
   `reclaim.rules`, never members of an admin role or `protectedUsers`, never group-assigned licences.
4. **Act** — `Invoke-LOReclaim` (`POST /users/{id}/assignLicense`, `-WhatIf`, `ConfirmImpact = High`): re-reads each user first, removes, and writes the
   removal to a **rollback file** before moving on; refuses to overwrite an old rollback file. `Restore-LOReclaim` puts the licences back with the same
   disabled plans after checking that a seat is free.

Same fictional tenant as episodes 1–8 (`contoso`); lab users `labadmin`, `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo`. The data in the tests
(ten fictional users, five SKUs, zero-style GUIDs, **example prices**) never appears in the demo.

| Path | What it is |
|---|---|
| [`src/licensing.json`](src/licensing.json) | Thresholds (90 days inactive, 30 days grace), protected users, supersede map, overlap limit, prices (empty), reclaim allow list (empty) and rules |
| [`src/LicensingOptimization/LicensingOptimization.psm1`](src/LicensingOptimization/LicensingOptimization.psm1) | The module: Graph collection, pure analysis, reclaim and restore, markdown report |
| [`src/LicensingOptimization/LicensingOptimization.psd1`](src/LicensingOptimization/LicensingOptimization.psd1) | Module manifest |
| [`src/Invoke-LicensingOptimization.ps1`](src/Invoke-LicensingOptimization.ps1) | Runner: audit (live or `-Snapshot`), `-SaveSnapshot`, `-AsOf`, `-OutFile`, `-Reclaim -RollbackFile`, `-Restore`, `-WhatIf` |
| [`tests/LicensingOptimization.Tests.ps1`](tests/LicensingOptimization.Tests.ps1) | 55 Pester tests (a small fake Graph tenant, including POST bodies and the rollback file; one test checks our calls against the real Microsoft.Graph.Authentication module) |
| [`tests/fixtures/`](tests/fixtures) | Fictional SKUs, users, admin roles, a test config with example prices, and the snapshot built from them |
| [`sample/licensing-audit.md`](sample/licensing-audit.md) | Report for the fictional snapshot, generated offline |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and shot list (no new VM; trial licences only, no cost) |

## Run the tests

```bash
cd series/microsoft-365/episodes/09-licensing-optimization
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Without the real Graph module:  Tests Passed: 54, Failed: 0, Skipped: 1
# With Microsoft.Graph.Authentication installed (adds the "real module parameters" test):
#                                 Tests Passed: 55, Failed: 0, Skipped: 0
```

Both results were produced in this repo's container (PowerShell 7.6, Pester 6.2.0; Microsoft.Graph.Authentication saved to a temp folder on
`PSModulePath`). PSScriptAnalyzer (Warning and Error) reports 0 issues on `src/`. The "What if:" lines printed during the run come from the `-WhatIf` tests.

## Run it

```powershell
cd src
# Offline (no tenant): analyse the fictional snapshot
./Invoke-LicensingOptimization.ps1 -Snapshot ../tests/fixtures/snapshot.json -ConfigFile ../tests/fixtures/licensing.test.json `
    -AsOf 2026-11-21T12:00:00Z -OutFile ../sample/licensing-audit.md
#   -> 10 users, 11 findings; reclaimable seats 6; reclaim plan 5 removals (E5 is reclaimable but not allowed)

# Needs tenant (see demo.md): copy licensing.json to licensing.lab.json first
./Invoke-LicensingOptimization.ps1 -ConfigFile ./licensing.lab.json -OutFile ./audit.lab.md   # LicenseAssignment.Read.All, User.Read.All, AuditLog.Read.All, RoleManagement.Read.Directory
./Invoke-LicensingOptimization.ps1 -ConfigFile ./licensing.lab.json -Reclaim -RollbackFile ./rollback.lab.json -WhatIf
./Invoke-LicensingOptimization.ps1 -ConfigFile ./licensing.lab.json -Reclaim -RollbackFile ./rollback.lab.json   # + LicenseAssignment.ReadWrite.All
./Invoke-LicensingOptimization.ps1 -Restore ./rollback.lab.json
```

## What we learned / gotchas

- **Sign-in data needs Entra ID P1 or P2** (Learn: *user* resource and *signInActivity*), the `AuditLog.Read.All` permission and a role such as Reports Reader.
  Without the licence Graph refuses the request (the module turns that into a clear message), and if a tenant ever returns the user list without it the
  `NoSignInData` finding switches the inactivity rules off. The property isn't returned for a user who never signed in or last signed in before April 2020.
- **`lastSignInDateTime` counts failed attempts** (Learn). The audit uses `lastSuccessfulSignInDateTime`, available since 1 Dec 2023 and **not backfilled**, and
  only falls back to the newest of the interactive and non-interactive dates when it is missing. *Not verified:* how many lab users fall back.
- **With `signInActivity` selected the page size maxes out at 500** (Learn: *List users*).
- **`assignedLicenses` does not say how a licence was assigned** (Learn); `licenseAssignmentStates` does: `assignedByGroup` is `null` when direct, the group id when inherited,
  and it carries `state` (`Active`, `ActiveWithError`, `Disabled`, `Error`) and `error` (`CountViolation`, `MutuallyExclusiveViolation`, `DependencyViolation`,
  `ProhibitedInUsageLocationViolation`, `UniquenessViolation`, `Other`). The one-line hints for each error are our reading of the problems table in Learn's
  group-licensing page (not a documented mapping).
- **Group licences are left to the group.** Removing someone from a group is the fix, so the plan never touches them. The directory role members used for the admin
  protection come from `directoryRoles`, which Learn says only lists **activated** roles and direct members (no PIM-eligible or group-assigned members); Learn recommends the
  unified RBAC API instead, which we did not use because we could not verify its filter requirements. Put your break-glass accounts in `protectedUsers` too.
- **Removing a licence has consequences (Learn):** Exchange Online data is held 30 days and then deleted and can't be recovered; the mailbox stops being searchable by eDiscovery;
  holds must be removed first; Office apps show unlicensed product errors; OneDrive files stay until the user is deleted, and an unlicensed OneDrive is archived on its 93rd unlicensed day.
- **Money is saved only when the subscription shrinks.** Learn: with an annual plan, or in the middle of a billing cycle, you can't remove the licence from the subscription until the
  commitment is complete. The report says so and calls the figure *potential*.
- **Why the reclaim is guarded:** empty allow list by default; `-WhatIf`; `ConfirmImpact = High` (one prompt per removal); re-read before each removal; rollback file written
  after each success and never overwritten; restore checks for a free seat. The tests prove that `-WhatIf` sends nothing, that only `GET` and `POST .../assignLicense` are ever sent, and that a failure
  in the middle leaves a rollback file with exactly the removals that happened.
- Pitfalls hit while building: `Measure-Object -Sum` on an empty list fails under strict mode (summed by hand); a one-item hashtable returned from a helper has `.Count` equal to its number
  of keys (the test helper wraps with `@()`); PSScriptAnalyzer caught that a runner function called `Connect-Graph` shadows an alias of `Connect-MgGraph` (renamed); `Format-Table` prints
  nothing without a console (the runner uses `Out-String -Width`) and wraps a long text column into one letter per line (the long text is only in the markdown report).
- **Not verified** (needs tenant, see [demo.md](demo.md)): whether the service accepts Business Standard directly next to E5 (Learn lists conflicting service plans as an assignment error, so it may be
  refused); that a licence assigned both directly and through a group shows two `licenseAssignmentStates` entries and that `removeLicenses` then removes only the direct one; the real `skuPartNumber`
  of the lab's Dynamics 365 Sales trial; that `Restore-LOReclaim` can reassign without a usage location problem (Learn: usage location is required to assign); the SKU part numbers in `supersededBy`
  are documented in Learn's service plan table, but *which licence supersedes which is your decision*. No price comes from Microsoft: the test prices are examples.

Not covered (to keep the episode to 6 minutes): buying, renewing or reducing subscriptions (Billing), Microsoft 365 usage reports per workload (episode 1 reads the activity report), disabling individual service
plans to downgrade a user, guest licences, group-based licensing set-up and reprocessing, Power Platform and Azure licences, PowerShell on `Microsoft.Graph.Users.Actions` (`Set-MgUserLicense`).

## References

- [user: assignLicense](https://learn.microsoft.com/graph/api/user-assignlicense?view=graph-rest-1.0) · [group: assignLicense](https://learn.microsoft.com/graph/api/group-assignlicense?view=graph-rest-1.0) · [user resource type](https://learn.microsoft.com/graph/api/resources/user?view=graph-rest-1.0) · [List users](https://learn.microsoft.com/graph/api/user-list?view=graph-rest-1.0)
- [signInActivity](https://learn.microsoft.com/graph/api/resources/signinactivity?view=graph-rest-1.0) · [licenseAssignmentState](https://learn.microsoft.com/graph/api/resources/licenseassignmentstate?view=graph-rest-1.0) · [subscribedSku](https://learn.microsoft.com/graph/api/resources/subscribedsku?view=graph-rest-1.0) · [List directoryRoles](https://learn.microsoft.com/graph/api/directoryrole-list?view=graph-rest-1.0) · [List members of a directory role](https://learn.microsoft.com/graph/api/directoryrole-list-members?view=graph-rest-1.0)
- [How to detect and investigate inactive user accounts](https://learn.microsoft.com/entra/identity/monitoring-health/howto-manage-inactive-user-accounts) · [Product names and service plan identifiers for licensing](https://learn.microsoft.com/entra/identity/users/licensing-service-plan-reference) · [Group-based licensing and its errors](https://learn.microsoft.com/entra/identity/users/licensing-groups-resolve-problems)
- [What happens to a user's data when you remove their license](https://learn.microsoft.com/microsoft-365/admin/manage/assign-licenses-to-users?view=o365-worldwide#what-happens-to-a-user's-data-when-you-remove-their-license) · [Remove a former employee, step 6 (licence and holds)](https://learn.microsoft.com/microsoft-365/admin/add-users/remove-former-employee-step-6?view=o365-worldwide) · [Delete a user (annual plan note)](https://learn.microsoft.com/microsoft-365/admin/add-users/delete-a-user?view=o365-worldwide) · [OneDrive retention and deletion](https://learn.microsoft.com/sharepoint/retention-and-deletion) · [Manage unlicensed OneDrive accounts](https://learn.microsoft.com/sharepoint/unlicensed-onedrive-accounts)
- Blog: [Licensing Optimization — Complete Guide](https://www.devladlog.com/articles/office-365/2025-05-06-licensing-optimization-complete-guide-2025/)
  (note, read 21 Nov 2026: the article has no licensing cmdlets, SKU names or prices; its code uses placeholder cmdlets `Set-Configuration` and `Get-DeploymentStatus`, an `api.microsoft.com`
  endpoint that isn't Microsoft Graph, and `Directory.ReadWrite.All` scopes. This folder's code is meant to replace it.)
