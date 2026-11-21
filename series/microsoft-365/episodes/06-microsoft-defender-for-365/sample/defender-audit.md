# Defender for Office 365 audit

Collected 2026-11-21 10:00 UTC. 6 mailboxes, 5 preset rules, 2 settings below the Standard baseline, 13 findings.

## Coverage

| Mailbox | EOP features | Defender for Office 365 |
|---|---|---|
| labadmin@contoso.onmicrosoft.com | Strict | Standard |
| alex.demo@contoso.onmicrosoft.com | Standard | Standard |
| sam.demo@contoso.onmicrosoft.com | Standard | Standard |
| jordan.demo@contoso.onmicrosoft.com | Default/custom | Built-in protection |
| riley.demo@contoso.onmicrosoft.com | Strict | Standard |
| taylor.demo@contoso.onmicrosoft.com | Default/custom | None |

## Findings

| Severity | Target | Rule | Detail |
|---|---|---|---|
| High | ATP rule: Strict Preset Security Policy | PresetDisabled | State is 'Disabled': nobody gets these protections. |
| High | Mailbox: labadmin@contoso.onmicrosoft.com | PriorityNotStrict | Priority account, but gets EOP: Strict, Defender: Standard. |
| High | Mailbox: riley.demo@contoso.onmicrosoft.com | PriorityNotStrict | Priority account, but gets EOP: Strict, Defender: Standard. |
| High | Mailbox: taylor.demo@contoso.onmicrosoft.com | NoSafeLinksOrAttachments | Excluded from Built-in protection and not in a preset: no Safe Links or Safe Attachments from presets. |
| Medium | Anti-Spam: Default | BelowStandard | BulkThreshold is '7', Standard recommends '6'. |
| Medium | ATP rule: Standard Preset Security Policy | CombinedConditions | Uses SentToMemberOf + RecipientDomainIs: different condition types are ANDed. Matches one condition but not all: jordan.demo@contoso.onmicrosoft.com, taylor.demo@contoso.onmicrosoft.com. |
| Medium | ATP Safe Links: Contoso Safe Links (legacy) | BelowStandard | AllowClickThrough is 'True', Standard recommends 'False'. |
| Medium | EOP rule: Standard Preset Security Policy | CombinedConditions | Uses SentToMemberOf + RecipientDomainIs: different condition types are ANDed. Matches one condition but not all: jordan.demo@contoso.onmicrosoft.com, taylor.demo@contoso.onmicrosoft.com. |
| Medium | Mailbox: jordan.demo@contoso.onmicrosoft.com | NotOnPreset | Not covered by Standard or Strict (EOP: Default/custom, Defender: Built-in protection). |
| Medium | Mailbox: taylor.demo@contoso.onmicrosoft.com | NotOnPreset | Not covered by Standard or Strict (EOP: Default/custom, Defender: None). |
| Medium | Rule: ATP Built-In Protection Rule | BuiltInProtectionExcluded | Exceptions: taylor.demo@contoso.onmicrosoft.com. Microsoft: exceptions are typically only for users without Defender for Office 365 licences. |
| Low | ATP rule: Standard Preset Security Policy | Drift | SentToMemberOf is 'all-staff@contoso.onmicrosoft.com' in the tenant, '' in defender.json. -ApplyPresets fixes it. |
| Low | EOP rule: Standard Preset Security Policy | Drift | SentToMemberOf is 'all-staff@contoso.onmicrosoft.com' in the tenant, '' in defender.json. -ApplyPresets fixes it. |
