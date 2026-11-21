# Demo shot list — DEVLADLOG Microsoft 365 #10: Exchange Online Administration

Everything in `src/` and `tests/` already ran in the build container (65 Pester tests against a fake Exchange tenant, an offline report from a fictional inventory). This file lists what the
human-supervised session must set up and record in the **lab tenant**. Every Exchange call below is **needs tenant**; every screen shows the real product (the real Exchange admin center, Outlook on the web,
the script talking to the real Exchange Online). `tests/fixtures/*` and `sample/` are for the automated tests only and never appear on screen.

Nothing is bought. The seeded "leaks" use reserved example addresses (`example.com`, `example.org`) and are removed in tear-down. Never use a real external address.

## Lab environment

No VM. Recorded on the **lab Windows desktop**: a browser on the lab tenant (Exchange admin center, Microsoft 365 admin center, Outlook on the web) and PowerShell 7.2+ on the host.

| Cloud item | Notes | Cost / requirement |
|---|---|---|
| Microsoft 365 E5 trial (already in the lab, until 20 Dec 2026) | Includes Exchange Online; every lab user already has an E5 licence, so each has a mailbox | in the lab |
| Lab users | `labadmin` (recording account, Global Administrator: Learn lists Global Administrator and Exchange Administrator as giving every task in Exchange Online PowerShell), `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo` | none |
| Seeded items (created in Setup, removed in Tear-down) | forwarding on `riley.demo`; an Inbox rule on `taylor.demo`; a disabled mail flow rule; one shared mailbox `mglab-support` | none |
| Host PowerShell | PowerShell 7.2+, `Install-Module ExchangeOnlineManagement -Scope CurrentUser` (tests were run with 3.11.1) | none |
| Sign-in | `Connect-ExchangeOnline -UserPrincipalName <lab admin UPN>` opens the interactive sign-in. The recorder signs in; no credential is written to any file | none |

## Setup (before recording)

1. **Module and a dry connection.** `Install-Module ExchangeOnlineManagement -Scope CurrentUser`, then `Connect-ExchangeOnline -ShowBanner:$false`. Off camera, run a baseline audit and save it:
   `./Invoke-ExchangeAdmin.ps1 -SaveSnapshot ./snapshot.lab.json -OutFile ./audit.lab.md`. Check the `Collection` rows: any `CollectionError` finding names a cmdlet or permission that failed (Get-User, Get-InboxRule, ...). **Fix the cause, do not record around it.**
   This run also tells you the real string formats listed under "Not verified" in the README: look at the `ForwardTo` text and the `totalBytes` values in `snapshot.lab.json`.
2. **Forwarding on one mailbox (needs tenant, writes).**
   `Set-Mailbox -Identity riley.demo@<lab domain> -ForwardingSmtpAddress riley.private@example.com -DeliverToMailboxAndForward $false`
   (Learn: this is how an admin forwards outside; the Exchange admin center shows it under Recipients > Mailboxes > riley.demo > Manage email forwarding.) Mail sent to `example.com` is never delivered: don't send test mail to this mailbox during the recording.
3. **An Inbox rule that forwards outside.** Sign in to Outlook on the web as `taylor.demo` (lab password, not recorded) > Settings > Mail > Rules > Add new rule: name `MG Lab forward`, condition *Apply to all messages*, action *Forward to* `taylor.private@example.com`. Save.
   **Not verified:** that the web UI accepts an external address typed here (it should: it is how users forward) and what `Get-InboxRule` then returns in `ForwardTo`. If the address is refused, record that as the lesson and create the rule another way, or skip this beat.
4. **A mail flow rule that copies outside, left switched off.** Exchange admin center > Mail flow > Rules > Add a rule > Create a new rule: name `MG Lab test copy`, apply to messages from `sam.demo`, action *Bcc the message to* `counsel@example.org`, mode **Test without Policy Tips**, no comment (the audit asks for one), save and **leave it disabled**.
   (The audit should then show `TransportRuleExternalCopy` as Medium and `TransportRuleNoComment`.)
5. **Config for the lab.** Copy `src/exchange.json` to `exchange.lab.json` (outside the repo). Leave everything as shipped except `fix.allowedRules`: `["MailboxForwardingExternal"]` (do this only after the first audit looks right).
   Put your own break-glass or service mailboxes (if the lab has any beyond the demo users) in `forwarding.ignoreMailboxes`.
6. **Shared mailbox file.** Copy `src/shared-mailboxes.json` to `shared-mailboxes.lab.json` and fill it in:
   ```json
   { "removeExtra": false, "mailboxes": [ { "alias": "mglab-support", "displayName": "MG Lab Support", "fullAccess": ["sam.demo@<lab domain>"], "sendAs": ["sam.demo@<lab domain>"] } ] }
   ```
