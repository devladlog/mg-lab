# Hybrid migration readiness

## Directory check

Findings: 17 (13 high, 2 medium, 2 low) on 12 account(s). Ready for directory synchronization: **no, fix the high findings first**.

| Severity | Rule | Account | What was found |
|---|---|---|---|
| High | ProxyInvalidChars | jordan.demo | proxyAddresses 'SMTP:jordan demo@contoso.com' has a space or one of < > ( ) ; , [ ] " (Learn: a space makes the value be discarded and regenerated) |
| High | UpnInvalidChars | jordan.demo | UPN 'jordan demo@contoso.com': contains '' (or a space) |
| High | ProxyInvalidChars | jose.demo | proxyAddresses 'SMTP:josé.demo@contoso.com' has letters with diacritical marks |
| High | UpnInvalidChars | jose.demo | UPN 'josé.demo@contoso.com': letters with diacritical marks or other non-ASCII characters |
| High | UpnDuplicate | lee.demo | UPN 'lee.demo@contoso.com' is also used by: lee.old |
| High | UpnDuplicate | lee.old | UPN 'lee.demo@contoso.com' is also used by: lee.demo |
| High | UpnFormat | pat.demo | UPN 'pat.@contoso.com': user name ends with a period, ampersand, space or at sign |
| High | ProxyInvalidChars | quinn.demo | proxyAddresses 'smtp:quinn (old)@contoso.com' has a space or one of < > ( ) ; , [ ] " (Learn: a space makes the value be discarded and regenerated) |
| High | MailDuplicate | riley.demo | mail 'shared.alias@contoso.com' is also used by: taylor.demo |
| High | ProxyDuplicate | riley.demo | proxyAddress 'shared.alias@contoso.com' is also used by: taylor.demo |
| High | UpnNonRoutable | sam.demo | UPN suffix 'contoso.local' is not a verified domain in the tenant. Learn: such a UPN is synchronized to the onmicrosoft.com domain instead. |
| High | MailDuplicate | taylor.demo | mail 'shared.alias@contoso.com' is also used by: riley.demo |
| High | ProxyDuplicate | taylor.demo | proxyAddress 'shared.alias@contoso.com' is also used by: riley.demo |
| Medium | SamTooLong | a.very.long.account.name | sAMAccountName is 24 characters (maximum 20) |
| Medium | MailNicknameLeadingDot | casey.demo | mailNickname '.casey' starts with a period |
| Low | UpnMailMismatch | lee.old | UPN 'lee.demo@contoso.com' differs from the primary SMTP address 'lee.old@contoso.com' (Learn recommends aligning them) |
| Low | DisplayNameMissing | nodisplay.demo | displayName is empty (Learn: if the attribute exists it must have a value) |


