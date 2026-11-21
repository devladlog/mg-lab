# DEVLADLOG Microsoft 365 #1 — Tenant Administration & Monitoring

A **read-only tenant health check** on Microsoft Graph and PowerShell. One command collects what an admin otherwise
checks in five admin centers and turns it into findings with a severity:

- **Service health**: every service mapped to Healthy / Recovering / Degraded / Down, with its open incidents and advisories
- **Message center**: posts with an *action required by* date in the next 30 days (and ones overdue by up to 7 days)
- **Licences**: SKUs that are exhausted, nearly full (90 %+), unused, over-assigned, or in a warning / grace state
- **Global Administrators**: count (Microsoft recommends fewer than five, and two cloud-only emergency access
  accounts), guests and disabled accounts holding the role
- **Secure Score**: latest value and the trend over the last 7 days
- **Inactive licensed users** (usage report), with detection of **concealed** (hashed) report data

It only sends GET requests with read scopes, writes a Markdown report, saves the raw snapshot as JSON (audit trail,
re-render offline), and returns exit code 1 with `-FailOnHigh` so a pipeline or runbook can alert.

| Path | What it is |
|---|---|
| [`src/M365TenantHealth/M365TenantHealth.psm1`](src/M365TenantHealth/M365TenantHealth.psm1) | The module. Collection (`Invoke-M365GraphGet`, `Get-M365UsageReport`, `Get-M365TenantSnapshot`) is kept apart from pure analysis functions (`Get-M365ServiceHealthSummary`, `Get-M365MessageCenterDigest`, `Get-M365LicenseSummary`, `Get-M365InactiveUser`, `Get-M365GlobalAdminReport`, `Get-M365SecureScoreSummary`, `Get-M365TenantFinding`, `ConvertTo-M365HealthMarkdown`) |
| [`src/M365TenantHealth/M365TenantHealth.psd1`](src/M365TenantHealth/M365TenantHealth.psd1) | Module manifest |
| [`src/Invoke-TenantHealthCheck.ps1`](src/Invoke-TenantHealthCheck.ps1) | Runner: delegated sign-in, app-only (certificate) or offline from a saved snapshot; `-OutFile`, `-SnapshotFile`, `-FailOnHigh` |
| [`tests/M365TenantHealth.Tests.ps1`](tests/M365TenantHealth.Tests.ps1) | 38 Pester tests (Graph mocked; 2 of them check our calls against the real Microsoft Graph PowerShell module) |
| [`tests/fixtures/`](tests/fixtures/) | Fictional `contoso` snapshot (zero GUIDs) and usage report CSVs, plain and concealed |
| [`sample/report.md`](sample/report.md) | Report generated from the fictional snapshot |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and the shot list for the lab recording |

## Run the tests

```bash
cd series/microsoft-365/episodes/01-tenant-administration-monitoring
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Without Microsoft.Graph.Authentication installed: Tests Passed: 36, Failed: 0, Skipped: 2
# With it installed (Install-Module Microsoft.Graph.Authentication): Tests Passed: 38, Failed: 0, Skipped: 0
```

Both results above were produced in this repo's container (PowerShell 7.6, Pester 6.2.0, Microsoft.Graph.Authentication
2.41.2 saved to a temp folder and put on `PSModulePath`). PSScriptAnalyzer (Warning and Error) reports 0 issues on `src/`.

## Run it

```powershell
# Offline, no tenant: re-render the fictional snapshot (this is how sample/report.md was produced)
./src/Invoke-TenantHealthCheck.ps1 -FromSnapshot ./tests/fixtures/snapshot.json -Now 2026-11-20T09:30:00Z -OutFile ./sample/report.md -FailOnHigh
# -> 14 findings (5 High / 3 Medium / 6 Low), exit code 1

# Live, delegated (needs tenant): an admin signs in and consents to the 7 read scopes
Install-Module Microsoft.Graph.Authentication -Scope CurrentUser
./src/Invoke-TenantHealthCheck.ps1 -OutFile ./report.md -SnapshotFile ./snapshot.json

# Scheduled, app-only (needs tenant): app registration + certificate, same permissions as *application* permissions
./src/Invoke-TenantHealthCheck.ps1 -TenantId <tenant-id> -ClientId <app-id> -CertificateThumbprint <thumbprint> -OutFile ./report.md -FailOnHigh
```

## Permissions

| Data | API | Least-privileged permission (delegated and application) |
|---|---|---|
| Service health | `GET /admin/serviceAnnouncement/healthOverviews`, `/issues` | `ServiceHealth.Read.All` |
| Message center | `GET /admin/serviceAnnouncement/messages` | `ServiceMessage.Read.All` |
| Active users report | `GET /reports/getOffice365ActiveUserDetail(period='D30')` | `Reports.Read.All` |
| Concealed-names setting | `GET /admin/reportSettings` | `ReportSettings.Read.All` |
| Licences | `GET /subscribedSkus` | `LicenseAssignment.Read.All` |
| Global Administrators | `GET /roleManagement/directory/roleAssignments?$filter=roleDefinitionId eq '62e90394-…'&$expand=principal` | `RoleManagement.Read.Directory` |
| Secure Score | `GET /security/secureScores` | `SecurityEvents.Read.All` |

