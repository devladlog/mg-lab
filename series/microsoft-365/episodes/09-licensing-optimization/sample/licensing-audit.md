# Microsoft 365 licence optimization report

Generated: 2026-11-21

10 users scanned, 11 finding(s): High 2, Medium 8, Low 1, Info 0.

**Reclaimable seats: 6** (6 priced). Potential saving 122 EUR per month, 1464 EUR per year, only if the subscription is reduced at renewal.

## Findings

| Severity | Rule | User | Licence | How assigned | Reclaimable | Detail |
|---|---|---|---|---|---|---|
| High | AssignmentError | morgan.demo@contoso.example | Microsoft_Entra_ID_Governance | Group | no | State Error, error CountViolation. Not enough licences: buy more, or free seats held by users who do not use them. |
| High | RedundantLicence | sam.demo@contoso.example | O365_BUSINESS_PREMIUM | Direct | yes | O365_BUSINESS_PREMIUM is covered by SPE_E5 on the same user. |
| Medium | DisabledAccountLicensed | taylor.demo@contoso.example | Microsoft_Entra_ID_Governance | Direct | yes | Account is disabled but still holds Microsoft_Entra_ID_Governance. |
| Medium | DisabledAccountLicensed | taylor.demo@contoso.example | SPE_E5 | Group | no | Account is disabled but still holds SPE_E5. Assigned through a group: remove the user from the group instead. |
| Medium | InactiveLicensed | jordan.demo@contoso.example | Microsoft_Entra_ID_Governance | Direct | yes | No successful sign-in for 98 days (limit 90). |
| Medium | InactiveLicensed | jordan.demo@contoso.example | SPE_E5 | Direct | yes | No successful sign-in for 98 days (limit 90). |
| Medium | NeverSignedIn | emergency-01@contoso.example | Dynamics_365_Sales_Premium_Viral_Trial | Direct | no | Never signed in, created 81 days ago. Not reclaimable: the user is in protectedUsers. |
| Medium | NeverSignedIn | emergency-01@contoso.example | SPE_E5 | Direct | no | Never signed in, created 81 days ago. Not reclaimable: the user is in protectedUsers. |
| Medium | NeverSignedIn | riley.demo@contoso.example | Dynamics_365_Sales_Premium_Viral_Trial | Direct | yes | Never signed in, created 81 days ago. |
| Medium | NeverSignedIn | riley.demo@contoso.example | SPE_E5 | Direct | yes | Never signed in, created 81 days ago. |
| Low | DuplicateDirectAndGroup | alex.demo@contoso.example | Microsoft_Entra_ID_Governance | Both | yes | Microsoft_Entra_ID_Governance is assigned directly and through a group: removing the user from the group would not free the seat. |

## Seats paid for but not assigned

| Licence | Seats | Assigned | Unassigned | Monthly cost of idle seats |
|---|---|---|---|---|
| SPE_E5 | 25 | 8 | 17 | 850 EUR |
| O365_BUSINESS_PREMIUM | 5 | 1 | 4 | 40 EUR |
| Microsoft_Entra_ID_Governance | 25 | 6 | 19 | 114 EUR |
| Dynamics_365_Sales_Premium_Viral_Trial | 25 | 3 | 22 | 0 EUR |

## Reclaim plan (nothing removed yet)

| User | Licence | Why |
|---|---|---|
| alex.demo@contoso.example | Microsoft_Entra_ID_Governance | DuplicateDirectAndGroup |
| sam.demo@contoso.example | O365_BUSINESS_PREMIUM | RedundantLicence |
| jordan.demo@contoso.example | Microsoft_Entra_ID_Governance | InactiveLicensed |
| riley.demo@contoso.example | Dynamics_365_Sales_Premium_Viral_Trial | NeverSignedIn |
| taylor.demo@contoso.example | Microsoft_Entra_ID_Governance | DisabledAccountLicensed |

_Removing a licence is not free of consequences: Exchange Online data is held for 30 days and then deleted, and an unlicensed OneDrive is archived after 93 days (Microsoft Learn). Money is saved only when the subscription is reduced; an annual commitment cannot be reduced mid-term._

