# DEVLADLOG Microsoft 365 #2 — Microsoft Teams Architecture & Governance

**Teams governance as code.** One policy file ([`src/governance.json`](src/governance.json)) drives four things:

1. **Preview** — `Resolve-TeamName` applies the naming convention (prefix/suffix with user attributes such as
   `[Department]`), the blocked words and the 63-character limit, exactly as the Entra ID group naming policy describes them.
2. **Create** — `New-GovernedTeam` builds the `POST /teams` body (standard template, **private unless told otherwise**,
   at least N owners), sends it, follows the `202 Accepted` → `Location` → `teamsAsyncOperation` flow, supports `-WhatIf`.
3. **Audit** — `Get-TeamsInventory` + `Get-TeamsGovernanceFinding`: ownerless teams, too few owners, guests in public
   teams, names off the convention, inactive teams (joined from the Teams usage report).
4. **Tenant** — `Set-TeamsDirectoryPolicy` writes the same naming requirement, blocked words and group-creation
   restriction to the tenant's `Group.Unified` directory setting (merge, `-WhatIf`, `ConfirmImpact = High`), so the
   service enforces what the script previews.

| Path | What it is |
|---|---|
| [`src/governance.json`](src/governance.json) | The policy: convention `TEAM_[Department]_[GroupName]`, blocked words, minimum 2 owners, private default, no guests in public teams, 90 days inactivity, creation limited to one group (zero GUID) |
| [`src/TeamsGovernance/TeamsGovernance.psm1`](src/TeamsGovernance/TeamsGovernance.psm1) | The module (pure naming/request/finding functions + the few that call Graph) |
| [`src/TeamsGovernance/TeamsGovernance.psd1`](src/TeamsGovernance/TeamsGovernance.psd1) | Module manifest |
| [`src/Invoke-TeamsGovernance.ps1`](src/Invoke-TeamsGovernance.ps1) | Runner: `-Audit` (live or `-InventoryFile`), `-NewTeam … -WhatIf`, `-ApplyTenantPolicy -WhatIf` |
| [`tests/TeamsGovernance.Tests.ps1`](tests/TeamsGovernance.Tests.ps1) | 39 Pester tests (Graph mocked; 2 check our calls against the real Microsoft Graph PowerShell module) |
| [`tests/fixtures/`](tests/fixtures/) | Fictional teams, members (with `owner`/`guest` roles), Teams activity CSV, group settings, saved inventory |
| [`sample/teams-audit.md`](sample/teams-audit.md) | Audit generated offline from the fictional inventory |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and the shot list for the lab recording |

## Run the tests

```bash
cd series/microsoft-365/episodes/02-microsoft-teams-architecture-governance
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Without Microsoft.Graph.Authentication installed: Tests Passed: 37, Failed: 0, Skipped: 2
# With it installed:                                  Tests Passed: 39, Failed: 0, Skipped: 0
```

Both results were produced in this repo's container (PowerShell 7.6, Pester 6.2.0, Microsoft.Graph.Authentication 2.41.2
on a temporary `PSModulePath`). PSScriptAnalyzer (Warning and Error) reports 0 issues on `src/`.

## Run it

```powershell
cd src
# Offline (no tenant): audit the fictional inventory -> 7 findings (2 High / 1 Medium / 4 Low), sample/teams-audit.md
./Invoke-TeamsGovernance.ps1 -Audit -InventoryFile ../tests/fixtures/inventory.json -OutFile ../sample/teams-audit.md

# Preview a team (no tenant, no Graph call): prints the final name and the exact JSON body
./Invoke-TeamsGovernance.ps1 -NewTeam 'Budget 2027' -Department Finance -OwnerIds <id1>,<id2> -WhatIf
./Invoke-TeamsGovernance.ps1 -NewTeam 'CEO office' -Department Finance -OwnerIds <id1>,<id2> -WhatIf   # -> BlockedWord:CEO

# Needs tenant
./Invoke-TeamsGovernance.ps1 -NewTeam 'Budget 2027' -Department Finance -OwnerIds <id1>,<id2>       # Team.Create
./Invoke-TeamsGovernance.ps1 -Audit -OutFile ./teams-audit.md -SaveInventory ./inventory.json      # Team.ReadBasic.All, TeamMember.Read.All, Reports.Read.All
./Invoke-TeamsGovernance.ps1 -ApplyTenantPolicy -WhatIf                                             # GroupSettings.ReadWrite.All
```

## Permissions (least privileged, from each API page)

| Operation | API | Permission |
|---|---|---|
| Create team | `POST /teams` | `Team.Create` |
| List teams | `GET /teams` (only `id`, `displayName`, `description`, `visibility` are populated) | `Team.ReadBasic.All` |
| Team members and roles | `GET /teams/{id}/members` | `TeamMember.Read.All` (delegated) |
| Team activity | `GET /reports/getTeamsTeamActivityDetail(period='D180')` | `Reports.Read.All` + a reports-capable admin role |
| Naming policy, creation restriction | `GET/PATCH/POST /groupSettings`, `GET /groupSettingTemplates/{id}` | `GroupSettings.ReadWrite.All` (Groups Administrator role) |

## What we learned / gotchas

- **The API default visibility is Public.** The `team` resource documents `visibility` as "Defaults to Public". A
  provisioning script that forgets one property creates org-wide open teams. `New-TeamsCreateRequest` always sets it
  from the policy (default `private`) and has a test for it.
