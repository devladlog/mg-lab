# DEVLADLOG Microsoft 365 #3 — Microsoft 365 Groups Lifecycle

**The rest of a group's life, as code.** Episode 2 controlled how teams are born; this one handles everything after.
One file ([`src/lifecycle.json`](src/lifecycle.json)) drives:

1. **Policy** — `Set-GroupsExpirationPolicy` makes the tenant's single `groupLifecyclePolicy` match the file (create,
   or PATCH only the properties that differ), then `addGroup` for each group of a **Selected** rollout. `-WhatIf`,
   `ConfirmImpact = High`.
2. **Preview** — `Get-ExpirationRolloutImpact`: which groups not yet under the policy are older than the lifetime and
   will therefore start with **35 days** to expiry the day you switch it on.
3. **Audit** — `Get-GroupsLifecycleInventory` + `Get-GroupsLifecycleFinding`: ownerless groups whose renewal mail goes
   to nobody, groups expiring soon (= not renewed by activity), groups in scope but not covered, policy drift, deleted
   groups close to permanent deletion.
4. **Act** — `Invoke-GroupRenewal` (`POST /groups/{id}/renew`), `Restore-DeletedM365Group` (checks the 30-day window,
   then `POST /directory/deletedItems/{id}/restore`), `Invoke-TeamArchive` (refuses ownerless teams, then
   `POST /teams/{id}/archive` and follows the async operation).

Same fictional tenant as episodes 1–2 (`contoso`, Alex Demo, the episode 2 teams `Project Falcon`, `Old Offsite 2024`,
`TEAM_Sales_Partner Portal`, `TEAM_Finance_Budget 2027`).

| Path | What it is |
|---|---|
| [`src/lifecycle.json`](src/lifecycle.json) | 180-day lifetime, Selected (4 pilot groups, zero GUIDs), alternate email for ownerless groups, warn 30 days before expiry and 7 days before permanent deletion, archive with SharePoint read-only for members |
| [`src/GroupsLifecycle/GroupsLifecycle.psm1`](src/GroupsLifecycle/GroupsLifecycle.psm1) | The module: pure policy/preview/finding functions + the few that call Graph (`Invoke-MgGraphRequest`) |
| [`src/GroupsLifecycle/GroupsLifecycle.psd1`](src/GroupsLifecycle/GroupsLifecycle.psd1) | Module manifest |
| [`src/Invoke-GroupsLifecycle.ps1`](src/Invoke-GroupsLifecycle.ps1) | Runner: `-Audit` (live or `-InventoryFile`), `-ApplyExpirationPolicy [-ImpactInventoryFile] -WhatIf`, `-Renew`, `-Restore`, `-Archive` |
| [`tests/GroupsLifecycle.Tests.ps1`](tests/GroupsLifecycle.Tests.ps1) | 47 Pester tests (Graph mocked; 2 check our calls against the real Microsoft Graph PowerShell module) |
| [`tests/fixtures/inventory.json`](tests/fixtures/inventory.json) | Fictional policy, 5 groups and 2 deleted groups |
| [`sample/lifecycle-audit.md`](sample/lifecycle-audit.md) | Audit generated offline from the fictional inventory |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and the shot list for the lab recording |

## Run the tests

```bash
cd series/microsoft-365/episodes/03-microsoft-365-groups-lifecycle
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Without Microsoft.Graph.Authentication installed: Tests Passed: 45, Failed: 0, Skipped: 2
# With it installed:                                  Tests Passed: 47, Failed: 0, Skipped: 0
```

Both results were produced in this repo's container (PowerShell 7.6, Pester 6.2.0, Microsoft.Graph.Authentication
2.41.2 saved to a temp folder on `PSModulePath`). PSScriptAnalyzer (Warning and Error, Graph module loaded) reports
0 issues on `src/`.

## Run it

