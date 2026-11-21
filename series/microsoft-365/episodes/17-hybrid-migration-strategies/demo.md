# Demo shot list — DEVLADLOG Microsoft 365 #17: Hybrid Migration Strategies

Everything in `src/` and `tests/` already ran in the build container (69 Pester tests against stubbed AD and Exchange cmdlets; offline reports from fictional fixtures). This file lists what the human-supervised
session must set up and record. Every screen shows real code running against the **real lab domain and the real lab tenant**; `tests/fixtures/*` and `sample/` are for the automated tests only and never appear on screen.
Everything marked **needs lab** has not been run against the lab.

**What is not demoed, and must be said on screen:** a mailbox move. The lab has no on-premises Exchange Server, and a hybrid deployment needs a public domain, certificates and a reachable endpoint. The `New-MigrationBatch` text is printed and labelled "Not run". Microsoft Entra Connect is **not** installed and no sync is started
(it would copy the lab AD accounts into the real tenant).

## Lab environment

No new VM. Nothing is bought. Recorded on the **lab Windows desktop** (PowerShell 7, browser on the lab tenant) and on **CON-SRV02** (Windows Server 2025 Desktop Experience, domain member `lab.contoso.com`, 10.50.0.22; see `series/LAB.md`).

| Item | Notes | Cost / requirement |
|---|---|---|
| CON-DC01 (10.50.0.10) | The shared lab domain controller. Only the new OU `MG Lab Hybrid` is touched: six disabled `hy.*` accounts created and removed by `src/setup/*.ps1` (the remove script refuses anything that is not `hy.*`). Take a Hyper-V checkpoint of CON-DC01 before the setup as an extra safety net | none |
| CON-SRV02 | PowerShell 7.2 or later (**not verified** that it is installed: `winget install Microsoft.PowerShell` or the MSI from the PowerShell releases page), RSAT AD PowerShell (`Install-WindowsFeature RSAT-AD-PowerShell`), `Install-Module Microsoft.Graph.Identity.DirectoryManagement -Scope CurrentUser`. Sign in to the lab Domain Admin; the Graph sign-in is interactive as `labadmin` (scope `Domain.Read.All`, consent once) | none |
| Lab windows desktop | PowerShell 7.2+, `Install-Module ExchangeOnlineManagement -Scope CurrentUser`, `Connect-ExchangeOnline` as `labadmin` (Global Administrator) | none |
| Lab tenant | Microsoft 365 E5 trial (until 20 Dec 2026): every lab user already has a mailbox. Lab users `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo` get a department in Setup; one shared mailbox `mglab-finance` is created | in the lab |

Copy the repo folder `series/microsoft-365/episodes/17-hybrid-migration-strategies/src` to both machines (e.g. `C:\mg\src`). Lab config files (`migration.lab.json`, `rollback.lab.json`, `waves/`) stay outside the repo and are never committed.

## Setup (before recording)

1. **Strategy.** Nothing to set up. Off camera: `./Invoke-HybridMigration.ps1 -Mode Strategy -Source Exchange2010OrLater -Mailboxes 120` works without a connection.
2. **Seed the lab domain (CON-SRV02, needs lab, writes to AD).**
   ```powershell
   cd C:\mg\src\setup
   ./New-LabHybridOu.ps1 -Server 10.50.0.10 -WhatIf     # look first
   ./New-LabHybridOu.ps1 -Server 10.50.0.10
   ```
   Creates `OU=MG Lab Hybrid,DC=lab,DC=contoso,DC=com` with `hy.alex`, `hy.sam`, `hy.jordan` (a space in a proxy address), `hy.riley` and `hy.taylor` (same `mail` and proxy address), `hy.josee` (an accent in the UPN), all disabled, all with the UPN suffix `lab.contoso.com`.
   **Not verified:** that AD accepts the accented UPN and the proxy address with a space (it should: AD does not validate `proxyAddresses`). If one is refused, record that as the lesson and drop that account from the narration.