7. **Outbound spam policy:** look, don't touch. Defender portal > Email & collaboration > Policies & rules > Threat policies > Anti-spam > Anti-spam outbound policy (Default): note the *Automatic forwarding rules* value; the audit reports it as it is (a new trial tenant is probably `Automatic`, which is Medium).
   **Not verified:** the value in this tenant.

## Screens to capture (match `script.yaml` screen scenes)

### 1. `screens/audit.jpg` — "The audit, on the real tenant" (needs tenant, read-only)
```powershell
./Invoke-ExchangeAdmin.ps1 -ConfigFile ./exchange.lab.json -OutFile ./audit.lab.md
```
Capture the findings table (severity, rule, target, what was found), the totals line and `Fix plan: n removal(s)`. With `fix.allowedRules` still empty in the first run the plan line says 0 (matches the narration "the fix plan is empty"); in the recording order
run it once with the shipped config, then switch to `exchange.lab.json` with the rule allowed for screen 2. Rewrite the narration to the real rows. Mask the tenant domain in every address.

### 2. `screens/fix.jpg` — "Preview, remove, restore" (needs tenant, **writes**)
1. `./Invoke-ExchangeAdmin.ps1 -Mode Fix -ConfigFile ./exchange.lab.json -RollbackFile ./rollback.lab.json -WhatIf` : "What if" lines, nothing removed, no rollback file (`Test-Path ./rollback.lab.json` is `False`).
2. Same command without `-WhatIf`: it asks to confirm each mailbox (`ConfirmImpact = High`). Answer **Yes only for `riley.demo`**. Expected: one `Removed` row. If another mailbox appears in the plan, answer No and say why (it is a real finding).
3. Exchange admin center > Recipients > Mailboxes > `riley.demo` > Manage email forwarding: off. Show `rollback.lab.json` (mailbox address masked). Re-run the audit: the finding is gone.
4. `./Invoke-ExchangeAdmin.ps1 -Mode Restore -RollbackFile ./rollback.lab.json` : `Restored`. Refresh the admin center: forwarding is back. Then set it to `$null` again in Tear-down (or run Fix once more with a new rollback file name).
Rewrite the narration to the real mailbox. **Do not run the Fix against any mailbox that is not a lab demo mailbox.**

### 3. `screens/shared.jpg` — "Create it, send a message, trace it" (needs tenant, **writes**)
1. `./Invoke-ExchangeAdmin.ps1 -Mode SyncSharedMailboxes -DesiredFile ./shared-mailboxes.lab.json -WhatIf` : lists create + 2 grants, writes nothing.
2. Same without `-WhatIf` : `Done` rows. The grants of a new mailbox are retried (up to `provision.retryCount`, `provision.retrySeconds` apart). **Not verified** that the retry is needed in the lab: say so if the first grant works at once.
3. Run it a third time: "Already as declared: nothing to do."
4. Outlook on the web as `sam.demo`: open the shared mailbox (right-click the account's folder list > Add shared folder or mailbox, or wait for auto-mapping), send a message **from the shared mailbox** to `alex.demo`.
5. After a few minutes: `./Invoke-ExchangeAdmin.ps1 -Mode Trace -ConfigFile ./exchange.lab.json -SenderAddress mglab-support@<lab domain> -Hours 1`. Capture the row (status `Delivered`, recipient, trace id). If nothing shows yet, wait and run again, and say how long it took
   (**not verified:** how quickly a message appears).
6. Re-run the audit: `SharedMailboxSignInEnabled` (Medium) for `mglab-support`. In the Microsoft 365 admin center > Users > Active users > MG Lab Support > Block sign-in; re-run the audit and the finding is gone (Learn: block it and keep it blocked).
Rewrite the narration to the real names. Mask addresses.

## Masking checklist
- Tenant name and domain, admin UPN, user addresses beyond the lab aliases, trace ids if they could identify the tenant.
- `exchange.lab.json`, `shared-mailboxes.lab.json`, `snapshot.lab.json`, `audit.lab.md`, `rollback.lab.json` contain tenant data: don't show them in full, never commit them.

## Tear-down
1. If forwarding is still restored or removed differently from how you found it: `Set-Mailbox riley.demo@<lab domain> -ForwardingSmtpAddress $null`. Check with `Get-Mailbox riley.demo@<lab domain> | Format-List *forwarding*`.
2. Outlook on the web as `taylor.demo`: delete the rule `MG Lab forward`.
3. Exchange admin center > Mail flow > Rules: delete `MG Lab test copy`.
4. Delete the shared mailbox: `Remove-Mailbox -Identity mglab-support@<lab domain> -Confirm:$false` (or the Exchange admin center). Check that `sam.demo` no longer shows it in Outlook.
5. Delete `exchange.lab.json`, `shared-mailboxes.lab.json`, `snapshot.lab.json`, `audit.lab.md`, `rollback.lab.json`; `Disconnect-ExchangeOnline -Confirm:$false`.
