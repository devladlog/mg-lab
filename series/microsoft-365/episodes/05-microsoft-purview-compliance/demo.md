# Demo shot list — DEVLADLOG Microsoft 365 #5: Microsoft Purview Compliance

Everything in `src/` and `tests/` already ran in the build container (60 Pester tests with the real
ExchangeOnlineManagement module present, offline plan and audit against `tests/fixtures/inventory.json`, test-file
generator). This file lists what the human-supervised session must set up and record in the **lab tenant**. Every
Security & Compliance cmdlet below is **needs tenant**.

## Lab environment

No VMs and no Azure resources. Everything is in the lab tenant (Microsoft 365 E5 trial, ends 20 Dec 2026) and runs
from the recording laptop (PowerShell 7 + browser). Cost: none beyond the existing trial.

| Item | Notes | Cost |
|---|---|---|
| Microsoft 365 E5 trial | Manual labels and DLP for Exchange/SharePoint/OneDrive are E3 features; DLP for Teams chat needs E5 — all covered by the trial | in the lab |
| Recording account `labadmin` | **Compliance Administrator** (labels, DLP, retention). Turning on labels for SharePoint/OneDrive in the portal needs **Global Administrator** once (or SharePoint admin + `Set-SPOTenant`) | none |
| Lab users | `alex.demo`, `sam.demo` (pilot group of the label policy, together with `labadmin`). Nothing else to configure | none |
| PowerShell 7.2+ with `ExchangeOnlineManagement` 3.2+ | `Install-Module ExchangeOnlineManagement -Scope CurrentUser` (REST mode for `Connect-IPPSSession`) | none |
| Browser with `pipeline/mask.js` | Purview portal as Lab Admin; a **second browser profile** signed in as Alex Demo (Word, Outlook, OneDrive) | none |

## Setup (the day before recording)

Labels and label policies can take **up to 24 hours** to reach all apps; retention labels **up to 7 days** in
Exchange (about a day in SharePoint/OneDrive). Deploy at least one day before the label and DLP screens.

1. Copy `src/compliance.json` to an uncommitted `src/compliance.lab.json` and replace `contoso.onmicrosoft.com` in
   `labelPolicy.publishTo` with the lab domain. Pass `-PolicyFile ./compliance.lab.json` everywhere below.
2. Purview portal → Information Protection → Sensitivity labels: if the banner offers to turn on processing of
   content in Office online files, select **Turn on now** (Global Administrator), or run
   `Set-SPOTenant -EnableAIPIntegration $true` in SharePoint Online PowerShell. Takes about 15 minutes. Without it,
   Word on the web has no Sensitivity button and DLP can't see labels on files in SharePoint/OneDrive.
3. Check what already exists (a new tenant may have default labels or a default Teams DLP policy):
   `./Invoke-PurviewCompliance.ps1 -PolicyFile ./compliance.lab.json -Audit -SaveInventory ./inventory.lab.json`.
   If default labels exist with the same display names, rename ours in the lab copy — don't delete theirs on camera.
4. Run **screen 1** (plan + deploy). That's the only step that must happen ≥ 24 h before screens 2–4.
5. Offline check on the recording laptop: `pwsh -NoProfile -Command 'Invoke-Pester ./tests'` → 59 passed, 1 skipped
   (60 passed with ExchangeOnlineManagement installed).
