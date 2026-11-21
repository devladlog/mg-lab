# AD hygiene report: lab.contoso.com

Generated 2026-11-20 09:00 UTC. High 3 / Medium 8 / Low 3 / Info 2.

| Severity | Check | Object | Detail |
|---|---|---|---|
| High | PasswordNeverExpires | adm-alex | Password never expires on a user account. |
| High | PasswordNotRequired | scanner01 | PASSWD_NOTREQD is set: this account may have an empty password. |
| High | StaleUser | adm-alex | Privileged account, last sign-in about 140 days ago (lastLogonTimestamp can lag by up to 14 days). |
| Medium | KrbtgtPassword | krbtgt | krbtgt password is 311 days old (policy: 180). Reset it twice, at least 10 hours apart. |
| Medium | PasswordPolicy | lab.contoso.com | Default domain policy minimum password length is 7 (policy: 14). |
| Medium | PrivilegedGroup | Administrators | 2 members besides the built-in Administrator: adm-alex, adm-sam. Policy: at most 1. |
| Medium | PrivilegedGroup | Domain Admins | 2 members besides the built-in Administrator: adm-alex, adm-sam. Policy: at most 1. |
| Medium | RecycleBin | lab.contoso.com | Active Directory Recycle Bin is not enabled. Enabling it is irreversible, and only objects deleted afterwards can be restored from it. |
| Medium | ServiceAccount | svc-backup | User account with an SPN and a password that never expires. Consider a group Managed Service Account (gMSA). |
| Medium | StaleComputer | CON-OLD01 | Computer account last authenticated about 232 days ago. |
| Medium | StaleUser | mlopes | Enabled account, last sign-in about 162 days ago (lastLogonTimestamp can lag by up to 14 days). |
| Low | LockoutPolicy | lab.contoso.com | Account lockout threshold is 0 (never locks out). |
| Low | NeverUsed | rold | Enabled, created 2026-03-01, never signed in. |
| Low | OrphanedAdminCount | pformer | adminCount=1 but no longer in a protected group: inheritance stays off until you clear it. |
| Info | FunctionalLevel | lab.contoso.com | DomainMode is Windows2016Domain (target: 2025). |
| Info | FunctionalLevel | lab.contoso.com | ForestMode is Windows2016Forest (target: 2025). |

