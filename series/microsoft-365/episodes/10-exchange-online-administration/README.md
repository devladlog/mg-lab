# DEVLADLOG Microsoft 365 #10 — Exchange Online Administration

**Find where mail leaves the organization, fix the worst case safely, build shared mailboxes from a file, and trace a message.** One config file
([`src/exchange.json`](src/exchange.json)) and one module read the tenant through Exchange Online PowerShell (the EXO V3 module). The audit is read-only;
the only writes are *removing mailbox-level external forwarding* (off until you name the rule, with a rollback file) and *creating the shared mailboxes you declared*.

1. **Audit** — `Get-EAInventory` (mailboxes, statistics, shared-mailbox permissions, Inbox rules, mail flow rules, outbound spam policies, accepted domains, sign-in state of the
   account behind each mailbox) and `Get-EAFinding`: `MailboxForwardingExternal`, `MailboxForwardingRecipient`, `InboxRuleForwardingExternal`, `TransportRuleExternalCopy`
   (live = High, disabled or test mode = Medium), `TransportRuleNoComment`, `OutboundAutoForwarding` (`On` = High, `Automatic` = Medium), `SharedMailboxSignInEnabled`,
   `SharedMailboxNearLimit` / `SharedMailboxOverLimit` (the 50 GB unlicensed limit), `SharedMailboxNoDelegates`, `FullAccessSprawl`, `MailboxNearQuota`, and `CollectionError`
   (an item that could not be read, so a half-finished audit is visible). "Outside" means: not an accepted domain of type Authoritative or InternalRelay, and not in `forwarding.allowedExternalDomains`.
2. **Fix** — `Get-EAFixPlan`, `Invoke-EAForwardingFix`, `Restore-EAForwarding`: only `MailboxForwardingExternal`, only if `fix.allowedRules` lists it (empty by default = nothing),
   never a mailbox in `forwarding.ignoreMailboxes`. `Set-Mailbox -ForwardingSmtpAddress $null`, `-WhatIf`, `ConfirmImpact = High`, re-read before each change, rollback file written after each success and never overwritten.
3. **Shared mailboxes** — `Get-EASharedMailboxPlan`, `Invoke-EASharedMailboxPlan`: a desired-state file (alias, display name, Full Access and Send As delegates) is compared with the tenant and
   only the difference is applied (`New-Mailbox -Shared`, `Add-MailboxPermission`, `Add-RecipientPermission`). A second run changes nothing. Existing user mailboxes are never converted. `-RemoveExtra` also removes delegates that are not declared.
4. **Message trace** — `Get-EAMessageTrace` wraps `Get-MessageTraceV2` and refuses a window over 10 days or older than 90 days before calling the service; it warns when the result hits your limit (the cmdlet has no paging).

Same fictional tenant as episodes 1–9 (`contoso`); lab users `labadmin`, `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo`. The data in the tests (nine fictional mailboxes, `example.com` addresses) never appears in the demo.

| Path | What it is |
|---|---|
| [`src/exchange.json`](src/exchange.json) | Allowed external domains, ignored mailboxes, shared mailbox and quota limits, trace limits, retry settings, `fix.allowedRules` (empty) |
| [`src/shared-mailboxes.json`](src/shared-mailboxes.json) | The desired shared mailboxes (empty by default) |
| [`src/ExchangeAdmin/ExchangeAdmin.psm1`](src/ExchangeAdmin/ExchangeAdmin.psm1) · [`.psd1`](src/ExchangeAdmin/ExchangeAdmin.psd1) | The module: collection, pure analysis, fix and restore, shared-mailbox plan, trace, markdown report |
| [`src/Invoke-ExchangeAdmin.ps1`](src/Invoke-ExchangeAdmin.ps1) | Runner: `-Mode Audit` (live or `-Snapshot`), `Fix`, `Restore`, `SyncSharedMailboxes`, `Trace` |
| [`tests/ExchangeAdmin.Tests.ps1`](tests/ExchangeAdmin.Tests.ps1) | 65 Pester tests against a fake Exchange tenant (the cmdlets are stubbed and mocked; every write is recorded) |
| [`tests/fixtures/`](tests/fixtures) | Fictional inventory, desired-state file and a test config |
| [`sample/exchange-audit.md`](sample/exchange-audit.md) | Report for the fictional inventory, generated offline |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and shot list (no new VM, nothing bought) |

