# DEVLADLOG Microsoft 365 #6 — Microsoft Defender for Office 365

**Defender for Office 365 as code.** One file ([`src/defender.json`](src/defender.json)) says who gets Microsoft's
preset security policies; the module applies it, proves who is really protected, and reads the two signals that show
whether protection works — threats in email, and people in a phishing simulation:

1. **Presets** — `Set-DefenderPresetPolicy`: Strict for the *Priority Accounts* group, Standard for the whole domain,
   on both rules of each preset (the built-in protection features = `EOPProtectionPolicyRule`, Defender for Office 365
   = `ATPProtectionPolicyRule`), every recipient parameter sent (unused ones as `$null`, so old conditions don't
   linger), then turned on. Checks all four rules exist first: they are only created the first time a preset is
   turned on in the Defender portal.
2. **Coverage** — `Test-DORecipientInScope` / `Get-DOProtectionCoverage`: the preset each mailbox actually gets, using
   Microsoft's documented logic (values of one condition: OR; different condition types: **AND**; any exception
   excludes; Strict before Standard; Built-in protection for Safe Links/Safe Attachments otherwise).
3. **Audit** — `Get-DefenderInventory` + `Get-DefenderFinding`: missing/disabled preset rules, combined conditions
   (naming who falls through), priority accounts not on Strict, mailboxes left on defaults, Built-in protection
   exceptions, drift from the file, and every row of **Microsoft's configuration analyzer**
   (`Get-ConfigAnalyzerPolicyRecommendation -RecommendedPolicyType Standard`) — we don't re-implement its tables.
4. **Hunting** — `New-DOHuntingQuery` + `Invoke-DOHuntingQuery`: KQL on `EmailEvents` through Microsoft Graph
   `POST /security/runHuntingQuery`; the queries are compiled in the tests with Microsoft's **Kusto.Language** parser
   against the EmailEvents columns, so a wrong column name fails before it ever runs.
5. **Attack simulation** — `Get-DOAttackSimulationReport` + `Get-DOSimulationSummary`: the latest (or a given)
   simulation and its users via Graph; compromise and report rates, training progress, findings above a target rate.

Same fictional tenant as episodes 1–5 (`contoso`); the lab users are `labadmin`, `alex.demo`, `sam.demo`,
`jordan.demo`, `riley.demo`, `taylor.demo`. The demo uses only Microsoft's documented test methods: the **EICAR** file
sent internally, and **Attack simulation training** with a Microsoft payload against lab users.

| Path | What it is |
|---|---|
| [`src/defender.json`](src/defender.json) | Strict = Priority Accounts group, Standard = accepted domain (one condition type each), no Built-in protection exceptions, 7-day hunting window, 20% compromise target |
| [`src/DefenderForOffice/DefenderForOffice.psm1`](src/DefenderForOffice/DefenderForOffice.psm1) | The module: config validation, preset parameters, scope logic and coverage, findings, KQL, simulation summary + the functions that call Exchange Online and Graph |
| [`src/DefenderForOffice/DefenderForOffice.psd1`](src/DefenderForOffice/DefenderForOffice.psd1) | Module manifest |
| [`src/Invoke-DefenderForOffice.ps1`](src/Invoke-DefenderForOffice.ps1) | Runner: `-Audit` (live or `-InventoryFile`), `-ApplyPresets [-WhatIf]`, `-Hunt [-Recipient] [-ShowQuery]`, `-SimulationReport` (live or `-ReportFile`) |
| [`tests/DefenderForOffice.Tests.ps1`](tests/DefenderForOffice.Tests.ps1) | 48 Pester tests (Exchange Online and Graph mocked; 3 compile the KQL with Kusto.Language; 2 check our calls against the real ExchangeOnlineManagement and Microsoft.Graph.Authentication modules) |
| [`tests/kql/`](tests/kql/) | `KqlCheck`: .NET 10 console using `Microsoft.Azure.Kusto.Language` 12.4.1 with the EmailEvents schema from Learn |
| [`tests/fixtures/`](tests/fixtures/) | Fictional inventory (the AND trap, a disabled Strict rule, a Built-in protection exception, 2 analyzer rows), a simulation report, a runHuntingQuery response |
| [`sample/defender-audit.md`](sample/defender-audit.md) | Coverage + audit of the fictional inventory, generated offline |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and the shot list for the lab recording |

