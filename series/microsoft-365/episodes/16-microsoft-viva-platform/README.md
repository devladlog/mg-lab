# DEVLADLOG Microsoft 365 #16 — Microsoft Viva Platform

**Viva Engage communities and roles as code.** Viva is a family (Connections, Engage, Insights, Learning, Goals) and
Microsoft Graph reaches only part of it. The part that is a stable, administrable v1.0 API is **Viva Engage**:
communities and roles under `/employeeExperience`. That is what this episode builds, on the same fictional tenant as
the earlier episodes (`contoso`, Alex Demo, the Project Falcon team). One file
([`src/communities.json`](src/communities.json)) drives:

1. **Plan / Apply** — `Get-VivaCommunityDiff` and `Set-VivaCommunity`: create the communities that are missing
   (POST, follow the asynchronous operation, read the new community's `groupId`), add missing owners and members on the
   connected Microsoft 365 group, and (only with `-FixDrift`) patch description or privacy. **It never deletes**:
   Learn says deleting a community deletes its group, notebook and Planner plans. `-WhatIf` lists every step.
2. **Audit** — `Get-VivaInventory` + `Get-VivaFinding`: no owner (High), fewer owners than policy, only owners as
   members, privacy drift, communities not in the file (Info), duplicate names, a community in the file that is missing,
   too many Network Administrators and Network Administrators who are not on the allow list (High). Markdown report.
3. **Throttling and async** — `Invoke-VivaRequest` waits for `Retry-After` on 429; `Wait-VivaOperation` polls more than
   30 seconds apart and refuses a shorter interval.

| Path | What it is |
|---|---|
| [`src/communities.json`](src/communities.json) | 3 communities (private/public, owners, members) and the policy: `minOwners`, `maxNetworkAdmins`, `allowedNetworkAdmins` (`contoso.com` users) |
| [`src/VivaEngage/VivaEngage.psm1`](src/VivaEngage/VivaEngage.psm1) | The module: pure config/body/diff/finding functions + the few that call Graph (`Invoke-MgGraphRequest`) |
| [`src/VivaEngage/VivaEngage.psd1`](src/VivaEngage/VivaEngage.psd1) | Module manifest |
| [`src/Invoke-VivaEngage.ps1`](src/Invoke-VivaEngage.ps1) | Runner: `-Plan` (diff, live or `-InventoryFile`), `-Apply [-FixDrift] [-WhatIf]`, `-Audit` (live or `-InventoryFile`) |
| [`tests/VivaEngage.Tests.ps1`](tests/VivaEngage.Tests.ps1) | 54 Pester tests (Graph mocked; 2 check our calls against the real Microsoft Graph PowerShell module) |
| [`tests/fixtures/inventory.json`](tests/fixtures/inventory.json) | A fictional tenant: 4 communities and 2 roles |
| [`sample/viva-audit.md`](sample/viva-audit.md) | Audit of the fixture, generated offline (10 findings: 3 High, 4 Medium, 1 Low, 2 Info) |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Narration/scenes, and the lab shot list with tear-down |

## Run the tests

```powershell
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Without Microsoft.Graph.Authentication installed: Tests Passed: 52, Failed: 0, Skipped: 2
# With it installed:                                 Tests Passed: 54, Failed: 0, Skipped: 0
# PSScriptAnalyzer (Warning, Error) on ./src:        0 issues
```

Needs PowerShell 7.2+ and Pester 5+ (built with 7.6 and Pester 6.2). No tenant, no licence.

## Run it

```powershell
cd src
# Offline (no tenant): diff and audit of the fictional inventory
./Invoke-VivaEngage.ps1 -Plan  -InventoryFile ../tests/fixtures/inventory.json
./Invoke-VivaEngage.ps1 -Audit -InventoryFile ../tests/fixtures/inventory.json -OutFile ../sample/viva-audit.md

# Needs tenant (copy communities.json to communities.lab.json first: real UPNs, never committed)
./Invoke-VivaEngage.ps1 -ConfigFile ./communities.lab.json -Apply -WhatIf
./Invoke-VivaEngage.ps1 -ConfigFile ./communities.lab.json -Apply
./Invoke-VivaEngage.ps1 -ConfigFile ./communities.lab.json -Audit -OutFile ./viva-audit.md -FailOnHigh
```

`-FailOnHigh` exits with code 2 when there is a High finding, so a pipeline can stop on it.

## Graph calls and permissions (delegated; from each API page on Microsoft Learn)

| Call | Used for | Permission |
|---|---|---|
| `GET /employeeExperience/communities` | List (`$select`, `$top`, paging) | `Community.Read.All` |
| `POST /employeeExperience/communities` | Create: 202 + `engagementAsyncOperation` | `Community.ReadWrite.All` |
| `GET` operation URL (from the header) | Poll until `succeeded` (`resourceId` = community id) | same as the call that started it |
| `GET /employeeExperience/communities/{id}` | Read `groupId` | `Community.Read.All` |
| `PATCH /employeeExperience/communities/{id}` | `-FixDrift`: description, privacy (204) | `Community.ReadWrite.All` |
| `GET /groups/{groupId}/owners`, `/members` | Current owners and members | `Group.Read.All` |
| `POST /groups/{groupId}/owners/$ref`, `/members/$ref` | Add an owner or a member | `Group.ReadWrite.All` (+ a supported Entra role in delegated scenarios) |
| `GET /employeeExperience/roles`, `/roles/{id}/members` | Role members for the audit | `EngagementRole.Read.All` |
| `GET /users/{id}`, `GET /users/{upn}` | UPN <-> id | `User.ReadBasic.All` |

Runner scopes: apply = `Community.ReadWrite.All`, `Group.ReadWrite.All`, `User.ReadBasic.All`; audit = `Community.Read.All`,
`EngagementRole.Read.All`, `Group.Read.All`, `User.ReadBasic.All`. The runner uses delegated sign-in only.

## What we learned / gotchas

- **Native mode only.** The communities and roles APIs work for Viva Engage networks in native mode, not legacy or external ones (Learn).
- **Create is asynchronous.** The answer is 202 Accepted plus an operation; Learn says to poll with **more than 30 seconds**
  between checks. `Wait-VivaOperation` has `ValidateRange(31, 600)` for that reason.
- **Header name.** Learn's text says `Operation-Location`, its example shows `Location`. `Get-VivaHeaderValue` reads both, in any case.
- **A Pester mock cannot fill `-ResponseHeadersVariable` in the caller's scope**, so the tests for the create flow mock
  `Invoke-VivaRequest`, one level above `Invoke-MgGraphRequest`. The 429 and polling tests mock `Invoke-MgGraphRequest`.
- **Owners and members are group operations.** The create API does not take them (delegated: the caller becomes owner;
  application permissions: `owners@odata.bind` is required, covered by `ConvertTo-VivaCommunityBody -AsApplication`, which the runner does not use). Group owners become community admins (Learn). You cannot provision a community with the Create group API.
- **An owner is added as member too.** Learn (Add owners) says an owner who should make changes also needs to be a member, so the diff adds both.
- **Throttling.** 10 requests per user per app per 30 seconds, then 429. `Invoke-VivaRequest` waits for `Retry-After`
  (30 s if the header is not readable) and tries again, up to 3 times.
- **Never delete.** The diff has no delete action and a test asserts no `DELETE` request is sent: deleting a community deletes its group, notebook and plans.
- **Roles are predefined.** Network Administrator and Verified Administrator, among others; custom roles are not possible (Learn). The audit counts Network Administrators and compares them with `allowedNetworkAdmins`.
- **PowerShell traps hit while building** (all covered by tests): a function that returns an empty array yields `$null` (callers wrap with `@()`;
  returning `, $array` instead nests the result); `Retry-After` was lost when a helper returned the header collection
  (PowerShell enumerates it), so the header is read directly from the exception's response.
- **What the episode leaves out on purpose.** Viva Goals was retired on 31 December 2025 (no replacement). The Learning
  provider API (`/employeeExperience/learningProviders`) is delegated only and needs a Viva Suite or Viva Learning licence plus the Knowledge Administrator role; the lab has neither. Viva Connections cards are an SPFx project, not a Graph call. Anything built on Microsoft 365 Copilot needs a licence the lab does not have, so no Copilot output exists in this episode.

## Not verified (needs the lab tenant)

- A real create: how long it takes, and whether the operation header is `Operation-Location` or `Location`.
- Which users may create communities (the network may restrict it); the exact role display names (`Network Administrator` is matched by the text `Network Admin`).
- That adding an owner to the group makes the person a community admin straight away, and that an owner who is not a member is accepted.
- The `owners@odata.bind` value format for application permissions (we follow the usual `…/users/{id}` convention; never sent by the runner).
- That `$select=id,displayName,description,privacy,groupId` is accepted on the communities list and `…/communities/{id}` (Learn documents `$select` for the list).
- Paging: `$top=20` is the documented default page size; the code follows `@odata.nextLink`, but no tenant here has more than one page.
- The Teams screen: Viva Connections depends on a home site the lab may not have.

## References

- Viva Engage communities: [community resource](https://learn.microsoft.com/graph/api/resources/community), [Create community](https://learn.microsoft.com/graph/api/employeeexperience-post-communities), [List communities](https://learn.microsoft.com/graph/api/employeeexperience-list-communities), [Update community](https://learn.microsoft.com/graph/api/community-update)
- Async operations: [engagementAsyncOperation](https://learn.microsoft.com/graph/api/resources/engagementasyncoperation)
- Roles: [engagementRole](https://learn.microsoft.com/graph/api/resources/engagementrole), [List roles](https://learn.microsoft.com/graph/api/employeeexperience-list-roles), [List role members](https://learn.microsoft.com/graph/api/engagementrole-list-members), [List assigned roles](https://learn.microsoft.com/graph/api/employeeexperienceuser-list-assignedroles)
- Groups: [Add owners](https://learn.microsoft.com/graph/api/group-post-owners)
- Blog guide: [Viva employee experience, complete guide 2026](https://www.devladlog.com/articles/office-365/2026-06-03-viva-employee-experience-complete-guide-2026/)
