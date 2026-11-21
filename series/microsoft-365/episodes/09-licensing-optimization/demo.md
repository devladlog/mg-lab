# Demo shot list — DEVLADLOG Microsoft 365 #9: Licensing Optimization

Everything in `src/` and `tests/` already ran in the build container (55 Pester tests, an offline report from a fictional snapshot). This file lists what the
human-supervised session must set up and record in the **lab tenant**. Every Graph call below is **needs tenant**; every screen shows the real product (the real
admin center, the script talking to the real Graph). `tests/fixtures/*` and `sample/` are for the automated tests only and never appear on screen.

The demo only uses **trial licences already in the lab**: no purchase, no cost. The prices shown in the report are the ones typed into `licensing.lab.json`
and are **examples, not Microsoft's and not what the lab pays** (the trials are free). Say that on camera (the script's hook does).

## Lab environment

No VM. Recorded on the **lab Windows desktop**: a browser on the lab tenant (Microsoft 365 admin center, Entra admin center) and PowerShell 7.2+ on the host.

| Cloud item | Notes | Cost / requirement |
|---|---|---|
| Microsoft 365 E5 trial (already in the lab, until 20 Dec 2026) | Includes Entra ID P2, which `signInActivity` needs (Learn: Entra ID P1 or P2 plus `AuditLog.Read.All`) | in the lab |
| Other trials in the lab | Entra ID Governance, Dynamics 365 Sales, Business Standard, Copilot Studio (see `series/LAB.md`): they give the audit real SKUs to look at | in the lab |
| Lab users | `labadmin` (recording account, Global Administrator), `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo` | none |
| Roles | `labadmin` as Global Administrator covers Reports Reader (sign-in data), License Administrator (assign licences) and role reading | none |
| Graph scopes (delegated, consent for `labadmin`) | Audit: `LicenseAssignment.Read.All`, `User.Read.All`, `AuditLog.Read.All`, `RoleManagement.Read.Directory`. Reclaim/restore add `LicenseAssignment.ReadWrite.All`. Optional group set-up adds `Group.ReadWrite.All` | none |
| Host PowerShell | PowerShell 7.2+, `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser` | none |

## Setup (before recording)

1. **Module.** `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser`.
2. **Config.** Copy `src/licensing.json` to `licensing.lab.json` (outside the repo) and edit it:
   - `inactivity.inactiveDays`: `3`, `neverSignedInGraceDays`: `0` (the lab is days old; say so on camera, production default is 90 and 30).
   - `prices.perUserPerMonth`: **example** numbers for the `skuPartNumber` values you see after step 4 (for instance `SPE_E5` 50, the Dynamics trial 0).
   - `reclaim.allowedSkuPartNumbers`: leave empty until step 4 tells you the exact `skuPartNumber` of the **Dynamics 365 Sales trial** (its real name is not verified: read it from the first audit),
     then put only that one in the list.
3. **Who has signed in.** Do **not** sign in as `riley.demo` and `taylor.demo` before recording (they should be `NeverSignedIn`). `alex.demo` signs in for episode 8; if the lab users already signed in
   during other recordings, the audit shows whatever is true: say so, don't edit it.
4. **Dry run, off camera** (also tells you the real SKU names and the Graph consent screens):
   ```powershell
   Connect-MgGraph -Scopes LicenseAssignment.Read.All, User.Read.All, AuditLog.Read.All, RoleManagement.Read.Directory -NoWelcome
   ./Invoke-LicensingOptimization.ps1 -ConfigFile ./licensing.lab.json -SaveSnapshot ./snapshot.lab.json -OutFile ./audit.lab.md
   ```
   Check: `signInActivity` came back (no `NoSignInData` finding); `labadmin` is not in the reclaim plan; the Dynamics trial `skuPartNumber`.
   If Graph answers 403 on the users call, the message names the cause (P1/P2, permission, role): fix the consent, don't fall back to a snapshot.
5. **Make one disabled account for real.** Entra admin center (or Microsoft 365 admin center) > Users > `taylor.demo` > block sign-in. This sets `accountEnabled` to false while the licences stay.
   Re-enabled in tear-down.
