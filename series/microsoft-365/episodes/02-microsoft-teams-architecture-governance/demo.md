# Demo shot list — DEVLADLOG Microsoft 365 #2: Microsoft Teams Architecture & Governance

Everything in `src/` and `tests/` already ran in the build container (39 Pester tests, offline audit, `-WhatIf`
previews). This file lists what the human-supervised session must set up and record in the **lab tenant**.

## Prerequisites

| Item | Notes | Cost |
|---|---|---|
| Lab tenant with Teams licences (exists) | | none |
| **Microsoft Entra ID P1** for the users involved | Required by the naming policy and by the group-creation restriction (Microsoft 365 E5 includes it; the planned E5 trial covers this) | trial |
| Admin account for setup | Groups Administrator (group settings) + Teams Administrator; a Global Administrator only for the "exempt" shot | none |
| Fictional users | **Alex Demo** (no admin role, Department = `Finance`), **Megan Sample** (second owner), **Temp Owner** (will be deleted), one existing **guest** account | none |
| Security group **Team Creators** | Members: Alex Demo. Its object ID goes in `creation.allowedGroupId` of a *local copy* of `governance.json` (never commit the real ID) | none |
| PowerShell 7.2+ + `Microsoft.Graph.Authentication` | `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser` | none |
| Browser with `pipeline/mask.js` | Teams admin center, Entra admin center, Teams web | none |

## Setup (before recording) — order matters

1. **Seed teams before applying the naming policy** (otherwise Alex's teams get the prefix automatically):
   - As Alex in Teams: create private team **Project Falcon** (Alex only owner).
   - As admin: create public team **Sales Partner Portal**, add the guest as member, Alex + Megan as owners.
   - As admin: create team **Old Offsite 2024** with **Temp Owner** as the only owner, then **delete Temp Owner**
     (deleting the owner's account is how a team becomes ownerless).
   - Optional: one team nobody uses (it will only show as inactive once the usage report covers it; new teams can take
     days to appear in the report).
2. Run the tests: `pwsh -NoProfile -Command 'Invoke-Pester ./tests'` → `Tests Passed: 39`.
3. Copy `src/governance.json` to a local, uncommitted `governance.lab.json` and put the Team Creators object ID in it;
   pass `-PolicyFile ./governance.lab.json` in every command below.
4. Terminal: dark theme, font 18+, prompt `PS> `.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/create.jpg` — "WhatIf first, then the real team" (**needs tenant** for the real run)
```powershell
cd src
$alex = '<Alex object id>'; $megan = '<Megan object id>'
./Invoke-TeamsGovernance.ps1 -PolicyFile ./governance.lab.json -NewTeam 'Budget 2027' -Department Finance -OwnerIds $alex,$megan -WhatIf
./Invoke-TeamsGovernance.ps1 -PolicyFile ./governance.lab.json -NewTeam 'Budget 2027' -Department Finance -OwnerIds $alex,$megan
./Invoke-TeamsGovernance.ps1 -PolicyFile ./governance.lab.json -NewTeam 'CEO office' -Department Finance -OwnerIds $alex,$megan -WhatIf
```
Expected: `What if: … "Create private team with 2 owners" on target "TEAM_Finance_Budget 2027"` + JSON body; then
`TEAM_Finance_Budget 2027: Created <id>`; then `Name 'TEAM_Finance_CEO office' rejected: BlockedWord:CEO`.
Mask the object IDs and the team ID. Sign-in scope: `Team.Create`.

### 2. `screens/admin-center.jpg` — "Private, two owners, on the convention" (**needs tenant**)
Teams admin center → Teams → Manage teams → search `TEAM_` → **TEAM_Finance_Budget 2027**: Privacy *Private*, then
its Members tab. **Verify and note in README**: does the team have exactly Alex + Megan as owners, or was the signed-in
admin added too? If the admin was added, adjust the narration ("…plus the admin who created it") and decide whether
`New-GovernedTeam` should remove the creator afterwards.

### 3. `screens/audit.jpg` — "Audit every team against the same policy" (**needs tenant**)
```powershell
./Invoke-TeamsGovernance.ps1 -PolicyFile ./governance.lab.json -Audit -OutFile ./teams-audit.md -SaveInventory ./inventory.json
```
Expected rows: *Old Offsite 2024 — Ownerless (High)*, *Sales Partner Portal — GuestsInPublicTeam (High)* and
*NamingConvention (Low)*, *Project Falcon — TooFewOwners (Medium)* and *NamingConvention (Low)*. If the usage report
is concealed (episode 1 default), expect the *ActivityUnavailable* Info row instead of Inactive rows — that's correct
behaviour, say so in the narration. Rewrite the narration's specifics to match the screen. Scopes:
`Team.ReadBasic.All`, `TeamMember.Read.All`, `Reports.Read.All`.

### 4. `screens/exempt.jpg` — "The gotcha: admins skip the naming policy" (**needs tenant**, changes tenant settings)
```powershell
./Invoke-TeamsGovernance.ps1 -PolicyFile ./governance.lab.json -ApplyTenantPolicy -WhatIf   # show the values first
./Invoke-TeamsGovernance.ps1 -PolicyFile ./governance.lab.json -ApplyTenantPolicy           # confirm (ConfirmImpact High)
```
Wait until it applies (Microsoft: creation restriction can take 30 minutes or more). Then capture:
- Entra admin center → Groups → **Naming policy**: `TEAM_[Department]_[GroupName]` and the blocked words.
- Split screen: **Alex** in Teams creates team "CEO office" → blocked-word error (and the prefix preview for a valid
  name). **Global Administrator** creates a Microsoft 365 group "CEO office" in the Entra admin center → succeeds,
  no prefix.
Mask the tenant name and the admin's UPN.

## Masking checklist
- Tenant name/domain, admin UPN, object IDs, team IDs, the real Team Creators group ID.
- Don't show `inventory.json` / `teams-audit.md` from the lab in full if they contain real people.

## Tear-down
1. Revert the tenant setting: set `"restrict": false` and empty `prefixSuffix` / `blockedWords` in
   `governance.lab.json` and run `-ApplyTenantPolicy` again (or Entra admin center → Naming policy → Delete policy, and
   re-enable group creation). Check `EnableGroupCreation = true`.
2. Delete the test group "CEO office", and the seeded teams (Project Falcon, Sales Partner Portal, Old Offsite 2024,
   TEAM_Finance_Budget 2027) unless the lab keeps them for episode 3 (Groups lifecycle).
3. Delete `governance.lab.json`, `inventory.json`, `teams-audit.md`; `Disconnect-MgGraph`.
4. Remove any delegated consent granted only for the recording.