6. Terminal: dark theme, font 18+, prompt `PS> `.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/plan.jpg` — "Plan, then deploy" (**needs tenant**, creates labels and policies)
```powershell
cd src
Connect-IPPSSession -UserPrincipalName <labadmin UPN>
./Invoke-PurviewCompliance.ps1 -PolicyFile ./compliance.lab.json -Plan
./Invoke-PurviewCompliance.ps1 -PolicyFile ./compliance.lab.json -Deploy -WhatIf
./Invoke-PurviewCompliance.ps1 -PolicyFile ./compliance.lab.json -Deploy          # confirm each step, or -Confirm:$false
```
Expected on a clean tenant: 12 steps `Create` → 12 `WhatIf` (nothing created — check the portal) → 12 `Created`.
Then the Purview portal: **Information Protection → Sensitivity labels** (Public, General, Confidential),
**Label policies** (Contoso labels - pilot), **Data loss prevention → Policies** (both policies, status in simulation
with notifications), **Data lifecycle management / Records management → Retention labels** (Contoso Contract - 7 years).
If the retention rule step says `Wait`, the policy is still Pending: run `-Deploy` again later (Learn: don't change a
Pending policy). **Verify and note in README**: that `Get-LabelPolicy` returns label *names* in `Labels` and the format
of `PublishComplianceTag` on `Get-RetentionComplianceRule` (the audit matches by name; adjust if they come back as GUIDs).

### 2. `screens/label.jpg` — "Alex labels a document Confidential" (**needs tenant**, ≥ 24 h after screen 1)
As **Alex Demo**: OneDrive → New → Word document "Q4 supplier contract" → **Home → Sensitivity**: Public, General,
Confidential with their tooltips → **Confidential** → the red, centered header `CONFIDENTIAL - Contoso internal`
appears. If the Sensitivity button is missing: step 2 of the setup wasn't done, or the label policy hasn't reached
Alex yet (sign out and in again; don't fake it).

### 3. `screens/dlp-tip.jpg` — "The policy tip in Outlook" (**needs tenant**, ≥ 1 h after screen 1)
```powershell
./Invoke-PurviewCompliance.ps1 -NewTestFile -TestFilePath ./contoso-dlp-test.txt -Count 12
```
As **Alex Demo** in Outlook on the web: New mail → To `partner@example.com` (reserved example domain), subject
"Customer list", paste the 12 generated lines into the body. The policy tip shows the custom text of the high-count
rule ("Blocked: 10 or more card numbers can't leave Contoso…"). **Discard the draft — never press Send.** Nothing
leaves the tenant. The numbers are synthetic (random, Luhn-valid, no names, no expiry, no CVV); don't use the
well-known test card numbers — the Credit Card Number type ignores reserved test numbers.
**Verify and note in README**: the policy tip appears in simulation-with-notifications mode in Outlook on the web
(Learn: users receive policy tips in that mode). If the tip doesn't show after an hour, check
`Get-DlpCompliancePolicy -Identity 'Contoso - Card numbers' -DistributionDetail`.

### 4. `screens/simulation.jpg` — "Review the simulation, then promote" (**needs tenant**, changes enforcement)
As **Alex Demo**: OneDrive → New Word document "Customer list" → paste the same 12 lines → close. **Don't share it.**
Next day (or when it shows): Purview portal → **Data loss prevention → Policies → Contoso - Card numbers → View
simulation**: Simulation overview with the matched item, **Items for review** lists "Customer list.docx". Then:
```powershell
./Invoke-PurviewCompliance.ps1 -Promote -PolicyName 'Contoso - Card numbers' -Mode Enable
```
Expected: `From TestWithNotifications  To Enable  Result Changed (takes effect in about an hour)`. Don't promote the
Confidential-label policy on camera (not needed).

### Audit scene (not a screen)
The `audit` scene in script.yaml shows the offline audit of the fictional inventory (`sample/purview-audit.md`, real
output of this code). Optionally also run `-Audit` against the lab after screen 4 for the README; mask UPNs.

## Masking checklist
- Tenant name/domain, admin UPN, Alex's address, OneDrive/SharePoint URLs, policy GUIDs.
- The generated test file contains synthetic numbers only — still keep it off screen except the Outlook body.

## Tear-down (before the trial ends on 20 Dec 2026)
1. `Remove-DlpComplianceRule` for the three rules, then `Remove-DlpCompliancePolicy` for `Contoso - Card numbers` and
   `Contoso - Confidential label`.
2. `Remove-RetentionComplianceRule` for the rule of `Contoso retention labels`, then `Remove-RetentionCompliancePolicy`,
   then `Remove-ComplianceTag 'Contoso Contract - 7 years'` (only if it was never applied to content).
3. `Remove-LabelPolicy 'Contoso labels - pilot'`, then remove the three labels (`Remove-Label`) — Learn: don't delete
   labels you still need; files labeled in the lab keep the label metadata.
4. Delete "Q4 supplier contract" and "Customer list" from Alex's OneDrive (and the recycle bin), discard any drafts.
5. Delete `contoso-dlp-test.txt`, `compliance.lab.json`, `inventory.lab.json`; `Disconnect-ExchangeOnline`.