## Run the tests

```bash
cd series/microsoft-365/episodes/06-microsoft-defender-for-365
dotnet build -c Release -m:1 tests/kql          # once: enables the 3 KQL tests (restores Kusto.Language from NuGet)
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Without the KQL checker and without the two modules: Tests Passed: 43, Failed: 0, Skipped: 5
# With the KQL checker built:                           Tests Passed: 46, Failed: 0, Skipped: 2
# With the KQL checker and both modules installed:      Tests Passed: 48, Failed: 0, Skipped: 0
```

All three results were produced in this repo's container (PowerShell 7.6, Pester 6.2.0, .NET 10 SDK,
ExchangeOnlineManagement 3.11.1 and Microsoft.Graph.Authentication 2.41.2 saved to a temp folder on `PSModulePath`).
PSScriptAnalyzer 1.25.0 (Warning and Error) reports 0 issues on `src/`. `tests/kql/bin` and `obj` were deleted after
the run (rebuild with the command above).

## Run it

```powershell
cd src
# Offline (no tenant)
./Invoke-DefenderForOffice.ps1 -Audit -InventoryFile ../tests/fixtures/inventory.json -OutFile ../sample/defender-audit.md
#   -> coverage table + 13 findings: 4 High / 7 Medium / 2 Low
./Invoke-DefenderForOffice.ps1 -Hunt -ShowQuery
./Invoke-DefenderForOffice.ps1 -SimulationReport -ReportFile ../tests/fixtures/simulation-report.json
#   -> 4 targeted, 2 compromised (50%), 1 reported (25%); CompromiseRateHigh + CompromisedNoTraining

# Needs tenant
./Invoke-DefenderForOffice.ps1 -PolicyFile ./defender.lab.json -Audit -SaveInventory ./inventory.lab.json   # Exchange Online
./Invoke-DefenderForOffice.ps1 -PolicyFile ./defender.lab.json -ApplyPresets -WhatIf
./Invoke-DefenderForOffice.ps1 -PolicyFile ./defender.lab.json -ApplyPresets
./Invoke-DefenderForOffice.ps1 -Hunt -Recipient sam.demo@<lab domain> -Days 1                               # Graph: ThreatHunting.Read.All
./Invoke-DefenderForOffice.ps1 -SimulationReport                                                            # Graph: AttackSimulation.Read.All
```

## Licensing and permissions (Learn)

| Feature | Needs |
|---|---|
| Built-in protection features (anti-malware, anti-spam, anti-phishing) and the EOP half of the presets | every organization with cloud mailboxes |
| Safe Links, Safe Attachments, the Defender half of the presets, Built-in protection preset | Microsoft 365 E5 or a Defender for Office 365 add-on |
| Attack simulation training | Microsoft 365 E5 or Defender for Office 365 Plan 2; roles: Security Administrator / Attack Simulation Administrator (Security Reader can view) |
| `POST /security/runHuntingQuery` | `ThreatHunting.Read.All` (delegated or application) |
| `GET /security/attackSimulation/simulations`, `…/report/simulationUsers` | `AttackSimulation.Read.All` |

## What we learned / gotchas

- **Users AND groups = fewer people.** Learn: multiple values of the same condition use OR, but **different types of
  conditions use AND** — "Users: romain@contoso.com, Groups: Executives" applies to Romain *only if* he's also in
  Executives. Exceptions are OR. Adding a group "for good measure" next to the domain silently drops everyone outside
  the group. The config refuses combined types unless `allowCombinedConditions`, and the audit names who falls through.
- **The preset rules don't exist until you turn the preset on in the portal.** "If you never turned on the preset
  security policy, the associated rules don't exist. Turning off the preset security policy doesn't delete the
  associated rules." PowerShell can only set recipients and enable/disable — `Set-DefenderPresetPolicy` checks all
  four rules before changing any. And don't edit the individual threat policies behind a preset (Learn: unsupported).
- **Precedence:** Strict → Standard → Defender for Office 365 evaluation policies → custom policies (by priority) →
  Built-in protection / default policies. A disabled Strict Defender rule quietly drops priority accounts to Standard
  for Safe Links and Safe Attachments (`PriorityNotStrict`).