```powershell
cd src
# Offline (no tenant): audit the fictional inventory -> 7 findings (2 High / 3 Medium / 1 Low / 1 Info), sample/lifecycle-audit.md
./Invoke-GroupsLifecycle.ps1 -Audit -InventoryFile ../tests/fixtures/inventory.json -Now 2026-11-20T09:30:00Z -OutFile ../sample/lifecycle-audit.md

# Offline: who would start with 35 days? (Selected -> TEAM_Sales_Partner Portal; with "All" also Contoso Book Club)
./Invoke-GroupsLifecycle.ps1 -ApplyExpirationPolicy -ImpactInventoryFile ../tests/fixtures/inventory.json -Now 2026-11-20T09:30:00Z -WhatIf

# Needs tenant
./Invoke-GroupsLifecycle.ps1 -Audit -OutFile ./lifecycle-audit.md -SaveInventory ./inventory.json   # Directory.Read.All, Group.Read.All, GroupMember.Read.All
./Invoke-GroupsLifecycle.ps1 -ApplyExpirationPolicy -WhatIf                                          # Directory.ReadWrite.All
./Invoke-GroupsLifecycle.ps1 -Renew <group id>                                                       # Group.ReadWrite.All
./Invoke-GroupsLifecycle.ps1 -Restore <deleted group id>                                             # Group.ReadWrite.All
./Invoke-GroupsLifecycle.ps1 -Archive <team id> -WhatIf                                              # TeamSettings.ReadWrite.All
```

## Permissions (least privileged, from each API page)

| Operation | API | Permission |
|---|---|---|
| Read / create / update the policy | `GET/POST /groupLifecyclePolicies`, `PATCH /groupLifecyclePolicies/{id}` | `Directory.Read.All` (read), `Directory.ReadWrite.All` (write) |
| Add a group to a Selected policy | `POST /groupLifecyclePolicies/{id}/addGroup` | `Directory.ReadWrite.All` |
| List Microsoft 365 groups | `GET /groups?$filter=groupTypes/any(c:c+eq+'Unified')` | `Group.Read.All` (any group read permission works) |
| Owners | `GET /groups/{id}/owners` | `GroupMember.Read.All` |
| Deleted groups | `GET /directory/deletedItems/microsoft.graph.group`, `GET /directory/deletedItems/{id}` | `Group.Read.All` |
| Renew | `POST /groups/{id}/renew` (204, no body) | `Group.ReadWrite.All` |
| Restore | `POST /directory/deletedItems/{id}/restore` | `Group.ReadWrite.All` (+ Groups Administrator role in delegated mode) |
| Archive a team | `POST /teams/{id}/archive` (202 + `Location`) | `TeamSettings.ReadWrite.All` |

## What we learned / gotchas

- **The first rollout is a cliff.** Learn: when you first set up expiration, groups older than the lifetime are set
  to **35 days** until expiration (unless renewed or auto-renewed). Switching an old tenant to **All** starts a
  35-day countdown for every old group at once. `Get-ExpirationRolloutImpact` lists them before you confirm. We do
  **not** compute dates for younger groups: Learn doesn't document that formula, so the preview only says
  *WithinLifetime*.
- **Only one policy per tenant**, lifetime **30 days or more**, **All / Selected / None**, **up to 500** groups in
  Selected (one group per `addGroup` call). Requires Microsoft Entra ID P1 (or P2) for the members of the groups the
  policy applies to (possessed, not necessarily assigned).
- **`alternateNotificationEmails` is one string**, semicolon-separated. The config keeps a list; we join on `;` for
  the API and compare as a case-insensitive set, so a reordered list isn't reported as drift.
- **Ownerless + no alternate email = nobody is told.** Notices go to owners 30, 15 and 1 day before expiry; groups
  without owners send them to the alternate email. The audit says who gets the mail, per group.