## Run the tests

```bash
cd series/microsoft-365/episodes/10-exchange-online-administration
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Without the ExchangeOnlineManagement module:   Tests Passed: 64, Failed: 0, Skipped: 1
# With ExchangeOnlineManagement 3.11.1 on PSModulePath (adds the "real modules" test):   Tests Passed: 65, Failed: 0, Skipped: 0
```

Both results were produced in this repo's container (PowerShell 7.6, Pester 6.2.0; the module saved to a temp folder on `PSModulePath`), about 1 to 2 minutes per run. PSScriptAnalyzer (Warning and Error)
reports 0 issues on `src/`. The "What if:" lines printed during the run come from the `-WhatIf` tests.

## Run it

```powershell
cd src
# Offline (no tenant): analyse the fictional inventory
./Invoke-ExchangeAdmin.ps1 -Snapshot ../tests/fixtures/inventory.json -ConfigFile ../tests/fixtures/exchange.test.json -OutFile ../sample/exchange-audit.md
#   -> Findings: 18 (6 high, 4 medium, 7 low, 1 info). Fixable here: 2. Fix plan: 2 removal(s).

# Needs tenant (see demo.md): connects with Connect-ExchangeOnline if there is no session
./Invoke-ExchangeAdmin.ps1 -OutFile ./audit.lab.md                      # read-only
./Invoke-ExchangeAdmin.ps1 -Mode Fix -ConfigFile ./exchange.lab.json -RollbackFile ./rollback.lab.json -WhatIf
./Invoke-ExchangeAdmin.ps1 -Mode Fix -ConfigFile ./exchange.lab.json -RollbackFile ./rollback.lab.json
./Invoke-ExchangeAdmin.ps1 -Mode Restore -RollbackFile ./rollback.lab.json
./Invoke-ExchangeAdmin.ps1 -Mode SyncSharedMailboxes -DesiredFile ./shared-mailboxes.lab.json -WhatIf
./Invoke-ExchangeAdmin.ps1 -Mode Trace -SenderAddress support@contoso.com -Hours 1
```

## What we learned / gotchas

- **Exchange cmdlets only exist after you connect.** Except for the nine `Get-EXO*` cmdlets, the cmdlets are created by implicit remoting, so unit tests need stubs with the right parameter names. One test checks the
  `Get-EXO*` and `Connect-ExchangeOnline` parameters we pass against the real module; the others (`Set-Mailbox`, `New-Mailbox`, `Add-MailboxPermission`, ...) use parameter names from Learn and could not be checked here.
- **`Get-InboxRule` does not work for View-Only Organization Management or the Global Reader role** (Learn). Run the audit as Exchange Administrator or Global Administrator (Learn lists both as giving every task in Exchange Online PowerShell);
  the narrowest role that works was not verified. A mailbox whose rules cannot be read becomes a `CollectionError` finding instead of being silently skipped.
