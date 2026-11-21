# SharePoint Online administration report

Generated: 2026-11-21

7 finding(s): High 2, Medium 4, Low 0, Info 1.

## Tenant settings against the baseline

| Severity | Setting | Detail |
|---|---|---|
| High | sharingCapability | is externalUserAndGuestSharing, more permissive than the baseline (externalUserSharingOnly). |
| Medium | isResharingByExternalUsersEnabled | is true, the baseline says false. |

## Site hygiene (usage report, period D180)

| Severity | Rule | Site | Detail |
|---|---|---|---|
| High | NearQuota | https://contoso.sharepoint.com/sites/hr | Uses 96 percent of its allocated storage (limit 90 percent). |
| Medium | InactiveSite | https://contoso.sharepoint.com/sites/projects-archive | Last activity 2026-03-02, 264 days ago (limit 90). |
| Medium | NoActivityRecorded | https://contoso.sharepoint.com/sites/new-empty | The report has no activity date for this site (new sites look the same: the report has no creation date). |
| Medium | NoOwner | https://contoso.sharepoint.com/sites/orphan | The report shows no owner principal name for this site. |
| Info | EmptySite | https://contoso.sharepoint.com/sites/new-empty | The site has no files. |

## Storage: 6 site(s), 36.054 GB used

| Site | Used GB | Used of allocated | Owner |
|---|---|---|---|
| https://contoso.sharepoint.com/sites/hr | 24 | 96 % | jordan.demo@contoso.com |
| https://contoso.sharepoint.com/sites/projects-archive | 10 | 40 % | sam.demo@contoso.com |
| https://contoso.sharepoint.com/sites/finance | 2 | 8 % | alex.demo@contoso.com |

## Remediation plan (nothing changed yet)

| Setting | Now | Becomes |
|---|---|---|
| isResharingByExternalUsersEnabled | true | false |

_The usage report has a refresh date (the Report Refresh Date column), is not live, and has no creation date, so a new site can look idle. Site-level sharing and sensitivity labels are not in the Graph report (see the README)._

