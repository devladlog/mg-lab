# Demo shot list — DEVLADLOG Microsoft 365 #3: Microsoft 365 Groups Lifecycle

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure / Power Platform | none |
| Tenant | Lab tenant: Entra admin center (Groups → Expiration, Deleted groups), Microsoft Graph. Changes the tenant's group expiration policy (state noted in setup, restored in tear-down). Reuses episode 2's teams |
| Lab users | **`labadmin`** (the recording account) with **Groups Administrator** (policy, renew, restore) and **Teams Administrator** (archive); its mailbox receives the ownerless-group notices (`alternateNotificationEmails` in the local lab copy only). **`alex.demo` (Alex Demo)** creates the two extra groups |
| Licences / trials | E5 trial (Entra ID P1 for expiration); cost 0 |
| Recording machine | The Windows lab laptop: PowerShell 7.2+ with `Microsoft.Graph.Authentication`, browser with `pipeline/mask.js` |

Everything in `src/` and `tests/` already ran in the build container (47 Pester tests with the real
Microsoft.Graph.Authentication module present, offline audit, offline rollout-impact preview). This file lists what
the human-supervised session must set up and record in the **lab tenant**. Every Graph call below is **needs tenant**.

## Prerequisites

| Item | Notes | Cost |
|---|---|---|
| Lab tenant (exists) with the episode 2 teams | `Project Falcon` (1 owner), `Old Offsite 2024` (ownerless), `TEAM_Sales_Partner Portal`, `TEAM_Finance_Budget 2027` | none |
| **Microsoft Entra ID P1** for the members of the groups under the policy | Microsoft 365 E5 in the lab includes it | included |
| Admin account | `labadmin` with **Groups Administrator** is enough for the policy, renew and restore (Learn: Groups Administrator or User Administrator manage the expiration policy); **Teams Administrator** for the archive shot | none |
| PowerShell 7.2+ + `Microsoft.Graph.Authentication` | `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser` | none |
| Admin mailbox for ownerless notices | `labadmin`'s mailbox (or a shared mailbox created for the episode); put the real address only in the local lab copy | none |
| Browser with `pipeline/mask.js` | Entra admin center | none |

Delegated scopes the runner asks for: `Directory.Read.All`, `Group.Read.All`, `GroupMember.Read.All` (audit);
`Directory.ReadWrite.All` (policy + addGroup); `Group.ReadWrite.All` (renew, restore); `TeamSettings.ReadWrite.All`
(archive).

## Setup (before recording)

1. **Record the current state first.** Entra admin center → Groups → Expiration: note lifetime, scope and email
   (or "no policy"), so tear-down can put it back. If the lab already has a policy set to **All**, read the gotcha
   section below before changing anything.
2. Create two extra Microsoft 365 groups (not teams) as Alex Demo: **Contoso Book Club** and **Temp Project Kickoff**.
   Delete **Temp Project Kickoff** (Entra → Groups → select → Delete) — it's the restore target.
3. Copy `src/lifecycle.json` to an uncommitted `src/lifecycle.lab.json`: put the object IDs of `Project Falcon`,
   `Old Offsite 2024`, `TEAM_Sales_Partner Portal`, `TEAM_Finance_Budget 2027` in `selectedGroupIds` and the admin
   mailbox in `alternateNotificationEmails`. Pass `-PolicyFile ./lifecycle.lab.json` to every command below.