6. **Optional, a real duplicate (direct + group), needs `Group.ReadWrite.All`, Entra ID P1 (included in E5):**
   ```powershell
   Connect-MgGraph -Scopes Group.ReadWrite.All, LicenseAssignment.ReadWrite.All, User.Read.All -NoWelcome
   $g = Invoke-MgGraphRequest -Method POST -Uri /v1.0/groups -ContentType 'application/json' -Body (@{ displayName = 'MG Lab - Licence test'; mailEnabled = $false; mailNickname = 'mglab-licence-test'; securityEnabled = $true } | ConvertTo-Json)
   $sku = (Invoke-MgGraphRequest -Uri /v1.0/subscribedSkus).value | Where-Object skuPartNumber -eq 'Microsoft_Entra_ID_Governance'   # same SKU that alex.demo already holds directly
   Invoke-MgGraphRequest -Method POST -Uri "/v1.0/groups/$($g.id)/assignLicense" -ContentType 'application/json' -Body (@{ addLicenses = @(@{ skuId = $sku.skuId; disabledPlans = @() }); removeLicenses = @() } | ConvertTo-Json -Depth 4)
   $alex = (Invoke-MgGraphRequest -Uri "/v1.0/users/alex.demo@<lab domain>").id
   Invoke-MgGraphRequest -Method POST -Uri "/v1.0/groups/$($g.id)/members/`$ref" -ContentType 'application/json' -Body (@{ '@odata.id' = "https://graph.microsoft.com/v1.0/directoryObjects/$alex" } | ConvertTo-Json)
   ```
   Group licence processing is not instant: wait for the group's licence to show on `alex.demo` before the audit. Expect a `DuplicateDirectAndGroup` row. **Not verified**: that Graph shows two
   `licenseAssignmentStates` entries for one SKU, and what `removeLicenses` does to a licence held both ways. If the row doesn't appear, skip this beat (nothing in the script depends on it) and say nothing about it.
7. **Optional, a real redundant licence:** Microsoft 365 admin center > Active users > `sam.demo` > Licenses and apps > add **Microsoft 365 Business Standard** next to E5. Learn lists conflicting
   service plans as a cause of assignment errors, so the service may refuse (Exchange Online Plan 1 vs Plan 2): if it refuses, record the refusal as a short gotcha and skip the `RedundantLicence` beat.

## Screens to capture (match `script.yaml` screen scenes)

### 1. `screens/licences.jpg` — "What the tenant holds" (admin center)
Microsoft 365 admin center > Billing > **Licenses**, as `labadmin`: the trial products with Available and Assigned counts. Open one product (Users tab, Groups tab) to show who holds it.
Mask the tenant name. Rewrite the narration to the real numbers.

### 2. `screens/audit.jpg` — "The audit, on real data" (needs tenant, read-only)
```powershell
./Invoke-LicensingOptimization.ps1 -ConfigFile ./licensing.lab.json -OutFile ./audit.lab.md
```
Capture the findings table (rule, user, licence, how assigned, reclaimable, saving), the totals line, the "Seats paid for but not assigned" table and the "Reclaim plan" line. Show that a group-assigned licence
(if step 6 was done) is marked not reclaimable. Rewrite the narration to the real rows. Mask UPN domains; the SKU ids are not in the table.

### 3. `screens/reclaim.jpg` — "Preview, remove, restore" (needs tenant, **writes**)
1. `./Invoke-LicensingOptimization.ps1 -ConfigFile ./licensing.lab.json -Reclaim -RollbackFile ./rollback.lab.json -WhatIf` : "What if" lines, nothing removed, no rollback file on disk (show `Test-Path`).
2. Same command without `-WhatIf` (needs `LicenseAssignment.ReadWrite.All`: the runner asks for consent). It asks to confirm each removal (`ConfirmImpact = High`): answer **Yes only for `riley.demo`** and No for the others.
3. Microsoft 365 admin center > Active users > `riley.demo` > Licenses and apps: the Dynamics trial is unchecked/gone. Show `rollback.lab.json` (skuId and user ids masked or cropped).
4. `./Invoke-LicensingOptimization.ps1 -Restore ./rollback.lab.json` : `Restored`. Refresh the admin center: back. (Licence changes can take a moment to show.)
Rewrite the narration to the real user and licence. Removing a trial seat has no cost and no mailbox risk for a never-used lab account; **do not run this against any other account**.

## Masking checklist
- Tenant name/domain, admin UPN, user addresses beyond the lab aliases, SKU and user object ids, group ids.
- `licensing.lab.json`, `snapshot.lab.json`, `audit.lab.md`, `rollback.lab.json` contain tenant data: don't show them in full, never commit them.

## Tear-down (before the trial ends on 20 Dec 2026)
1. If anything is still removed: `./Invoke-LicensingOptimization.ps1 -Restore ./rollback.lab.json`, then check each lab user's licences against `series/LAB.md` (E5, Entra ID Governance, Dynamics 365 Sales trial).
2. Re-enable `taylor.demo` (unblock sign-in).
3. Delete the group **MG Lab - Licence test** (remove its licence first: `POST /groups/{id}/assignLicense` with `removeLicenses`; Learn says a licensed group must have its licences removed before deletion) and remove Business Standard from `sam.demo` if it was added.
4. Delete `licensing.lab.json`, `snapshot.lab.json`, `audit.lab.md`, `rollback.lab.json`; `Disconnect-MgGraph`; remove the delegated consent granted only for the recording.