- **Activity renews groups ~35 days before expiry** (Outlook group messages, SharePoint file activity, visiting a
  Teams channel, viewing a Viva Engage post), with no email to the owner. So a group *inside* the 30-day window
  wasn't renewed by activity — that's what `ExpiringSoon` means. Renewal from activity isn't immediate: a flag is set
  and renewal happens within 24 hours once the group is near expiry.
- **Expired groups are deleted one day after expiration**, and Microsoft never deletes a group before the last
  notification is sent. Deleted groups are restorable for **30 days**, not customizable; content (site, mailbox) can
  take up to 24 hours to come back. After 30 days the group's data in Planner, Sites and Teams is permanently deleted
  (a mailbox on legal hold is retained).
- **Archiving needs an owner.** `POST /teams/{id}/archive` requires the team and group to have an owner, so an
  ownerless team can't even be frozen — `Invoke-TeamArchive` checks first. `shouldSetSpoSiteReadOnlyForMembers`
  isn't supported in application context (delegated only).
- **`/groups/{id}/owners` with `$select` needs advanced query parameters** (Learn: all query options except `$expand`
  need them), so the inventory calls it without query options and just counts.
- **`expirationDateTime` is in v1.0** (the expiration article still says Beta; the v1.0 `group` resource documents
  it, read-only, `null` for security groups). We use v1.0 throughout.
- **Container quirk (not a product issue):** in a non-interactive `pwsh` with no console width, `Format-Table`
  piped to `Out-String` without `-Width` printed nothing. The runner always passes `-Width 200`.
- Not verified here (needs tenant, see [demo.md](demo.md)): what `addGroup` returns for a group that is already in
  the policy, and the exact `Location` format of the archive operation in the lab (the docs show
  `/teams({id})/operations({opId})`; we accept relative or absolute).

Related, no code needed: the **ownerless group policy** in the Microsoft 365 admin center (episode 2) asks active
members to accept ownership — it pairs well with the `OwnerlessExpiring` finding.

## References

- [Configure the expiration policy for Microsoft 365 groups](https://learn.microsoft.com/entra/identity/users/groups-lifecycle)
- [Restore a deleted Microsoft 365 group](https://learn.microsoft.com/entra/identity/users/groups-restore-deleted)
- [groupLifecyclePolicy resource](https://learn.microsoft.com/graph/api/resources/grouplifecyclepolicy?view=graph-rest-1.0) · [List](https://learn.microsoft.com/graph/api/grouplifecyclepolicy-list?view=graph-rest-1.0) · [addGroup](https://learn.microsoft.com/graph/api/grouplifecyclepolicy-addgroup?view=graph-rest-1.0) · [New-MgGroupLifecyclePolicy](https://learn.microsoft.com/powershell/module/microsoft.graph.groups/new-mggrouplifecyclepolicy?view=graph-powershell-1.0)
- [group resource (expirationDateTime, renewedDateTime)](https://learn.microsoft.com/graph/api/resources/group?view=graph-rest-1.0) · [group: renew](https://learn.microsoft.com/graph/api/group-renew?view=graph-rest-1.0) · [List groups](https://learn.microsoft.com/graph/api/group-list?view=graph-rest-1.0) · [List group owners](https://learn.microsoft.com/graph/api/group-list-owners?view=graph-rest-1.0)
- [List deletedItems](https://learn.microsoft.com/graph/api/directory-deleteditems-list?view=graph-rest-1.0) · [Get deleted item](https://learn.microsoft.com/graph/api/directory-deleteditems-get?view=graph-rest-1.0) · [Restore deleted item](https://learn.microsoft.com/graph/api/directory-deleteditems-restore?view=graph-rest-1.0)
- [Archive team](https://learn.microsoft.com/graph/api/team-archive?view=graph-rest-1.0)
- Blog: [Microsoft 365 Groups Lifecycle — Complete Guide](https://www.devladlog.com/articles/office-365/2025-07-09-groups-lifecycle-complete-guide-2025/)
  (note: the current article is a generic template with placeholder cmdlets such as `Set-Configuration`; this
  folder's code is meant to replace them)
