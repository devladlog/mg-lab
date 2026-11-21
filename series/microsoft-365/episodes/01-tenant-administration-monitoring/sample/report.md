# Tenant health: contoso
Collected 2026-11-20 09:30 UTC (usage period D30)

**Findings:** 5 High / 3 Medium / 6 Low

| Severity | Area | Finding | Detail |
|---|---|---|---|
| High | Licensing | EMSPREMIUM: Status:Warning, InGracePeriod | 5 assigned of 0 enabled, 5 in grace period (warning) |
| High | Message center | MC000005 overdue by 5 days | Action required: review meeting recording expiration settings [Microsoft Teams] |
| High | Message center | MC000001 action in 4 days | Action required: update the sign-in configuration of a legacy integration [Microsoft Entra] |
| High | Privileged access | 5 active Global Administrator assignments | Microsoft recommends fewer than five. |
| High | Privileged access | Guest holds Global Administrator: Partner Admin (Fabrikam) |  |
| Medium | Licensing | SPE_E5: Exhausted | 25 assigned of 25 enabled |
| Medium | Secure Score | Secure Score dropped 4 percentage points in 7 days | Now 58 percent |
| Medium | Service health | Microsoft Teams: serviceDegradation | TM000001 |
| Low | Licensing | SPE_E3: NearlyFull | 47 assigned of 50 enabled |
| Low | Licensing | AAD_PREMIUM: Unused | 0 assigned of 10 enabled |
| Low | Message center | MC000002 action in 24 days | Plan for change: retention label behaviour in shared libraries [SharePoint Online, OneDrive for Business] |
| Low | Privileged access | Disabled account still holds Global Administrator: Former Admin |  |
| Low | Service health | Microsoft Entra: extendedRecovery | EN000002 |
| Low | Usage | 2 licensed users inactive for 30+ days | megan.sample@contoso.onmicrosoft.com, new.starter@contoso.onmicrosoft.com |

## Service health

| Service | State | Incidents | Advisories |
|---|---|---|---|
| Exchange Online | Healthy | 0 | 0 |
| Microsoft Teams | Degraded | 1 | 0 |
| SharePoint Online | Healthy | 0 | 0 |
| Microsoft Entra | Recovering | 0 | 1 |
| Microsoft 365 suite | Healthy | 0 | 0 |

## Licences

| SKU | Assigned | Purchased | Use % |
|---|---|---|---|
| SPE_E5 | 25 | 25 | 100 |
| SPE_E3 | 47 | 50 | 94 |
| AAD_PREMIUM | 0 | 10 | 0 |
| EMSPREMIUM | 5 | 0 |  |

## Secure Score

290 of 500 (58 percent), change over 7 days: -4

