# DEVLADLOG Microsoft 365 #11 — SharePoint Online Administration

**Write down what the tenant should look like, ask Microsoft Graph what it really looks like, list the sites that need attention, and change
one setting with a way back.** One baseline file ([`src/sharepoint-baseline.json`](src/sharepoint-baseline.json)) and one module read the tenant through Microsoft Graph.
The audit is read-only; the remediation is the only thing that writes, and it is off until you name a setting.

1. **Tenant settings** — `Get-SPATenantSetting` (`GET /admin/sharepoint/settings`) and `Get-SPASettingFinding`: each property in the baseline is compared with the tenant.
   A name that is not an updatable property is an error (a typo must not silently check nothing). Sharing level drift has a direction: wider than the baseline keeps its
   severity, narrower is reported as `Low`. Lists are compared as sets. A property the tenant does not return is `Info`, never drift.
2. **Sites** — `Get-SPASiteUsageReport` (`getSharePointSiteUsageDetail`), `Get-SPASiteFinding`, `Get-SPAStorageSummary`: `InactiveSite`, `NoActivityRecorded`, `NearQuota`,
   `NoOwner`, `EmptySite`. Deleted sites and your `ignoreSiteUrlPatterns` are left out. A concealed report (site URLs are hashes) stops the audit with the setting to change.
3. **Plan** — `Get-SPARemediationPlan`: only a drifted setting that is *also* in `remediate.allowedSettings` (empty by default = nothing).
4. **Act** — `Invoke-SPARemediation` (`PATCH /admin/sharepoint/settings`, `-WhatIf`, `ConfirmImpact = High`): one request per setting with only that property in the body; re-reads the
   tenant first (skips a setting that already matches); writes the **previous value to a rollback file** after each success; stops at the first failure; refuses to overwrite an old rollback file.
   `Restore-SPARemediation` puts the old values back, newest first, **only if the setting still has the value we applied**.

Same fictional tenant as episodes 1–10 (`contoso`); lab users `labadmin`, `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo`. The data in the tests (eight fictional sites, one
settings object) never appears in the demo.

| Path | What it is |
|---|---|
| [`src/sharepoint-baseline.json`](src/sharepoint-baseline.json) | Baseline (example values: yours to decide), site thresholds (90 days, 90 percent), ignore patterns (empty) and the remediation allow list (empty) |
| [`src/SharePointAdmin/SharePointAdmin.psm1`](src/SharePointAdmin/SharePointAdmin.psm1) | The module: Graph collection, pure analysis, remediation and restore, markdown report |
| [`src/SharePointAdmin/SharePointAdmin.psd1`](src/SharePointAdmin/SharePointAdmin.psd1) | Module manifest |
| [`src/Invoke-SharePointAdmin.ps1`](src/Invoke-SharePointAdmin.ps1) | Runner: audit (live, or `-SettingsFile` + `-UsageFile` offline), `-AsOf`, `-OutFile`, `-Remediate -RollbackFile`, `-Restore`, `-WhatIf` |
| [`tests/SharePointAdmin.Tests.ps1`](tests/SharePointAdmin.Tests.ps1) | 53 Pester tests (a small fake Graph tenant, including PATCH bodies and the rollback file; one test checks our calls against the real Microsoft.Graph.Authentication module) |
| [`tests/fixtures/`](tests/fixtures) | Fictional settings, a usage report (and a concealed one) and a test baseline |
| [`sample/sharepoint-report.md`](sample/sharepoint-report.md) | Report for the fictional data, generated offline |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and shot list (no new VM; trial licences only, no cost) |

## Run the tests

```bash
cd series/microsoft-365/episodes/11-sharepoint-online-administration
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Without the real Graph module:  Tests Passed: 52, Failed: 0, Skipped: 1
# With Microsoft.Graph.Authentication on PSModulePath (adds the "real module parameters" test):
#                                 Tests Passed: 53, Failed: 0, Skipped: 0
```

Both results were produced in this repo's container (PowerShell 7.6, Pester 6.2.0; `Microsoft.Graph.Authentication` 2.41.2 saved to a temp folder, since removed). PSScriptAnalyzer (Warning and Error)
reports 0 issues on `src/`. The "What if:" lines printed during the run come from the `-WhatIf` tests.

