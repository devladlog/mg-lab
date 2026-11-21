# Demo shot list — DEVLADLOG Microsoft 365 #4: Entra ID Governance & Identity

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure / Power Platform | none. **Do not link an Azure subscription** on the ID Governance dashboard (guest governance billing) |
| Tenant | Lab tenant: Entra admin center (PIM, Access reviews, Lifecycle workflows), My Access, Microsoft Graph. Reuses episode 2's guest and `TEAM_Sales_Partner Portal` |
| Lab users | **`labadmin`** (the recording account): Privileged Role Administrator, Identity Governance Administrator, Lifecycle Workflows Administrator. **`alex.demo` (Alex Demo)**: eligible Groups Administrator, owner/reviewer (second browser profile). **`jordan.demo` (Jordan Demo)** replaces "Megan Sample" of the test fixtures. Emergency access accounts: the lab has none, so leave that list empty in the local copy and record what the audit says |
| Extra objects (created and deleted in this episode) | Throwaway member **`sam.leaver`** ("Sam Leaver", Department `Sales`, E5 + Entra ID Governance trial licences while it exists): the leaver workflow revokes its sessions, removes all its group and team memberships and disables it, which must never run on a shared lab user such as `sam.demo`. Microsoft 365 group **Sales Pipeline Review** (Sam Leaver sole owner) |
| Licences / trials | E5 trial (Entra ID P2) + **Entra ID Governance trial, ends 20 Dec 2026**: record before ~15 Dec; cost 0 |
| Recording machine | The Windows lab laptop: PowerShell 7.2+ with `Microsoft.Graph.Authentication`, browser with `pipeline/mask.js`; a second browser profile signed in as Alex Demo (activation, review) |

Everything in `src/` and `tests/` already ran in the build container (53 Pester tests with the real
Microsoft.Graph.Authentication module present, offline audit, offline `-Preview` of the three request bodies). This
file lists what the human-supervised session must set up and record in the **lab tenant**. Every Graph call below is
**needs tenant**.

## Prerequisites

| Item | Notes | Cost |
|---|---|---|
| Microsoft 365 E5 (includes **Entra ID P2**) | PIM and basic access reviews | in the lab |
| **Entra ID Governance** trial (ends **20 Dec 2026**) | Lifecycle workflows need it. **Record before ~15 Dec.** When it ends, eligible assignments are removed and time-bound active assignments become permanent (Learn) — plan the tear-down before that date | trial, free |
| **No guest governance billing** | Do **not** link an Azure subscription on the ID Governance dashboard. Everything in this episode stays on P2/employee-licence features: basic guest review (no inactive-user scope, no user-to-group affiliation), workflow scoped to members. The script refuses the billable settings | none |
| Admin roles for `labadmin` (recording account) | **Privileged Role Administrator** (PIM writes), **Identity Governance Administrator** (access reviews), **Lifecycle Workflows Administrator** (workflows); Global Reader is enough for the audit | none |
| Users | **Alex Demo** (`alex.demo`), **Jordan Demo** (`jordan.demo`), the fictional **guest** in `TEAM_Sales_Partner Portal` (episode 2), emergency access accounts (none in the lab), and the throwaway **Sam Leaver** (`sam.leaver`, Department = `Sales`) | none |
| PowerShell 7.2+ + `Microsoft.Graph.Authentication` | `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser` | none |
| Browser with `pipeline/mask.js` | Entra admin center; a second browser profile signed in as Alex (activation, review) | none |

Delegated scopes the runner asks for: audit `RoleAssignmentSchedule.Read.Directory`, `RoleEligibilitySchedule.Read.Directory`,
`AccessReview.Read.All`, `LifecycleWorkflows-Workflow.ReadBasic.All`; `-AssignEligible`
`RoleEligibilitySchedule.ReadWrite.Directory`; `-CreateGuestReview` `AccessReview.ReadWrite.All`; `-CreateLeaverWorkflow`
`LifecycleWorkflows-Workflow.ReadWrite.All`; `-RunLeaver` `User.Read.All`, the two schedule read scopes,
`GroupMember.Read.All`, `LifecycleWorkflows-Workflow.Read.All`, `LifecycleWorkflows-Workflow.Activate`.

## Setup (before recording)

1. Copy `src/governance.json` to an uncommitted `src/governance.lab.json`: real object IDs for Alex (eligible
   assignment + fallback reviewer) and the emergency access accounts. Keep `governanceLicenceEndsOn` = `2026-12-20`.
   Pass `-PolicyFile ./governance.lab.json` everywhere below.
