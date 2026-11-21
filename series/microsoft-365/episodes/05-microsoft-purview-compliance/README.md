# DEVLADLOG Microsoft 365 #5 — Microsoft Purview Compliance

**Microsoft Purview as code.** One file ([`src/compliance.json`](src/compliance.json)) drives the three Purview
controls most tenants start with, through Security & Compliance PowerShell:

1. **Sensitivity labels** — Public, General, Confidential (with a red header), published by a label policy to a
   **pilot group** of mailboxes, not the whole tenant (`New-Label`, `New-LabelPolicy`).
2. **Data loss prevention** — two policies, both starting in **simulation with policy tips**
   (`TestWithNotifications`):
   - *Contoso - Card numbers* (Exchange, SharePoint, OneDrive, Teams): the shape of Microsoft's PCI DSS template —
     1–9 card numbers shared outside: notify; 10+: block external access, override with justification, incident report.
   - *Contoso - Confidential label* (Exchange, SharePoint, OneDrive — **not Teams**): block external sharing of
     content labeled Confidential.
3. **Retention** — a retention label (keep 7 years from creation, then delete) published by a retention label policy
   (`New-ComplianceTag`, `New-RetentionCompliancePolicy`, `New-RetentionComplianceRule -PublishComplianceTag`).
4. **Plan / deploy** — `Get-PurviewPlan` compares the file with the tenant (Create / Exists / Drift / Wait) and
   `Invoke-PurviewPlan` creates what's missing in dependency order, with **its own `-WhatIf`**, because the WhatIf
   switch doesn't work in Security & Compliance PowerShell. Never deletes, never changes a DLP mode on its own.
5. **Promote** — `Set-PurviewDlpMode` moves a policy from simulation to `Enable` after review (refuses while the
   policy is still distributing).
6. **Audit** — `Get-PurviewInventory` + `Get-PurviewFinding`: distribution errors, simulations running past 15 days,
   labels nobody can apply, unpublished retention labels, label conditions in policies that include Teams, record
   labels, Preservation Lock, drift from the file.
7. **Test data** — `New-DlpTestContent`: synthetic Luhn-valid card numbers next to a keyword, because the Credit Card
   Number type ignores reserved test card numbers.

Same fictional tenant as episodes 1–4 (`contoso`, Alex Demo); the lab users are `labadmin`, `alex.demo`, `sam.demo`.

| Path | What it is |
|---|---|
| [`src/compliance.json`](src/compliance.json) | 3 labels + pilot label policy, 2 DLP policies (3 rules) in simulation, 1 retention label + its policy, audit threshold (15 days) |
| [`src/PurviewCompliance/PurviewCompliance.psm1`](src/PurviewCompliance/PurviewCompliance.psm1) | The module: config validation, pure parameter builders, plan, findings, test data + the functions that call Security & Compliance PowerShell |
| [`src/PurviewCompliance/PurviewCompliance.psd1`](src/PurviewCompliance/PurviewCompliance.psd1) | Module manifest |
| [`src/Invoke-PurviewCompliance.ps1`](src/Invoke-PurviewCompliance.ps1) | Runner: `-Plan`, `-Deploy [-WhatIf]`, `-Audit`, `-Promote`, `-NewTestFile` (plan and audit also offline with `-InventoryFile`) |
| [`tests/PurviewCompliance.Tests.ps1`](tests/PurviewCompliance.Tests.ps1) | 60 Pester tests (cmdlets mocked; 1 checks the runner against the real ExchangeOnlineManagement module) |
| [`tests/fixtures/inventory.json`](tests/fixtures/inventory.json) | Fictional, half-deployed tenant: a legacy label, a label rule in a policy with Teams, an overdue simulation, a failed and a Pending retention policy |
| [`tests/fixtures/learn-parameters.json`](tests/fixtures/learn-parameters.json) | Parameter names copied from the Microsoft Learn syntax of each cmdlet — the tests fail if the module uses one that isn't there |
| [`sample/purview-audit.md`](sample/purview-audit.md) | Audit of the fictional inventory, generated offline |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and the shot list for the lab recording |

## Run the tests

```bash
cd series/microsoft-365/episodes/05-microsoft-purview-compliance
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Without ExchangeOnlineManagement installed: Tests Passed: 59, Failed: 0, Skipped: 1
# With it installed:                          Tests Passed: 60, Failed: 0, Skipped: 0
```