## Run it

```powershell
cd src
# Offline (no tenant): analyse the fictional data
./Invoke-SharePointAdmin.ps1 -BaselineFile ../tests/fixtures/baseline.test.json -SettingsFile ../tests/fixtures/settings.json `
    -UsageFile ../tests/fixtures/siteusage.csv -AsOf 2026-11-21T12:00:00Z -OutFile ../sample/sharepoint-report.md
#   -> 7 findings (2 setting drifts, 5 site findings); remediation plan 1 change; 6 sites, 36.054 GB

# Needs tenant (see demo.md): copy sharepoint-baseline.json to sharepoint-baseline.lab.json first
./Invoke-SharePointAdmin.ps1 -BaselineFile ./sharepoint-baseline.lab.json -OutFile ./report.lab.md    # SharePointTenantSettings.Read.All, Reports.Read.All, ReportSettings.Read.All
./Invoke-SharePointAdmin.ps1 -BaselineFile ./sharepoint-baseline.lab.json -Remediate -RollbackFile ./rollback.lab.json -WhatIf
./Invoke-SharePointAdmin.ps1 -BaselineFile ./sharepoint-baseline.lab.json -Remediate -RollbackFile ./rollback.lab.json   # + SharePointTenantSettings.ReadWrite.All
./Invoke-SharePointAdmin.ps1 -Restore ./rollback.lab.json
```

## What we learned / gotchas

- **`GET /sites/getAllSites` is application-permission only** (Learn: delegated "Not supported"). The site list here comes from the **SharePoint site usage report**, which works with the
  delegated `Reports.Read.All` and a limited admin role (Learn: *getSharePointSiteUsageDetail*). Columns the Graph report returns: Report Refresh Date, Site Id, Site URL, Owner Display Name, Is Deleted,
  Last Activity Date, File Count, Active File Count, Page View Count, Visited Page Count, Storage Used (Byte), Storage Allocated (Byte), Root Web Template, Owner Principal Name, Report Period.
  The admin-center version of the report also shows external sharing and the sensitivity label; **those two are not columns of the Graph CSV**, so this tool cannot audit per-site sharing.
- **Usage reports hide names by default since 1 September 2021, and that includes site IDs and site URLs** (Learn: *Microsoft 365 admin center usage reports overview*). A Global Administrator
  clears *Conceal user, group, and site names in all reports* (Settings > Org settings > Services > Reports); it takes a few minutes and showing identifiable data is a logged event in the Purview audit
  log. The report still downloads when concealed — it is just hashes — so `Test-SPAConcealedReport` checks that the site URLs are URLs and the audit stops with the setting to change instead of printing a useless table.
- **The report has no creation date.** A site created yesterday has a blank last activity date, exactly like a site nobody ever used: the rule is named `NoActivityRecorded`, not "unused".
  Learn says the last activity date is the most recent activity *regardless of the period you pick*, so `D180` is only the span of the aggregated counters.
- **`PATCH /admin/sharepoint/settings` takes only the properties you send** (Learn: "supply *only* the values for properties to update; existing properties that aren't included maintain their previous values"). Sending one
  property per request is our choice, so a failure names exactly one setting. It needs `SharePointTenantSettings.ReadWrite.All` and the **SharePoint Administrator** role; reading also works for **Global Reader**.
- **What the tool can't set:** `availableManagedPathsForSiteCreation` is read-only, and `idleSessionSignOut` is an object: the baseline refuses both rather than guess how to patch a nested object.
- **Sharing levels, from narrowest to widest** (Learn, *sharingCapabilities*): `disabled` (only people in the organization), `existingExternalUserSharingOnly`, `externalUserSharingOnly` (new and existing guests),
  `externalUserAndGuestSharing` (anyone links). Learn's planning page adds that a site can be set at the same or a more restrictive level than the organization, never wider, and that the OneDrive level
  can't be more permissive than the SharePoint one. *Not verified:* whether `sharingCapability` in this API is the SharePoint level, the OneDrive level, or both: the demo reads it right after a change in the admin center.
- **Why the remediation is guarded:** empty allow list by default; `-WhatIf`; `ConfirmImpact = High`; re-read before each change; rollback written after each success and never overwritten; restore skips a setting
  someone changed after us. The tests prove that `-WhatIf` sends nothing, that only `GET` is sent while auditing, that a PATCH body holds one property (a one-item list stays a JSON array), and that a failure
  in the middle leaves a rollback file with exactly the changes that happened.
- Pitfalls hit while building: `$obj.PSObject.Properties.Name` on an empty object fails under strict mode (the empty-baseline test caught it); a PowerShell function that returns a single hashtable returns the hashtable, not an array,
  so `Patches[0]` in the test helper indexed the hashtable (wrapped with `@()`); `Format-Table` prints nothing without a console (the runner uses `Out-String -Width`).
- **Not verified** (needs tenant, see [demo.md](demo.md)): how long a PATCH takes to show in `GET` and in the admin center; the real `Root Web Template`, `Storage Allocated (Byte)` and `Is Deleted` values
  (the code reads `Is Deleted` as the text `True`/`False`, assumed from the column name) and whether system sites appear in the report (hence `ignoreSiteUrlPatterns`); what the allocated column holds when
  site storage is managed automatically (`isSitesStorageLimitAutomatic`); whether Graph accepts `sharingCapability` changes the same way the admin center does. The baseline values are examples, not Microsoft recommendations.

Not covered (to keep the episode to 6 minutes): site-level sharing, sensitivity labels, site lifecycle and access policies (SharePoint Advanced Management: not in the lab's licences), creating, locking, deleting
or restoring sites, permissions and groups, hub sites and navigation, the SharePoint Online Management Shell and PnP PowerShell, the OneDrive settings (episode 12).

## References

- [sharepointSettings resource](https://learn.microsoft.com/graph/api/resources/sharepointsettings?view=graph-rest-1.0) · [Get settings](https://learn.microsoft.com/graph/api/sharepointsettings-get?view=graph-rest-1.0) · [Update settings](https://learn.microsoft.com/graph/api/sharepointsettings-update?view=graph-rest-1.0)
- [reportRoot: getSharePointSiteUsageDetail](https://learn.microsoft.com/graph/api/reportroot-getsharepointsiteusagedetail?view=graph-rest-1.0) · [sites: getAllSites](https://learn.microsoft.com/graph/api/site-getallsites?view=graph-rest-1.0) · [Working with usage reports in Microsoft Graph](https://learn.microsoft.com/graph/api/resources/report?view=graph-rest-1.0) · [adminReportSettings](https://learn.microsoft.com/graph/api/resources/adminreportsettings?view=graph-rest-1.0)
- [Microsoft 365 admin center usage reports overview (show or conceal names)](https://learn.microsoft.com/microsoft-365/admin/activity-reports/activity-reports?view=o365-worldwide#show-user-group-or-site-details-in-usage-reports) · [SharePoint Site usage report](https://learn.microsoft.com/microsoft-365/admin/activity-reports/sharepoint-site-usage-ww?view=o365-worldwide) · [Reports show anonymous user names](https://learn.microsoft.com/troubleshoot/microsoft-365/admin/miscellaneous/reports-show-anonymous-user-name)
- [Manage sharing settings for SharePoint and OneDrive](https://learn.microsoft.com/sharepoint/turn-external-sharing-on-or-off) · [Plan sharing and collaboration options](https://learn.microsoft.com/sharepoint/collaboration-options) · [Change the sharing settings for a site](https://learn.microsoft.com/sharepoint/change-external-sharing-site)
- Blog: [SharePoint Online Administration — Complete Guide](https://www.devladlog.com/articles/office-365/2025-03-04-sharepoint-online-admin-complete-guide-2025/)
  (note, read 21 Nov 2026: the article's code uses placeholder cmdlets `Set-Configuration` and `Get-DeploymentStatus`, an `api.microsoft.com` endpoint that isn't Microsoft Graph, and `Directory.ReadWrite.All` /
  `User.ReadWrite.All` scopes; it has no SharePoint administration command. This folder's code is meant to replace it.)
