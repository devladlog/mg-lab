# Intune device audit

9 Windows device(s).

## Compliance state

| State | Devices | % |
|---|---|---|
| compliant | 7 | 78 |
| inGracePeriod | 1 | 11 |
| noncompliant | 1 | 11 |

## Findings (10)

| Severity | Rule | Device | User | Message |
|---|---|---|---|---|
| High | NonCompliant | CON-W11-02 | sam.demo@contoso.onmicrosoft.com | complianceState is noncompliant. Open Devices > Monitor > Noncompliant devices for the failing setting. |
| High | NotEncrypted | CON-W11-02 | sam.demo@contoso.onmicrosoft.com | isEncrypted is false. |
| Medium | DuplicateSerial | CON-W11-04 | sam.demo@contoso.onmicrosoft.com | serial SER-0009 appears on 2 records (CON-W11-04, CON-W11-04-OLD): re-enrolled device or stale record. |
| Medium | DuplicateSerial | CON-W11-04-OLD | sam.demo@contoso.onmicrosoft.com | serial SER-0009 appears on 2 records (CON-W11-04, CON-W11-04-OLD): re-enrolled device or stale record. |
| Medium | NeverSynced | CON-W11-04-OLD | sam.demo@contoso.onmicrosoft.com | no lastSyncDateTime: enrolled but never completed a sync. |
| Medium | OsBelowMinimum | DESKTOP-OLD01 | jordan.demo@contoso.onmicrosoft.com | OS 10.0.19045.5011 is below the policy minimum 10.0.26100.0. |
| Medium | StaleCheckIn | LAPTOP-STALE02 | riley.demo@contoso.onmicrosoft.com | last sync 62 days ago (limit 30). A device cleanup rule (30-270 days) only hides the record; it does not wipe or retire. |
| Low | InGracePeriod | CON-W11-03 | taylor.demo@contoso.onmicrosoft.com | in grace period, expires 2026-11-22 08:00 UTC |
| Low | NoPrimaryUser | KIOSK-01 |  | no primary user (userless device). |
| Low | PersonalOwned | BYOD-PC-01 | alex.demo@contoso.onmicrosoft.com | personal (BYOD) device: check the enrollment restrictions you intended. |