- **Built-in protection is basic on purpose:** its Safe Links lets users click through and doesn't rewrite URLs, and
  doesn't apply to internal mail. Exceptions are "typically only useful" for users without Defender licences.
- **Defaults differ between portal and PowerShell:** in custom Safe Links policies, *Let users click through to the
  original URL* and *Do not rewrite URLs* are selected by default when created in the portal, `$false` when created in
  PowerShell; Safe Attachments custom default is `-Enable $false`. That's why the audit relies on Microsoft's
  configuration analyzer rather than assumptions.
- **runHuntingQuery** looks back 30 days by default; if the query and `Timespan` both filter time, the shorter wins. We
  pass `P{n}D` and keep `ago()` in the query. Learn's second example returns lowercase column keys —
  `ConvertFrom-DOHuntingResult` matches the schema names case-insensitively.
- **KQL fails at run time, so check it at build time:** `tests/kql` binds the queries to the EmailEvents schema with
  Microsoft's parser (`EmailEvents | where Verdict == "Phish"` → `KS142 … does not refer to any known column`).
- **EICAR:** Learn says to exclude `EICAR.TXT` from the local antivirus, or it's quarantined before you can attach it.
  We test internal → internal only.
- Not verified here (needs tenant, see [demo.md](demo.md)): the exact property names/value types of
  `Get-EOPProtectionPolicyRule` output (`State`, recipient lists), whether `SentToMemberOf` returns group addresses or
  display names, how long an EICAR message takes to appear in `EmailEvents`, and the threat type string it gets.
  Microsoft 365 Groups used as preset conditions would need `Get-UnifiedGroupLinks` instead of
  `Get-DistributionGroupMember` (the module expects mail-enabled security or distribution groups).

Not covered (to keep the episode to 6 minutes): impersonation protection entries, tenant allow/block list, quarantine
policies, Threat Explorer, automated investigation and response, priority account tagging.

## References

- [Preset security policies (PowerShell rules, precedence, AND/OR, Built-in protection)](https://learn.microsoft.com/defender-office-365/preset-security-policies)
- [Recommended settings for EOP and Defender for Office 365 (Standard/Strict tables)](https://learn.microsoft.com/defender-office-365/recommended-settings-for-eop-and-office365) · [Get-ConfigAnalyzerPolicyRecommendation](https://learn.microsoft.com/powershell/module/exchangepowershell/get-configanalyzerpolicyrecommendation)
- [Safe Links (recipient filters)](https://learn.microsoft.com/defender-office-365/safe-links-about) · [Set up Safe Attachments policies](https://learn.microsoft.com/defender-office-365/safe-attachments-policies-configure)
- [Configure anti-malware policies (EICAR test)](https://learn.microsoft.com/defender-office-365/anti-malware-policies-configure)
- [runHuntingQuery (Graph v1.0)](https://learn.microsoft.com/graph/api/security-security-runhuntingquery?view=graph-rest-1.0) · [EmailEvents table](https://learn.microsoft.com/defender-xdr/advanced-hunting-emailevents-table)
- [Get started using Attack simulation training (licensing, roles)](https://learn.microsoft.com/defender-office-365/attack-simulation-training-get-started) · [Simulate a phishing attack](https://learn.microsoft.com/defender-office-365/attack-simulation-training-simulations) · [List simulations](https://learn.microsoft.com/graph/api/attacksimulationroot-list-simulations?view=graph-rest-1.0) · [List simulationUsers](https://learn.microsoft.com/graph/api/usersimulationdetails-list?view=graph-rest-1.0) · [userSimulationDetails](https://learn.microsoft.com/graph/api/resources/usersimulationdetails?view=graph-rest-1.0) · [attackSimulationUser](https://learn.microsoft.com/graph/api/resources/attacksimulationuser?view=graph-rest-1.0)
- [Microsoft Defender for Office 365 service description](https://learn.microsoft.com/office365/servicedescriptions/microsoft-defender-for-office-365-features)
- Blog: [Microsoft Defender for 365 — Complete Guide](https://www.devladlog.com/articles/office-365/2026-05-02-defender-365-security-complete-guide-2026/)
  (note: the current article uses generic placeholder code such as `Set-Configuration` and no Defender cmdlets, and
  "Defender for 365" isn't an official product name — Microsoft Defender for Office 365 is; this folder's code is
  meant to replace it)
