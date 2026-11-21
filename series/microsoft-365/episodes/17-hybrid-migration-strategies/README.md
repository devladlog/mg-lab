# DEVLADLOG Microsoft 365 #17 — Hybrid Migration Strategies

**Pick the migration path, check Active Directory before directory synchronization, fix the first problem with a rollback file, and plan migration waves that never split mailboxes that belong together.**
One config file ([`src/migration.json`](src/migration.json)) and one module. Everything that decides something is a pure function, so it is tested without a tenant; only the
reading of Active Directory and Exchange Online and the guarded UPN fix touch a real service.

1. **Strategy** — `Get-HMStrategy`: Microsoft Learn's decision table as a function (source system, number of mailboxes, all at once or gradual, users managed on-premises) -> `Cutover`, `Staged`, `Hybrid` or `IMAP`, with the reasons and the warnings Learn gives.
2. **Directory check** — `Get-HMDirectoryInventory` (read-only `Get-ADUser`) and `Get-HMDirectoryFinding`: the attribute rules of *Prepare for directory synchronization to Microsoft 365*:
   `UpnNonRoutable` (suffix not verified in the tenant), `UpnInvalidChars` (space, the listed characters, diacritics), `UpnFormat`, `UpnTooLong` (64 before and 48 after the @), `UpnDuplicate`, `MailDuplicate`, `ProxyDuplicate`,
   `ProxyInvalidChars`, `ProxyTooLong`, `SamTooLong`, `SamInvalidChars`, `DisplayNameMissing`, `MailNicknameLeadingDot`, `TargetAddressInvalid`, `UpnMailMismatch`, `MultiplePrimarySmtp`. "Ready for synchronization" means no High finding.
3. **UPN fix** — `Get-HMUpnFixPlan`, `Invoke-HMUpnFix`, `Restore-HMUpn`: only `UpnNonRoutable`, only if `directory.upnFix.allowedRules` lists it (empty by default), only to a verified suffix, never a duplicate or invalid result;
   `-WhatIf`, `ConfirmImpact = High`, re-read before each change, rollback file written after each success and never overwritten; restore refuses an account somebody changed since.
4. **Waves** — `Get-HMMailboxInventory` (read-only, Exchange Online), `New-HMWavePlan`, `Export-HMWaveCsv`, `Get-HMBatchCommand`: pilot first, then departments within the count and size caps, groups tied by `MoveWith` (a shared mailbox moves with the user who has Full Access) never split,
   groups with a mailbox at or above `largeMailboxGB` in a wave of their own at the end. One CSV per wave with `EmailAddress, BadItemLimit, LargeItemLimit`, plus the `New-MigrationBatch` / `Start-MigrationBatch` text. **The text is printed, never run.**

Same fictional tenant as episodes 1–16 (`contoso`); lab users `labadmin`, `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo`. The names in the tests never appear in the demo.