Both results were produced in this repo's container (PowerShell 7.6, Pester 6.2.0, ExchangeOnlineManagement 3.11.1
saved to a temp folder on `PSModulePath`). PSScriptAnalyzer 1.25.0 (Warning and Error) reports 0 issues on `src/`.
Security & Compliance cmdlets only exist after `Connect-IPPSSession`, so the tests define stubs **with the documented
parameter names** and mock them; a separate test checks every parameter the module passes against the Learn syntax.

## Run it

```powershell
cd src
# Offline (no tenant): plan and audit against the fictional inventory
./Invoke-PurviewCompliance.ps1 -Plan  -InventoryFile ../tests/fixtures/inventory.json
#   -> 12 steps: 4 Create, 6 Exists, 1 Drift (label policy misses Confidential), 1 Wait (retention policy Pending)
./Invoke-PurviewCompliance.ps1 -Audit -InventoryFile ../tests/fixtures/inventory.json -Now 2026-11-21T10:00:00Z -OutFile ../sample/purview-audit.md
#   -> 13 findings: 2 High / 7 Medium / 1 Low / 3 Info
./Invoke-PurviewCompliance.ps1 -NewTestFile -TestFilePath ./contoso-dlp-test.txt -Count 12

# Needs tenant (Connect-IPPSSession, or pass -UserPrincipalName)
./Invoke-PurviewCompliance.ps1 -PolicyFile ./compliance.lab.json -Plan
./Invoke-PurviewCompliance.ps1 -PolicyFile ./compliance.lab.json -Deploy -WhatIf
./Invoke-PurviewCompliance.ps1 -PolicyFile ./compliance.lab.json -Deploy
./Invoke-PurviewCompliance.ps1 -PolicyFile ./compliance.lab.json -Audit -OutFile ./purview-audit.md -SaveInventory ./inventory.lab.json
./Invoke-PurviewCompliance.ps1 -Promote -PolicyName 'Contoso - Card numbers' -Mode Enable
```

## Licensing (Learn)

| Feature | Needs |
|---|---|
| Manual sensitivity labels, DLP for Exchange / SharePoint / OneDrive | Microsoft 365 / Office 365 E3 and up |
| DLP for Teams chat and channel messages | E5 (or E5 Compliance / E5 Information Protection and Governance) |
| Auto-labeling (client-side and service-side policies) | E5 / P2 tier |
| Retention labels and policies (data lifecycle management) | see the Purview service description |

## What we learned / gotchas

- **`-WhatIf` doesn't work in Security & Compliance PowerShell.** Every cmdlet page we used says so. A dry run has
  to be your own code: `Invoke-PurviewPlan` implements `SupportsShouldProcess` and never passes `-WhatIf` down (a
  test fails if it does).
- **The famous test card number doesn't trigger DLP.** The Credit Card Number type "doesn't flag reserved test card
  numbers". It needs a 14–19 digit number that passes Luhn; **high confidence** also needs a keyword (e.g. `Visa`) or
  an expiry date within 300 characters. `New-DlpTestContent` generates random Luhn-valid numbers next to `Visa`.
- **One location can switch off a condition.** Teams chat and channel messages can't define content by sensitivity
  label, and when a policy has several locations "a 'no' value takes precedence". A label rule in a policy that
  includes Teams can't work — the config refuses it, the audit finds it (`LabelConditionWithTeams`). Teams
  *attachments* are still covered through SharePoint/OneDrive.
- **Rollout is incremental:** simulation → simulation with policy tips for a pilot → turn on. A simulation runs for
  up to 15 days; for Exchange and Teams only items that are new during the simulation are evaluated (SharePoint and
  OneDrive: existing and new). Turned on, a policy takes effect in about an hour. "Stop processing more rules"
  doesn't work in simulation mode.
- **Timing:** labels and label policies — allow 24 hours (Office on the web often within the hour); retention
  labels — about a day in SharePoint/OneDrive, up to 7 days in Exchange (and the mailbox needs at least 10 MB).
- **Pending means wait.** Learn: wait until a retention policy's status is no longer Pending before changing it;
  `DistributionResults` only matters when the status is an error (warnings can be ignored). The plan emits `Wait`.
- **Irreversible settings are opt-in.** A record label can't be removed from content once applied; Preservation Lock
  means no one, including an administrator, can turn the policy off or make it less restrictive. The config refuses
  both unless `allowRecordLabels` / `allowPreservationLock` is set.
- **Retention label publishing = one rule.** `New-RetentionComplianceRule -PublishComplianceTag` takes one label name,
  can't be combined with `-Name` or `-RetentionDuration`, and only one rule fits in a retention policy — so the file
  has one label per retention label policy.
