# Exchange Online audit

Collected: 2026-11-21T12:00:00Z (UTC). 9 mailboxes (3 shared), 4 mail flow rules, 3 outbound spam policies, 3 accepted domains.

**18 findings:** 6 high, 4 medium, 7 low, 1 info. 2 can be fixed by this tool (and only if the rule is in `fix.allowedRules`).

| Severity | Rule | Target | What was found |
|---|---|---|---|
| High | InboxRuleForwardingExternal | riley.demo@contoso.com | Inbox rule 'Forward to home' (enabled) sends mail to riley.home@example.net. |
| High | MailboxForwardingExternal | sam.demo@contoso.com | Forwards all mail to sam.private@example.com (without keeping a copy). |
| High | MailboxForwardingExternal | taylor.demo@contoso.com | Forwards all mail to taylor@partner-relay.example (and keeps a copy). |
| High | OutboundAutoForwarding | Open | Automatic external forwarding is allowed (On). |
| High | SharedMailboxOverLimit | finance@contoso.com | Holds 51 GB, over the 50 GB limit of an unlicensed shared mailbox. |
| High | TransportRuleExternalCopy | Copy HR to outside counsel | Mail flow rule sends or copies mail to counsel@example.org (state Enabled, mode Enforce). |
| Medium | OutboundAutoForwarding | Default | Automatic external forwarding is system-controlled (Automatic): it is Off in new tenants since 2021 but can still behave as On in older ones. |
| Medium | SharedMailboxNearLimit | support@contoso.com | Holds 46 GB, 92% of the 50 GB limit of an unlicensed shared mailbox. |
| Medium | SharedMailboxSignInEnabled | support@contoso.com | The account behind this shared mailbox can sign in. Learn: always block sign-in for it and keep it blocked. |
| Medium | TransportRuleExternalCopy | Test redirect | Mail flow rule sends or copies mail to audit@example.org (state Disabled, mode Audit). |
| Low | FullAccessSprawl | finance@contoso.com | 12 people have Full Access (limit in config: 10). |
| Low | InboxRuleForwardingExternal | riley.demo@contoso.com | Inbox rule 'Old rule' (disabled) sends mail to riley.home@example.net. |
| Low | MailboxForwardingRecipient | jordan.demo@contoso.com | Forwards all mail to the recipient 'Casey Contractor' (ForwardingAddress). Check that it is internal: a mail contact can point outside. |
| Low | MailboxNearQuota | riley.demo@contoso.com | Uses 95% of its send/receive quota (95 of 100 GB). |
| Low | SharedMailboxNoDelegates | archive-old@contoso.com | Nobody has Full Access or Send As on this shared mailbox. |
| Low | TransportRuleNoComment | Footer | The rule has no comment, so nobody can tell later why it exists. |
| Low | TransportRuleNoComment | Test redirect | The rule has no comment, so nobody can tell later why it exists. |
| Info | SharedMailboxSignInUnknown | archive-old@contoso.com | Could not read whether the account behind this shared mailbox can sign in (Get-User unavailable or no result). |

### What to do about each rule

- **FullAccessSprawl**: Use a security group as the delegate, and review who still needs it.
- **InboxRuleForwardingExternal**: Users create these rules themselves (or an attacker does after a takeover). The outbound spam policy is the control that blocks them.
- **MailboxForwardingExternal**: Remove it, or allow the domain in forwarding.allowedExternalDomains if it is intended.
- **MailboxForwardingRecipient**: Get-Recipient on that name shows whether it is a mail contact or mail user with an external address.
- **MailboxNearQuota**: Archive, clean up, or enable the archive mailbox.
- **OutboundAutoForwarding**: Learn recommends Off (set it explicitly): Set-HostedOutboundSpamFilterPolicy -AutoForwardingMode Off.
- **SharedMailboxNearLimit**: Plan the Exchange Online Plan 2 licence, or clean up, before it stops sending.
- **SharedMailboxNoDelegates**: Either it is unused (remove it) or access is granted another way.
- **SharedMailboxOverLimit**: Learn: a shared mailbox over 50 GB needs an Exchange Online Plan 2 licence (or less data). Over the limit it stops sending, then receiving.
- **SharedMailboxSignInEnabled**: Microsoft 365 admin center > Users > Active users > the shared mailbox > Block sign-in.
- **SharedMailboxSignInUnknown**: Check Active users in the Microsoft 365 admin center.
- **TransportRuleExternalCopy**: This rule is live: every matching message leaves the organization.
- **TransportRuleNoComment**: Set-TransportRule -Comments "owner, date, reason".

### Fix plan (2 forwarding removals)

- sam.demo@contoso.com: stop forwarding to smtp:sam.private@example.com
- taylor.demo@contoso.com: stop forwarding to smtp:taylor@partner-relay.example