**What this episode does not do:** it does not install Microsoft Entra Connect or start a synchronization (that would create the lab's AD users in the real tenant), it does not run the Hybrid Configuration wizard, and it does not move a mailbox:
the lab has no on-premises Exchange Server, and a hybrid deployment needs a public domain, certificates and a reachable endpoint. The plan, the files and the directory fixes are tested; the remote move itself is **not demoed** and the script says so.

| Path | What it is |
|---|---|
| [`src/migration.json`](src/migration.json) | Ignored accounts, UPN-fix allow list (empty) and target suffix, wave caps, batch endpoint and delivery domain (placeholders) |
| [`src/HybridMigration/HybridMigration.psm1`](src/HybridMigration/HybridMigration.psm1) · [`.psd1`](src/HybridMigration/HybridMigration.psd1) | The module |
| [`src/Invoke-HybridMigration.ps1`](src/Invoke-HybridMigration.ps1) | Runner: `-Mode Strategy`, `Directory`, `Waves`, `FixUpn`, `RestoreUpn` |
| [`src/setup/New-LabHybridOu.ps1`](src/setup/New-LabHybridOu.ps1) · [`Remove-LabHybridOu.ps1`](src/setup/Remove-LabHybridOu.ps1) | Seeds six disabled fictional accounts with the problems in one OU of the lab domain, and removes it again (refuses anything that is not `hy.*`) |
| [`tests/HybridMigration.Tests.ps1`](tests/HybridMigration.Tests.ps1) | 69 Pester tests (stubbed AD and Exchange cmdlets, mocked per test) |
| [`tests/fixtures/`](tests/fixtures) | Fictional users, mailboxes and a test config |
| [`sample/`](sample) | Reports for the fixtures, generated offline: `directory-check.md`, `waves.md`, `strategy.md` |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and shot list (no new VM, nothing bought) |

## Run the tests

```bash
cd series/microsoft-365/episodes/17-hybrid-migration-strategies
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Tests Passed: 69, Failed: 0, Skipped: 0   (PowerShell 7.6, Pester 6.2.0, about 40 s)
```

The "What if:" lines printed during the run come from the `-WhatIf` tests. PSScriptAnalyzer is not installed in the build container, so it was **not run**; the three scripts were checked with the PowerShell parser (0 errors) and every `-Mode` that works offline was run on the fixtures.

## Run it

```powershell
cd src
# Offline (no tenant, no domain): the fixtures
./Invoke-HybridMigration.ps1 -Mode Strategy  -Source Exchange2010OrLater -Mailboxes 400
./Invoke-HybridMigration.ps1 -Mode Directory -UsersFile ../tests/fixtures/users.json -VerifiedDomain contoso.com,contoso.onmicrosoft.com -ConfigFile ../tests/fixtures/migration.test.json -OutFile ../sample/directory-check.md
#   -> Users checked: 14. Findings: 17 (13 high). Ready for directory synchronization: False.
./Invoke-HybridMigration.ps1 -Mode Waves     -MailboxesFile ../tests/fixtures/mailboxes.json -ConfigFile ../tests/fixtures/migration.test.json -WaveDirectory ./waves -OutFile ../sample/waves.md

# Needs the lab (see demo.md)
./Invoke-HybridMigration.ps1 -Mode Directory -SearchBase 'OU=MG Lab Hybrid,DC=lab,DC=contoso,DC=com' -Server 10.50.0.10 -LiveDomains
./Invoke-HybridMigration.ps1 -Mode FixUpn    -SearchBase 'OU=MG Lab Hybrid,DC=lab,DC=contoso,DC=com' -Server 10.50.0.10 -LiveDomains -ConfigFile ./migration.lab.json -RollbackFile ./rollback.lab.json -WhatIf
./Invoke-HybridMigration.ps1 -Mode Waves     -FromExchangeOnline -PilotUsers alex.demo@<lab domain> -ConfigFile ./migration.lab.json
```

## What we learned / gotchas

- **Learn's own numbers disagree on cutover.** The mailbox-migration overview and the cutover articles say a cutover moves fewer than 2,000 mailboxes (and recommend 150 or fewer), while the `New-MigrationBatch` reference says a maximum of 1,000 Exchange 2003, 2007 or 2010 mailboxes.
  The tool therefore recommends cutover only under 150 mailboxes, and only warns about the 2,000 figure; it never relies on the larger number.
- **Staged migration is not for Exchange 2010 or later.** Learn: staged supports only Exchange 2003 and 2007 (both out of support: April 2014 and April 2017). A CSV for a staged batch holds at most 2,000 rows. Staged and hybrid both need directory synchronization first. A cutover batch does not take a CSV at all.
- **A non-routable UPN does not fail, it silently becomes something else.** Learn: a UPN with a non-routable domain (`.local`) is synchronized to the `onmicrosoft.com` domain. That is why `UpnNonRoutable` is High but the fix is a *plan*, not a surprise. Learn's fix is to register an alternative UPN suffix
  (Active Directory Domains and Trusts) and update the users; the Learn sample also uses `Get-ADUser` / `Set-ADUser`. The lab domain `lab.contoso.com` is itself a suffix that is not verified in the tenant, so every real lab account is flagged: that is a true finding, not a seeded one.
- **Invisible damage:** per Learn, a space in `proxyAddresses` makes the value be discarded and an address be generated from the alias at the initial domain; invalid characters in `userPrincipalName` can turn it into `<alias>@<initial domain>`. Check the raw value, not what the GUI shows.
- **Limits used (Learn, *Prepare for directory synchronization*):** UPN at most 113 characters, 64 before the `@` and 48 after; proxyAddresses values at most 256 characters, no space, none of `< > ( ) ; , [ ] "`, no diacritics; sAMAccountName at most 20 characters; displayName at most 256; givenName at most 64; mailNickname cannot start with a period.
  The 113 total can never fail on its own (64 + 1 + 48 = 113), so `UpnTooLong` fires on the 64 and 48 limits first; the test says so.
- **What AD refuses on its own:** a duplicate `userPrincipalName` and a sAMAccountName over 20 characters cannot be created in AD (the demo does not seed them; the unit tests do, from a file). Duplicate `mail` and `proxyAddresses` *can* be created, so those are seeded.
- **Onboarding items:** Learn says items up to 35 MB are migrated when onboarding to Exchange Online; the default `BadItemLimit` and `LargeItemLimit` are 0, and Learn recommends keeping `BadItemLimit` at 0 and raising it only for a mailbox whose move failed. The wave CSV writes both columns from `migration.json` (0 by default).
- **Why `MoveWith`:** nothing in Learn defines a rule for "shared mailboxes move with their users" that we could cite, so this is a design choice of this episode (people who use a shared mailbox lose or keep access in a way they notice when it moves at a different time), not a Microsoft requirement.
  The same goes for the wave caps and for putting large mailboxes last: they are config values you set, not Learn numbers, and the shipped values (50 mailboxes, 200 GB, 40 GB) are only placeholders.
- Pitfalls hit while building: under `Set-StrictMode`, `(… | Select-Object -First 1).Department` on an empty result throws instead of returning `$null`, so optional properties (`Department`, `Pilot`, `MoveWith`) are read through a helper; `$WhatIfPreference` does not flow into a module function, so the runner passes `-WhatIf:$WhatIfPreference` explicitly.
- **Not verified** (needs the lab, see [demo.md](demo.md)): the format of `TotalItemSize` from `Get-EXOMailboxStatistics` in the lab (the parser needs the `(n bytes)` text and throws otherwise); whether `Get-EXOMailboxPermission` returns `User` as a UPN or as `DOMAIN\user` (a Full Access user that is not matched by UPN gives no `MoveWith`, so the shared mailbox would be planned alone: look at the output);
  that `Get-ADUser` from PowerShell 7 on Windows Server 2025 returns `proxyAddresses` as expected; that AD accepts the accented UPN used in the seed script; that `Get-MgDomain` needs only `Domain.Read.All`; and that `Set-ADUser -UserPrincipalName` accepts a suffix that is not registered in the forest (the demo registers it first, as Learn does).
  `New-MigrationBatch` / `Start-MigrationBatch` / `New-MigrationEndpoint -ExchangeRemoteMove` are taken from Learn's example 3 and were never run.

Not covered (to keep the episode to 6 minutes): the Hybrid Configuration wizard and hybrid mail flow, Exchange hybrid decommissioning, Entra Connect installation and sync scoping, Exchange Online Migration endpoints for IMAP, SharePoint and OneDrive migration (episodes 11, 12 and the PnP episode of MG Lab), public folders, PST import, Google Workspace migration, throttling and migration performance.

## References

- [Decide on a migration path in Exchange Online](https://learn.microsoft.com/exchange/mailbox-migration/decide-on-a-migration-path) · [Ways to migrate multiple email accounts](https://learn.microsoft.com/exchange/mailbox-migration/mailbox-migration) · [How and when to decommission on-premises Exchange in a hybrid deployment (migration-type table)](https://learn.microsoft.com/exchange/decommission-on-premises-exchange#other-methods-to-migrate-to-exchange-online)
- [What you need to know about a cutover email migration](https://learn.microsoft.com/exchange/mailbox-migration/what-to-know-about-a-cutover-migration) · [Cutover migration](https://learn.microsoft.com/exchange/mailbox-migration/cutover-migration-to-office-365) · [What you need to know about a staged email migration](https://learn.microsoft.com/exchange/mailbox-migration/what-to-know-about-a-staged-migration) · [Perform a staged migration](https://learn.microsoft.com/exchange/mailbox-migration/perform-a-staged-migration/perform-a-staged-migration)
- [CSV files for mailbox migration](https://learn.microsoft.com/exchange/mailbox-migration/csv-files-for-migration) · [New-MigrationBatch](https://learn.microsoft.com/powershell/module/exchangepowershell/new-migrationbatch) · [Move mailboxes between on-premises and Exchange Online (hybrid)](https://learn.microsoft.com/exchange/hybrid-deployment/move-mailboxes)
- [Prepare for directory synchronization to Microsoft 365](https://learn.microsoft.com/microsoft-365/enterprise/prepare-for-directory-synchronization) · [Prepare a non-routable domain for directory synchronization](https://learn.microsoft.com/microsoft-365/enterprise/prepare-a-non-routable-domain-for-directory-synchronization) · [Synchronize domain users to Microsoft 365 (IdFix)](https://learn.microsoft.com/microsoft-365/admin/setup/manage-domain-users)
- [Understanding errors during Microsoft Entra synchronization](https://learn.microsoft.com/entra/identity/hybrid/connect/tshoot-connect-sync-errors) · [One or more objects don't sync](https://learn.microsoft.com/troubleshoot/entra/entra-id/user-prov-sync/objects-dont-sync-ad-sync-tool) · [End-to-end troubleshooting of Entra Connect objects and attributes](https://learn.microsoft.com/troubleshoot/entra/entra-id/user-prov-sync/troubleshoot-aad-connect-objects-attributes)
- Blog: [Hybrid Migration — Complete Guide](https://www.devladlog.com/articles/office-365/2025-08-11-hybrid-migration-complete-guide-2025/). Note from reading it while planning: despite the title it contains no migration strategies (no cutover, staged, hybrid or IMAP), no limits and no migration cmdlets; its scripts call placeholder cmdlets (`Set-Configuration`, `Get-DeploymentStatus`) and its "expected output" does not match what its setup script prints.
  Everything above follows Learn, not the post. The post should be rewritten around this episode.
