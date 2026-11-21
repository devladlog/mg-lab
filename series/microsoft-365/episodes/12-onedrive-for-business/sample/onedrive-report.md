# OneDrive for Business report

Generated: 2026-11-21

9 finding(s): High 3, Medium 3, Low 1, Info 2.

## Tenant OneDrive settings against the baseline

| Severity | Setting | Detail |
|---|---|---|
| High | allowedDomainGuidsForSyncApp | is (empty list), the baseline says 00000000-0000-0000-0000-0000000000d1. |
| High | isUnmanagedSyncAppForTenantRestricted | is false, the baseline says true. Without it, users can sync on any PC, not only on PCs joined to specific domains. |
| Medium | deletedUserPersonalSiteRetentionPeriodInDays | is 30, the baseline says 90. |

## Accounts (usage report, period D180)

| Severity | Rule | Owner | Detail |
|---|---|---|---|
| High | NearFull | jordan.demo@contoso.com | Uses 92.2 percent of its storage limit (limit 90 percent). |
| Medium | InactiveOneDrive | sam.demo@contoso.com | Last activity 2026-04-02, 233 days ago (limit 180). |
| Medium | NoActivityRecorded | taylor.demo@contoso.com | Has 12 file(s) but no activity date in the report. |
| Low | NeverUsed | riley.demo@contoso.com | No files and no activity recorded: the OneDrive was provisioned but never used. |
| Info | CustomQuota | morgan.demo@contoso.com | Storage limit is 5120 GB, not the tenant default of 1024 GB (a licence can also cap the default). |
| Info | DeletedRetained | casey.former@contoso.com | The owner was deleted: this OneDrive is in the retention period (the tenant setting), then 93 days in the site collection recycle bin. |

## Storage: 6 account(s), 1010.719 GB used, 1 deleted

| Owner | Used GB | Used of limit |
|---|---|---|
| jordan.demo@contoso.com | 943.718 | 92.2 % |
| alex.demo@contoso.com | 60 | 5.9 % |
| morgan.demo@contoso.com | 5 | 0.1 % |

_The report only lists users with a valid OneDrive licence, and a deleted owner shows up only after at least seven days (Microsoft Learn). Nothing here changed the tenant._

