# Microsoft 365 groups lifecycle audit

As of 2026-11-20 09:30 UTC. Tenant expiration policy: 180 days, Selected, alternate: (none). 5 groups, 2 deleted, 7 findings.

| Severity | Target | Rule | Detail |
|---|---|---|---|
| High | Marketing Events 2025 | PurgeSoon | Deleted; permanently deleted on 2026-11-23 (3 days left). Restore now if it's still needed. |
| High | Old Offsite 2024 | OwnerlessExpiring | No owners. Renewal mails for 2026-12-24 go to nobody: no alternate notification email is set. The team also cannot be archived until it has an owner. |
| Medium | Project Falcon | ExpiringSoon | Expires in 15 days (2026-12-05) and wasn't auto-renewed (activity renews around 35 days before expiry): owners are being asked to renew. |
| Medium | TEAM_Sales_Partner Portal | NotCoveredByPolicy | In scope of the policy but has no expirationDateTime (addGroup not applied?). |
| Medium | Tenant | PolicyDrift | Tenant policy differs from lifecycle.json: alternateNotificationEmails. |
| Low | Project Falcon | SingleOwner | Renewal depends on one person. |
| Info | Temp Project Kickoff | Restorable | Deleted; restorable until 2026-12-12 (22 days). |

| Group | Team | Owners | Expires | Last renewed |
|---|---|---|---|---|
| TEAM_Finance_Budget 2027 | yes | 2 | 2027-05-17 | 2026-11-18 |
| Project Falcon | yes | 1 | 2026-12-05 | 2026-06-08 |
| Old Offsite 2024 | yes | 0 | 2026-12-24 | 2026-06-27 |
| TEAM_Sales_Partner Portal | yes | 2 | - | 2025-01-15 |
| Contoso Book Club | no | 1 | - | 2023-02-01 |