- **Global Administrator and User Administrator are exempt from the group naming policy** (all workloads and endpoints).
  If a provisioning script runs as one of them, nothing but the script enforces the convention — which is why
  `New-GovernedTeam` resolves and validates the name before calling Graph.
- **Naming policy facts we mirrored**: prefix + group name + suffix ≤ **63** characters; supported attributes
  `[Department] [Company] [Office] [StateOrProvince] [CountryOrRegion] [Title]`; unsupported ones (e.g.
  `[postalCode]`) are kept as fixed text; blocked words are **not case-sensitive** and there's **no substring
  matching** (up to 5,000 words); requires **Microsoft Entra ID P1** licences. Our whole-word matcher is our reading of
  "no substring search" — the service remains the source of truth, and we only check the requested part of the name.
- **`POST /teams` is asynchronous**: `202 Accepted`, empty body, a relative `Location` header to a
  `teamsAsyncOperation` (`notStarted` / `inProgress` / `succeeded` / `failed`). We request
  `-OutputType HttpResponseMessage` to read the header (testable with a real `HttpResponseMessage`), and take the team
  ID from the operation's `targetResourceId` (the docs say not to parse resource locations).
- **The team's SharePoint site may not provision**; the docs say to call *Get filesFolder* if it isn't there after 5 minutes.
- **Owners and guests come from `conversationMember.roles`** (`owner`, `guest`; a basic member has no roles).
- **The activity join can silently fail.** If the usage report is concealed (episode 1), rows won't match team IDs.
  Instead of flagging every team as inactive, the audit emits one *ActivityUnavailable* Info finding.
- **Group creation restriction**: one group controls who can create Microsoft 365 groups (nesting allowed), it affects
  Outlook, SharePoint, Teams, Planner and more, the admin and allowed users need Entra ID P1, and changes can take
  30 minutes or more. Global admins keep creating groups in some admin centers but not in Teams.
- **`Connect-Graph` is taken.** Our runner first had a helper function called `Connect-Graph`. Microsoft.Graph.Authentication
  exports an **alias** `Connect-Graph` → `Connect-MgGraph`, and in PowerShell an alias wins over a function, so once the
  module is loaded our helper would have been bypassed. PSScriptAnalyzer only flagged it when the Graph module was
  loaded in the session; the helper is now `Connect-TeamsGovernanceGraph`.
- `pwsh -File script.ps1 -OwnerIds a,b` passes `"a,b"` as **one** string; the runner splits on commas. And
  `ForEach-Object Trim` honours `-WhatIf` (it is a "method invocation"), so the script uses `{ $_.Trim() }`.
- Not verified here (needs tenant, see [demo.md](demo.md)): whether the signed-in admin is also added as owner when the
  `members` collection is supplied with delegated permissions (Microsoft's sample with owners in `members` is the
  application-permission one), and the exact Group.Unified values present in the lab before the change.

Complementary, no code needed: the **ownerless group policy** in the Microsoft 365 admin center asks active members
to accept ownership of ownerless groups/teams.

## References

- [Plan for governance in Teams](https://learn.microsoft.com/microsoftteams/plan-teams-governance) · [Plan for lifecycle management in Teams](https://learn.microsoft.com/microsoftteams/plan-teams-lifecycle)
- [Enforce a naming policy on Microsoft 365 groups](https://learn.microsoft.com/entra/identity/users/groups-naming-policy)
- [Manage who can create Microsoft 365 Groups](https://learn.microsoft.com/microsoft-365/solutions/manage-creation-of-groups)
- [Create team (`POST /teams`)](https://learn.microsoft.com/graph/api/team-post?view=graph-rest-1.0) · [team resource (visibility default)](https://learn.microsoft.com/graph/api/resources/team?view=graph-rest-1.0) · [teamsAsyncOperation](https://learn.microsoft.com/graph/api/resources/teamsasyncoperation?view=graph-rest-1.0)
- [List teams](https://learn.microsoft.com/graph/api/teams-list?view=graph-rest-1.0) · [List members of team](https://learn.microsoft.com/graph/api/team-list-members?view=graph-rest-1.0) · [conversationMember (roles)](https://learn.microsoft.com/graph/api/resources/conversationmember?view=graph-rest-1.0)
- [reportRoot: getTeamsTeamActivityDetail](https://learn.microsoft.com/graph/api/reportroot-getteamsteamactivitydetail?view=graph-rest-1.0)
- [Update groupSetting](https://learn.microsoft.com/graph/api/groupsetting-update?view=graph-rest-1.0)
- [Limits and specifications for Microsoft Teams (100 owners, 25,000 members per team)](https://learn.microsoft.com/microsoftteams/limits-specifications-teams)
- [Manage ownerless Microsoft 365 groups and teams](https://learn.microsoft.com/microsoft-365/admin/create-groups/ownerless-groups-teams?view=o365-worldwide)
- [Invoke-MgGraphRequest](https://learn.microsoft.com/powershell/module/microsoft.graph.authentication/invoke-mggraphrequest?view=graph-powershell-1.0)
- Blog: [Microsoft Teams Architecture & Governance — Complete Guide](https://www.devladlog.com/articles/office-365/2025-01-01-teams-architecture-complete-guide-2025/)