- **Mailbox forwarding switches Inbox-rule redirects off** when `DeliverToMailboxAndForward` is `True` (Learn: *Diagnose Inbox rules that aren't working*, "by design"). So removing mailbox forwarding can make a user's redirect rule start working again:
  re-run the audit after a fix.
- **The outbound spam policy has the last word.** `Off` blocks automatic external forwarding (the sender gets NDR 5.7.520) and disables Inbox rules and mailbox forwarding that redirect outside; `Automatic` was `On` when introduced, became `Off` in 2021 for new tenants and for
  tenants that weren't using it, and *can still be equivalent to `On`* for older ones. Learn says to set `On` or `Off` explicitly. When settings disagree, a block (mail flow rule, remote domain) typically wins. The audit flags `On` as High and `Automatic` as Medium.
- **Outside is not "a domain I don't own".** A domain can be accepted by the tenant and relayed to another mail system (`ExternalRelay`). The audit counts only `Authoritative` and `InternalRelay` as inside. Wildcard accepted domains (`*.fabrikam.example`) are matched.
- **`ForwardingAddress` is a recipient, not an address.** It can point at a mail contact outside the organization; the audit raises it as a Low `MailboxForwardingRecipient` for a human to check and never fixes it.
- **Shared mailboxes (Learn):** up to 50 GB without a licence; over 50 GB needs Exchange Online Plan 2 (100 GB); near the limit they stop sending, then receiving. Litigation hold or archive needs Plan 2 (or Plan 1 plus Exchange Online Archiving).
  The account behind a shared mailbox has a system-generated password and Learn says to block its sign-in and keep it blocked. People who use the mailbox need their own licensed Exchange Online mailbox. Outsiders can't be given access.
  Blocking sign-in is **not automated** here (we report it, you do it in the admin center); `Get-User` gives `AccountDisabled`, and if that is not available the finding is `Info`, never "all fine".
- **`Get-MessageTraceV2` limits (Learn):** 90 days back, 10 days of data per query, 1000 results by default and 5000 at most, no paging (use `StartingRecipientAddress` with the last row's recipient and time), 100 queries per 5 minutes. With no parameters only the last 48 hours come back.
- **Why the fix is guarded:** empty allow list by default; `-WhatIf`; `ConfirmImpact = High` (one prompt per mailbox); re-read before each change; rollback file written after each success and never overwritten; restore refuses to overwrite a new forwarding address.
  The tests prove that `-WhatIf` sends no write, that only `Set-Mailbox -ForwardingSmtpAddress $null` is ever sent by the fix (`DeliverToMailboxAndForward` is left alone), and that a failure in the middle leaves a rollback file with exactly the removals that happened.
- Pitfalls hit while building: a helper that returns `, $array` hands the caller an array *inside* an array, so an empty list looked like one empty item (and produced findings with a blank address): return the array and wrap the call in `@()`; a parameter called `$Sender` trips
  PSScriptAnalyzer because `$Sender` is an automatic variable (renamed `SenderAddress`, as in the cmdlet); a Pester mock that relied on `$PSBoundParameters` did not see an explicit `$null`, so the fake copies the named parameters instead.
- **Not verified** (needs tenant, see [demo.md](demo.md)): the live string format of `ForwardTo` / `RedirectTo` (the parser accepts `"Name" [SMTP:address]` and plain addresses); the format of `TotalItemSize` from `Get-EXOMailboxStatistics` (we accept text with `(n bytes)`, numbers and objects with `ToBytes()`);
  whether `Get-EXOMailboxPermission` returns `User` as a UPN or `DOMAIN\user` in the lab (the comparison with the desired file is case-insensitive but exact); the output property names of `Get-MessageTraceV2` (`Received`, `SenderAddress`, `RecipientAddress`, `Subject`, `Status`, `Size`, `MessageTraceId`) and how soon a message shows up;
  that `Set-Mailbox -ForwardingSmtpAddress $null` clears it through the remoted cmdlet (Learn's troubleshooting articles use exactly this, but not through this module); that a freshly created shared mailbox really needs the retry; the `State` and `Mode` values of `Get-TransportRule`; which Exchange role is the narrowest that can run the audit.

Not covered (to keep the episode to 6 minutes): Send on Behalf (`GrantSendOnBehalfTo` comes back as recipient names, not addresses, so it can't be compared reliably with a file), permissions on user mailboxes, resource and group mailboxes, litigation hold, retention and archive,
hybrid and connectors, remote domains and the Auto forwarded messages report, `Get-MessageTraceDetailV2`, app-only (certificate) authentication for unattended runs, the Defender for Office 365 policies (episode 6), distribution groups and Microsoft 365 groups (episode 3).

## References

- [Get-MessageTraceV2](https://learn.microsoft.com/powershell/module/exchangepowershell/get-messagetracev2) · [Get-InboxRule](https://learn.microsoft.com/powershell/module/exchangepowershell/get-inboxrule) · [Get-EXORecipientPermission](https://learn.microsoft.com/powershell/module/exchangepowershell/get-exorecipientpermission) · [Set-HostedOutboundSpamFilterPolicy](https://learn.microsoft.com/powershell/module/exchangepowershell/set-hostedoutboundspamfilterpolicy) · [Set-Mailbox](https://learn.microsoft.com/powershell/module/exchangepowershell/set-mailbox) · [New-TransportRule](https://learn.microsoft.com/powershell/module/exchangepowershell/new-transportrule)
- [About the Exchange Online PowerShell module](https://learn.microsoft.com/powershell/exchange/exchange-online-powershell-v2) · [Connect to Exchange Online PowerShell](https://learn.microsoft.com/powershell/exchange/connect-to-exchange-online-powershell) · [Find the permissions required to run any Exchange cmdlet](https://learn.microsoft.com/powershell/exchange/find-exchange-cmdlet-permissions) · [Connect with a managed identity (roles that can run Exchange Online PowerShell)](https://learn.microsoft.com/powershell/exchange/connect-exo-powershell-managed-identity)
- [Control automatic external email forwarding](https://learn.microsoft.com/defender-office-365/outbound-spam-policies-external-email-forwarding) · [Configure outbound spam policies](https://learn.microsoft.com/defender-office-365/outbound-spam-policies-configure) · [Recommended settings for EOP and Defender for Office 365](https://learn.microsoft.com/defender-office-365/recommended-settings-for-eop-and-office365)
- [Configure email forwarding for a mailbox](https://learn.microsoft.com/exchange/recipients-in-exchange-online/manage-user-mailboxes/configure-email-forwarding) · [Diagnose Inbox rules that aren't working](https://learn.microsoft.com/troubleshoot/exchange/outlook-issues/resolve-inbox-rule-issues) · [Search the audit log: who set up forwarding](https://learn.microsoft.com/purview/audit-troubleshooting-scenarios#determine-who-set-up-email-forwarding-for-a-mailbox) · [Manage accepted domains in Exchange Online](https://learn.microsoft.com/exchange/mail-flow-best-practices/manage-accepted-domains/manage-accepted-domains) · [Accepted domains (relay domains)](https://learn.microsoft.com/exchange/mail-flow/accepted-domains/accepted-domains)
- [About shared mailboxes](https://learn.microsoft.com/microsoft-365/admin/email/about-shared-mailboxes) · [Create a shared mailbox (and remove its licence)](https://learn.microsoft.com/microsoft-365/admin/email/create-a-shared-mailbox) · [Convert a user mailbox to a shared mailbox](https://learn.microsoft.com/microsoft-365/admin/email/convert-user-mailbox-to-shared-mailbox) · [Exchange Online limits](https://learn.microsoft.com/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits) · [Service advisory for non-compliant shared mailboxes](https://learn.microsoft.com/microsoft-365/enterprise/microsoft-365-non-compliant-shared-mailboxes-exo-service-advisory) · [Manage permissions for recipients](https://learn.microsoft.com/exchange/recipients-in-exchange-online/manage-permissions-for-recipients)
- Blog: [Exchange Online — Complete Guide](https://www.devladlog.com/articles/office-365/2025-01-02-exchange-online-complete-guide-2025/). Note from reading it while planning: its code samples use placeholder cmdlets and an `api.microsoft.com` address instead of Exchange Online PowerShell cmdlets, and it states no Exchange limits, so everything above follows Learn, not the post. It should be corrected.