4. Run the tests on the recording machine: `pwsh -NoProfile -Command 'Invoke-Pester ./tests'` → `Tests Passed: 47`
   (45 + 2 skipped if Microsoft.Graph.Authentication isn't installed).
5. Terminal: dark theme, font 18+, prompt `PS> `.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/policy.jpg` — "WhatIf, then apply" (**needs tenant**, changes a tenant setting)
```powershell
cd src
./Invoke-GroupsLifecycle.ps1 -PolicyFile ./lifecycle.lab.json -ApplyExpirationPolicy -WhatIf
./Invoke-GroupsLifecycle.ps1 -PolicyFile ./lifecycle.lab.json -ApplyExpirationPolicy      # confirm (ConfirmImpact High)
```
Expected: impact table (selected groups without an expiration date: older than 180 days → `SetTo35Days`), then
`Policy | <id> | Created` (or `Updated: …`) and one `AddGroup | <id> | Added` per selected group. Then Entra admin
center → Groups → Expiration: 180 days, **Selected**, the alternate email, the four groups.
**Verify and note in README**: what `addGroup` returns for a group that is already in the list (true or false) —
not documented; the script reports whatever it gets.

### 2. `screens/audit.jpg` — "The audit, live" (**needs tenant**, read-only)
```powershell
./Invoke-GroupsLifecycle.ps1 -PolicyFile ./lifecycle.lab.json -Audit -OutFile ./lifecycle-audit.md -SaveInventory ./inventory.lab.json
```
Expected rows: `Old Offsite 2024 — OwnerlessExpiring (High)` (detail names the admin mailbox now that it's set),
`Project Falcon — SingleOwner (Low)`, `Temp Project Kickoff — Restorable (Info)`. `ExpiringSoon` won't show on new
expiration dates (they're ~180 days away) — that's expected; the fictional sample in `sample/lifecycle-audit.md`
shows it. Rewrite the narration's specifics to match the screen.

### 3. `screens/rollout.jpg` — "The gotcha: old groups get 35 days" (**needs tenant**, read-only — do NOT confirm)
Temporarily set `"managedGroupTypes": "All"` in `lifecycle.lab.json`, then:
```powershell
./Invoke-GroupsLifecycle.ps1 -PolicyFile ./lifecycle.lab.json -ApplyExpirationPolicy -WhatIf
```
Capture the impact table (`Contoso Book Club` etc. → `SetTo35Days`, `ExpiresAround`). Answer **No**/use -WhatIf only.
Set the file back to `Selected` immediately afterwards. The groups seeded for episodes 2–3 are only days old, so
unless the lab has older groups the table will show `WithinLifetime` only. In that case record the same preview
from the fictional inventory (no tenant needed) and change the bar to "rollout impact preview (fictional inventory)":
```powershell
./Invoke-GroupsLifecycle.ps1 -PolicyFile ./lifecycle.lab.json -ApplyExpirationPolicy -ImpactInventoryFile ../tests/fixtures/inventory.json -Now 2026-11-20T09:30:00Z -WhatIf
```
(with `All` in the file this lists `TEAM_Sales_Partner Portal` and `Contoso Book Club` → `SetTo35Days`, 2026-12-25).

### 4. `screens/restore.jpg` — "Deleted by mistake, back in a minute" (**needs tenant**)
Entra admin center → Groups → **Deleted groups**: `Temp Project Kickoff` listed. Then:
```powershell
./Invoke-GroupsLifecycle.ps1 -PolicyFile ./lifecycle.lab.json -Restore <Temp Project Kickoff id>     # confirm
```
Expected `Status : Restored`; refresh All groups → it's back.

### Optional (not in the script): renew and archive
```powershell
./Invoke-GroupsLifecycle.ps1 -PolicyFile ./lifecycle.lab.json -Renew <Project Falcon id> -WhatIf
./Invoke-GroupsLifecycle.ps1 -PolicyFile ./lifecycle.lab.json -Archive <Old Offsite 2024 id>   # expect "has no owner" — the point of the archive scene
```

## Masking checklist
- Tenant name/domain, admin UPN, the admin mailbox address, group IDs, policy ID.
- Don't show `inventory.lab.json` / `lifecycle-audit.md` from the lab in full if they contain real people.

## Tear-down
1. Put the expiration policy back to the state noted in setup step 1 (Entra → Groups → Expiration, or
   `Remove-MgGroupLifecyclePolicy` if there was none). Removing the policy disables expiration.
2. Delete `Contoso Book Club` and `Temp Project Kickoff` unless the lab keeps them for later episodes (episode 4
   reuses `TEAM_Sales_Partner Portal` and its guest).
3. Delete `lifecycle.lab.json`, `inventory.lab.json`, `lifecycle-audit.md`; `Disconnect-MgGraph`.