With delegated permissions the signed-in user also needs a matching Entra role. For usage reports that is one of the
"limited administrator" roles listed by Microsoft; **Global Reader (and Usage Summary Reports Reader) only get
tenant-level data, without per-user detail** — use Reports Reader for the inactive-users check.

## What we learned / gotchas

- **Usage reports are concealed by default.** Since 1 September 2021 Microsoft 365 hides user, group and site names in
  usage reports, and the setting also applies to the Graph reports API. The CSV then has hashes instead of UPNs. The
  module detects that (`Test-M365ConcealedReport`), reads `displayConcealedNames`, and reports it as *Info* instead
  of naming nobody (or the wrong people). Turning it off (Org settings → Reports) is a privacy decision, and showing
  identifiable information is a logged event in the audit log.
- **Status casing differs inside the docs.** The `serviceHealthStatus` enum is documented in camelCase
  (`serviceOperational`), the sample responses show PascalCase (`ServiceOperational`). We compare case-insensitively and
  map unknown values to *Unknown*, never to *Healthy*.
- **`adminReportSettings` comes back inside `value`** in the documented sample response, although it's a single object.
  The GET helper returns whatever is there and the snapshot takes the first item, so both shapes work.
- **Usage reports are files, not JSON.** The reports API answers `302` with a short-lived pre-authenticated download URL;
  the module uses `Invoke-MgGraphRequest -OutputFilePath` and `Import-Csv` (the CSV starts with a BOM; `Import-Csv`
  handles it — there is a test for it).
- **Measure inactivity from the report's own `Report Refresh Date`,** not from today: the report lags behind, and the
  29/30-day boundary has a test.
- **One failing section must not hide the others.** Each section is collected in its own `try/catch`; a 403 becomes a
  *Collection* finding and the rest of the report is still produced. Without a sign-in, the real cmdlet fails every
  section with "Authentication needed. Please call Connect-MgGraph." and the snapshot records exactly that.
- **Role assignments vs eligibility.** `roleAssignments` returns active assignments. Eligible assignments in Privileged
  Identity Management are a separate API (`roleEligibilityScheduleInstances`) and are not counted here.

Not verified here (needs the tenant, see [demo.md](demo.md)): that `Invoke-MgGraphRequest -OutputFilePath` follows the
302 redirect of the reports API in the current module version, and the exact admin roles each section needs in the lab.

## References

- [Working with the service communications API in Microsoft Graph](https://learn.microsoft.com/graph/api/resources/service-communications-api-overview?view=graph-rest-1.0)
- [List healthOverviews](https://learn.microsoft.com/graph/api/serviceannouncement-list-healthoverviews?view=graph-rest-1.0) · [serviceHealthIssue (status values)](https://learn.microsoft.com/graph/api/resources/servicehealthissue?view=graph-rest-1.0)
- [List serviceAnnouncement messages](https://learn.microsoft.com/graph/api/serviceannouncement-list-messages?view=graph-rest-1.0) · [serviceUpdateMessage](https://learn.microsoft.com/graph/api/resources/serviceupdatemessage?view=graph-rest-1.0)
- [reportRoot: getOffice365ActiveUserDetail](https://learn.microsoft.com/graph/api/reportroot-getoffice365activeuserdetail?view=graph-rest-1.0) · [Authorization for APIs to read Microsoft 365 usage reports](https://learn.microsoft.com/graph/reportroot-authorization)
- [Get adminReportSettings](https://learn.microsoft.com/graph/api/adminreportsettings-get?view=graph-rest-1.0) · [Microsoft 365 admin center usage reports: show user details](https://learn.microsoft.com/microsoft-365/admin/activity-reports/activity-reports?view=o365-worldwide) · [Reports show anonymous user names](https://learn.microsoft.com/troubleshoot/microsoft-365/admin/miscellaneous/reports-show-anonymous-user-name)
- [List subscribedSkus](https://learn.microsoft.com/graph/api/subscribedsku-list?view=graph-rest-1.0) · [Product names and service plan identifiers for licensing](https://learn.microsoft.com/entra/identity/users/licensing-service-plan-reference)
- [List unifiedRoleAssignments](https://learn.microsoft.com/graph/api/rbacapplication-list-roleassignments?view=graph-rest-1.0) · [List roleEligibilityScheduleInstances](https://learn.microsoft.com/graph/api/rbacapplication-list-roleeligibilityscheduleinstances?view=graph-rest-1.0)
- [Best practices for Microsoft Entra roles: fewer than five Global Administrators](https://learn.microsoft.com/entra/identity/role-based-access-control/best-practices#5-limit-the-number-of-global-administrators-to-less-than-5)
- [List secureScores](https://learn.microsoft.com/graph/api/security-list-securescores?view=graph-rest-1.0)
- [Invoke-MgGraphRequest](https://learn.microsoft.com/powershell/module/microsoft.graph.authentication/invoke-mggraphrequest?view=graph-powershell-1.0)
- Blog: [Tenant Administration & Monitoring — Complete Guide](https://www.devladlog.com/articles/office-365/2025-07-10-tenant-administration-complete-guide-2025/)