- **Policy tip text:** max 256 characters, no HTML, no tokens (validated). `WithJustification` and
  `WithoutJustification` are mutually exclusive.
- **Labels in Office on the web and DLP on labeled files** need sensitivity labels enabled for SharePoint and OneDrive
  (portal banner, or `Set-SPOTenant -EnableAIPIntegration $true`; about 15 minutes).
- Not verified here (needs tenant, see [demo.md](demo.md)): whether `Get-LabelPolicy` returns label names or GUIDs in
  `Labels`, the exact format of `PublishComplianceTag` on retention rules, the JSON shape of
  `ContentContainsSensitiveInformation` returned by `Get-DlpComplianceRule` (the Teams/label check looks for
  `"type":"Sensitivity"`), and the `WhenChangedUTC` property name used for the 15-day check. The audit reads them
  defensively; adjust after the first lab run.

Not covered (to keep the episode to 6 minutes): auto-labeling policies, encryption in labels, eDiscovery, Audit
(Premium), Insider Risk Management, Communication Compliance.

## References

- [Learn about data loss prevention (lifecycle, about an hour)](https://learn.microsoft.com/purview/dlp-learn-about-dlp) · [Create and deploy DLP policies](https://learn.microsoft.com/purview/dlp-create-deploy-policy) · [DLP simulation mode](https://learn.microsoft.com/purview/dlp-simulation-mode-learn) · [Get started with simulation mode](https://learn.microsoft.com/purview/dlp-simulation-mode-get-started)
- [DLP policy reference (policy scoping, rules)](https://learn.microsoft.com/purview/dlp-policy-reference) · [Use sensitivity labels as conditions in DLP policies](https://learn.microsoft.com/purview/dlp-sensitivity-label-as-condition) · [DLP and Microsoft Teams (licensing)](https://learn.microsoft.com/purview/dlp-microsoft-teams) · [What the DLP policy templates include (PCI DSS)](https://learn.microsoft.com/purview/dlp-policy-templates-include)
- [Credit Card Number entity definition](https://learn.microsoft.com/purview/sit-defn-credit-card-number)
- [New-DlpCompliancePolicy](https://learn.microsoft.com/powershell/module/exchangepowershell/new-dlpcompliancepolicy) · [New-DlpComplianceRule](https://learn.microsoft.com/powershell/module/exchangepowershell/new-dlpcompliancerule) · [Get-DlpComplianceRule](https://learn.microsoft.com/powershell/module/exchangepowershell/get-dlpcompliancerule) · [Get-DlpCompliancePolicy](https://learn.microsoft.com/powershell/module/exchangepowershell/get-dlpcompliancepolicy)
- [New-Label](https://learn.microsoft.com/powershell/module/exchangepowershell/new-label) · [New-LabelPolicy](https://learn.microsoft.com/powershell/module/exchangepowershell/new-labelpolicy) · [Create and configure sensitivity labels (24 hours)](https://learn.microsoft.com/purview/create-sensitivity-labels) · [Enable sensitivity labels for files in SharePoint and OneDrive](https://learn.microsoft.com/purview/sensitivity-labels-sharepoint-onedrive-files)
- [New-ComplianceTag](https://learn.microsoft.com/powershell/module/exchangepowershell/new-compliancetag) · [New-RetentionCompliancePolicy](https://learn.microsoft.com/powershell/module/exchangepowershell/new-retentioncompliancepolicy) · [New-RetentionComplianceRule](https://learn.microsoft.com/powershell/module/exchangepowershell/new-retentioncompliancerule) · [Publish retention labels (up to 7 days)](https://learn.microsoft.com/purview/create-apply-retention-labels) · [Identify errors in retention policies (Pending)](https://learn.microsoft.com/troubleshoot/microsoft-365/purview/retention/identify-errors-in-retention-and-retention-label-policies)
- [Microsoft Purview service description](https://learn.microsoft.com/office365/servicedescriptions/microsoft-365-service-descriptions/microsoft-365-tenantlevel-services-licensing-guidance/microsoft-purview-service-description) · [Automatically apply a sensitivity label (licensing)](https://learn.microsoft.com/purview/apply-sensitivity-label-automatically)
- [Connect-IPPSSession](https://learn.microsoft.com/powershell/module/exchangepowershell/connect-ippssession)
- Blog: [Microsoft Purview Compliance — Complete Guide](https://www.devladlog.com/articles/office-365/2025-04-05-purview-compliance-complete-guide-2025/)
  (note: the current article uses generic placeholder code such as `Set-Configuration` and no Purview cmdlets; this
  folder's code is meant to replace it)