2. Create **Sam Leaver** (Member, Department `Sales`). In PIM give Sam a **time-bound active** Groups Administrator
   assignment (e.g. 7 days). Create a Microsoft 365 group **Sales Pipeline Review** with Sam as the **only owner**.
3. Make sure the episode 2 guest is still a member of `TEAM_Sales_Partner Portal`.
4. Offline check on the recording machine: `pwsh -NoProfile -Command 'Invoke-Pester ./tests'` → `Tests Passed: 53`
   (51 + 2 skipped without the Graph module); `./Invoke-IdentityGovernance.ps1 -Preview` shows `Guest governance add-on needed: no`.
5. Terminal: dark theme, font 18+, prompt `PS> `.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/pim.jpg` — "Just-in-time Groups Administrator" (**needs tenant**, changes role assignments)
```powershell
cd src
./Invoke-IdentityGovernance.ps1 -PolicyFile ./governance.lab.json -AssignEligible -WhatIf
./Invoke-IdentityGovernance.ps1 -PolicyFile ./governance.lab.json -AssignEligible
```
Expected: `Alex Demo | Groups Administrator | Provisioned` (a second run shows `AlreadyEligible`). Entra admin center →
ID Governance → Privileged Identity Management → Microsoft Entra roles → Assignments → **Eligible assignments**: Alex,
Groups Administrator, end ≈ 180 days. As Alex: **My roles → Activate** with a justification → active until the
activation end. **Verify and note in README**: the `status` value the API returns for the request (Learn's example
shows `Provisioned`; approval settings on the role can change it).

### 2. `screens/review.jpg` — "The partner guest gets reviewed" (**needs tenant**)
```powershell
./Invoke-IdentityGovernance.ps1 -PolicyFile ./governance.lab.json -CreateGuestReview -StartDate (Get-Date).Date
```
Expected `Created (…)`. Entra admin center → ID Governance → **Access reviews** → the review → one instance per
group with guests (`TEAM_Sales_Partner Portal`). As Alex (owner): myaccess.microsoft.com → Access reviews → the guest
with Approve/Deny. Don't submit a decision on camera unless you want the guest removed at the end. Mask the guest's
address. If the instance list is empty, wait (instances can take a while to start) — don't fake it.

### 3. `screens/leaver.jpg` — "Sam's last day" (**needs tenant**, disables Sam)
```powershell
./Invoke-IdentityGovernance.ps1 -PolicyFile ./governance.lab.json -CreateLeaverWorkflow      # -> Created, note the Id
./Invoke-IdentityGovernance.ps1 -PolicyFile ./governance.lab.json -RunLeaver -WorkflowId <id> -UserId <Sam>
```
First run: `Sam Leaver: Blocked` with `HoldsEntraRole` (Blocker) and `SoleOwner` (Warning). Then remove Sam's
Groups Administrator assignment in PIM and add Alex as second owner of Sales Pipeline Review; run again and confirm →
`Started`. Entra admin center → ID Governance → **Lifecycle workflows** → the workflow → **Workflow history** → Sam,
4 tasks. **Verify and note in README**: the role-assignment instance can take a moment to disappear after removal;
if the second run still says Blocked, wait and retry (don't use `-Force` on camera).

### 4. `screens/audit.jpg` — "The gotcha: when the licence ends" (**needs tenant**, read-only)
```powershell
./Invoke-IdentityGovernance.ps1 -PolicyFile ./governance.lab.json -Audit -OutFile ./governance-audit.md -SaveInventory ./inventory.lab.json
```
Expected: `Tenant — LicenceEnding (High)` with the real counts, plus whatever else the lab really has (the recording
admin's own permanent Global Administrator assignment will likely appear as `PermanentActivePrivileged` — that's an
honest finding; mask the UPN). `NoGuestReview` should be gone after screen 2. Rewrite narration numbers to match.

## Masking checklist
- Tenant name/domain, admin UPN, guest email, all object IDs, workflow/review/request IDs.
- `inventory.lab.json` and `governance-audit.md` contain real role holders: don't show them in full.

## Tear-down (before the trial ends on 20 Dec 2026)
1. PIM: remove Alex's eligible Groups Administrator assignment (or let it go — it is removed when the trial ends anyway,
   but don't rely on that).
2. Access reviews: stop/delete "Quarterly review - guests in Microsoft 365 groups" (so no decision is auto-applied).
3. Lifecycle workflows: delete the leaver workflow (it goes to deleted workflows first).
4. Delete Sam Leaver (then permanently delete it from Deleted users, freeing the licences) and Sales Pipeline Review.
5. Delete `governance.lab.json`, `inventory.lab.json`, `governance-audit.md`; `Disconnect-MgGraph`; remove delegated
   consent granted only for the recording.