3. **Config for the lab.** Copy `src/migration.json` to `migration.lab.json` and set `waves.maxMailboxesPerWave` to `3` (the lab mailboxes are small, so the cap is what splits the waves). Leave `directory.upnFix.allowedRules` empty for the first Directory run; for the Fix screens set
   `"allowedRules": ["UpnNonRoutable"]` and `"targetSuffix": "<tenant>.onmicrosoft.com"` (the tenant's initial domain, from the Microsoft 365 admin center > Settings > Domains; Learn says UPNs with a non-routable suffix are synchronized to it).
4. **Register the suffix in AD (needs lab, writes).** CON-SRV02 > Server Manager > Tools > *Active Directory Domains and Trusts* > right-click the root > Properties > *UPN Suffixes* > add `<tenant>.onmicrosoft.com` (Learn: *Prepare a non-routable domain*, step 1). Removed in Tear-down.
5. **Departments, shared mailbox, pilot (needs lab, writes; lab windows desktop, connected to Exchange Online).**
   ```powershell
   $d = '<lab domain>'
   Set-User alex.demo@$d   -Department IT
   Set-User sam.demo@$d    -Department Finance
   Set-User taylor.demo@$d -Department Finance
   Set-User jordan.demo@$d -Department Sales
   Set-User riley.demo@$d  -Department Sales
   New-Mailbox -Shared -Name 'MG Lab Finance' -DisplayName 'MG Lab Finance' -Alias mglab-finance
   Add-MailboxPermission -Identity mglab-finance@$d -User sam.demo@$d -AccessRights FullAccess -InheritanceType All -AutoMapping $false
   ```
   (`Set-User -Department` and the shared mailbox cmdlets are standard; the exact grant syntax is the same as episode 10's SyncSharedMailboxes. **Not verified** in the lab.)
6. **Dry run off camera:** run all three live modes once and read the output. Check in `Waves` that `mglab-finance` lands in the same wave as `sam.demo` (if `Get-EXOMailboxPermission` returns the user as something else than the UPN, the shared mailbox is planned alone: say so and fix the comparison before recording, do not record around it).

## Screens to capture (match `script.yaml` screen scenes)

### 1. `screens/strategy.jpg` — "Same question, three answers" (no lab dependency)
Side by side: PowerShell on the lab desktop and the Microsoft Learn page *Decide on a migration path in Exchange Online* (table visible).
```powershell
./Invoke-HybridMigration.ps1 -Mode Strategy -Source Exchange2010OrLater -Mailboxes 120
./Invoke-HybridMigration.ps1 -Mode Strategy -Source Exchange2010OrLater -Mailboxes 400
./Invoke-HybridMigration.ps1 -Mode Strategy -Source Exchange2007 -Mailboxes 800
```
Expect Cutover, Hybrid, Staged. Capture the reasons and the notes (out of support, 2,000 rows, directory sync). Rewrite the narration if the output differs.

### 2. `screens/directory.jpg` — "The check on a real domain" (needs lab, read-only)
First the Microsoft Entra admin center (or Microsoft 365 admin center) > Domains: show the verified domains (mask the tenant name); `lab.contoso.com` is not in the list. Then on CON-SRV02:
```powershell
./Invoke-HybridMigration.ps1 -Mode Directory -SearchBase 'OU=MG Lab Hybrid,DC=lab,DC=contoso,DC=com' -Server 10.50.0.10 -LiveDomains -OutFile ./directory.lab.md
```
Capture the findings table (six `UpnNonRoutable`, `ProxyInvalidChars`, `UpnInvalidChars`, `MailDuplicate` and `ProxyDuplicate` on riley and taylor, `UpnMailMismatch`) and the last line `Ready for directory synchronization: False`. The `-LiveDomains` run signs in to Microsoft Graph interactively (browser). If that is awkward on CON-SRV02, pass `-VerifiedDomain` with the values read from the admin center instead, and say so.
Rewrite the narration to the real counts. Also run it once on the whole domain (`-SearchBase` omitted) only if you want to show the built-in lab accounts: they are flagged too, which is true, but it reads more than the OU and is not needed.

### 3. `screens/fix.jpg` — "Preview, change, restore" (needs lab, **writes to AD**)
1. `./Invoke-HybridMigration.ps1 -Mode FixUpn -SearchBase 'OU=MG Lab Hybrid,DC=lab,DC=contoso,DC=com' -Server 10.50.0.10 -LiveDomains -ConfigFile ./migration.lab.json -RollbackFile ./rollback.lab.json -WhatIf`: plan table (five changes, `hy.josee` skipped because the new UPN would be invalid), "What if" lines, `Test-Path ./rollback.lab.json` is `False`.
2. Same without `-WhatIf`: confirm per account; answer **Yes only for `hy.alex`** and No for the rest. Expected one `Changed` row.
3. Active Directory Users and Computers > `MG Lab Hybrid` > `hy.alex` > Account tab: the suffix is now the tenant's initial domain. Show `rollback.lab.json`. Re-run Directory: `UpnNonRoutable` is gone for that account.
4. `./Invoke-HybridMigration.ps1 -Mode RestoreUpn -RollbackFile ./rollback.lab.json -Server 10.50.0.10`: `Restored`; the Account tab shows `lab.contoso.com` again.
Never run the fix with a `-SearchBase` other than the lab OU. Rewrite the narration to the real account.

### 4. `screens/waves.jpg` — "Waves from real mailboxes" (needs lab, read-only; writes files)
```powershell
Connect-ExchangeOnline -ShowBanner:$false
./Invoke-HybridMigration.ps1 -Mode Waves -FromExchangeOnline -PilotUsers alex.demo@<lab domain> -ConfigFile ./migration.lab.json -WaveDirectory ./waves -OutFile ./waves.lab.md
Import-Csv ./waves/wave-01.csv
```
Capture: the wave table (wave-01 Pilot with `alex.demo` alone; `mglab-finance` and `sam.demo` in the same wave; no `Large` wave unless a lab mailbox is at or above 40 GB, which it will not be: say so), one CSV with the three columns, and the printed `New-MigrationBatch` text with the line
"Not run: needs an on-premises Exchange endpoint". Then Exchange admin center > Migration: the page lists no batches and no endpoints (real, empty). Mask the tenant domain in every address, and `<tenant>.mail.onmicrosoft.com` stays as the placeholder it is in the config.

## Masking checklist
- Tenant name and domain, `labadmin` UPN, user addresses beyond the lab aliases, the initial `onmicrosoft.com` domain, the Entra domains page.
- `migration.lab.json`, `rollback.lab.json`, `directory.lab.md`, `waves.lab.md` and `waves/*.csv` contain tenant data: don't show them in full, never commit them.
- The lab domain `lab.contoso.com` and the IP addresses are fictional lab values and may be shown.

## Tear-down
1. Restore anything left changed: `./Invoke-HybridMigration.ps1 -Mode RestoreUpn -RollbackFile ./rollback.lab.json -Server 10.50.0.10` (or just delete the OU, next step).
2. CON-SRV02: `./setup/Remove-LabHybridOu.ps1 -Server 10.50.0.10` (confirm). Check in Active Directory Users and Computers that `MG Lab Hybrid` is gone. If CON-DC01 got a checkpoint, delete it.
3. Active Directory Domains and Trusts > Properties > UPN Suffixes: remove `<tenant>.onmicrosoft.com`.
4. Exchange Online: `Remove-Mailbox -Identity mglab-finance@<lab domain> -Confirm:$false`; clear the departments (`Set-User <upn> -Department $null` for the five lab users, only if they were empty before: note their values in Setup step 5 first).
5. Delete `migration.lab.json`, `rollback.lab.json`, `directory.lab.md`, `waves.lab.md`, `waves/`; `Disconnect-ExchangeOnline -Confirm:$false`; `Disconnect-MgGraph`.
