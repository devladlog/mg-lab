# DEVLADLOG Power BI #15: Administration and Governance

Same **Contoso Bikes** scenario as the rest of the series. This episode is the admin side: a **read-only Monday check** of the tenant, written as a
PowerShell module with tests. It answers four questions: did a tenant setting change (drift against a baseline file), which workspaces have no Admin,
what do nine rules say about the metadata scanner result, and what happened yesterday in the activity log. Nothing in the tenant is changed.

Blog guide: <https://www.devladlog.com/articles/power-bi/2025-08-11-administration-governance-complete-guide-2025/>
(its code was not used: see "Not verified / not done").

**Draft status.** The module and its 59 tests are done and run here. The real calls to the Power BI and Fabric admin APIs have **never** been made: they need the lab tenant (see [demo.md](demo.md)).

| Path | What it is |
|---|---|
| [`src/PbiGovernance/PbiGovernance.psm1`](src/PbiGovernance/PbiGovernance.psm1), [`.psd1`](src/PbiGovernance/PbiGovernance.psd1) | The module, 11 exported functions (below) |
| [`src/Invoke-GovernanceAudit.ps1`](src/Invoke-GovernanceAudit.ps1) | The Monday run: drift, orphans, scan + rules, activity. Writes `out/governance-<date>.md`, `findings-<date>.json`, `scan-<date>.json`. `-ScanResultPath` applies the rules to a saved scan (offline), `-FailOn error\|warning\|none` sets the exit code |
| [`src/policy/tenant-baseline.example.json`](src/policy/tenant-baseline.example.json) | The baseline format (setting name, enabled, group names); write your own with `Export-PbiTenantBaseline` |
| [`tests/PbiGovernance.Tests.ps1`](tests/PbiGovernance.Tests.ps1), [`tests/fixtures/`](tests/fixtures) | Pester 5+, 59 tests. Fixtures are shaped like the Learn response samples, fictional names, zero GUIDs |
| [`tests/test_script.py`](tests/test_script.py) | pytest, 5 tests: `script.yaml` follows the series brief and every code scene is a real excerpt of `src/` |

Functions: `Get-PbiActivityEvent` (one UTC day, continuation token), `Get-PbiActivitySummary` (per activity, most viewed reports, failures, risky operations),
`Get-PbiOrphanedWorkspace` (Get Groups as Admin, Learn's OData filter), `Get-PbiModifiedWorkspace`, `Invoke-PbiWorkspaceScan` (getInfo in chunks of 100, poll, scanResult),
`Test-PbiGovernance` (rules GV001-GV009), `Get-PbiTenantSetting` (Fabric admin API, own token, retry on 429, `continuationUri`), `Export-PbiTenantBaseline`,
`Compare-PbiTenantSetting`, `New-PbiGovernanceReport`, `Get-PbiGovernanceRule`.

| Rule | Severity | Meaning |
|---|---|---|
| GV001 | warning | item without a sensitivity label |
| GV002 | info | semantic model neither promoted nor certified |
| GV003 | error | the scanner lists a misconfigured data source usage |
| GV004 | warning | schema could not be read (blind spot) |
| GV005 | error | workspace without an Admin |
| GV006 | warning | item shared with the whole organization (principal type None) |
| GV007 | info | workspace not Active |
| GV008 | warning | RLS role without members |
| GV009 | info | personal workspace holding items |

GV005 and GV006 read user lists, which the scanner returns only with `getArtifactUsers`; without them those rules stay silent and the report says so rather than "all clear".

## Run it

```bash
# from the episode folder: PowerShell 7.2+ and Pester 5+ (6.2.0 here); no tenant, no MicrosoftPowerBIMgmt needed
pwsh -NoProfile -Command "Invoke-Pester ./tests/PbiGovernance.Tests.ps1 -Output Normal"   # 59 passed, about 30 s
python3 -m pytest tests -q                                                                  # 5 passed (needs PyYAML)

# offline run of the rules on the saved scan: 12 findings, exit code 1
cd src && pwsh -NoProfile -File ./Invoke-GovernanceAudit.ps1 -ScanResultPath ../tests/fixtures/scan-result.json -SkipActivity -OutDir /tmp/out -Date 2026-11-20

# the real thing (needs the lab tenant, MicrosoftPowerBIMgmt, a Fabric administrator, see demo.md)
Connect-PowerBIServiceAccount
./Invoke-GovernanceAudit.ps1 -BaselinePath ./policy/tenant-baseline.json -FabricToken $fabric
```

What the 59 tests cover: the activity log (UTC day boundaries, the 28 day limit, paging through three pages including a page with a token and no events, the request cap, filters),
the summary, the orphaned-workspace filter, modified workspaces, the scan loop (chunks of 100, polling, failure, timeout), every rule on a fixture scan (including a workspace with an empty users list),
tenant settings (paging, 429 with `Retry-After`, 403, and one test over **real HTTP** against a loopback listener, a test stand-in only), baseline and drift, the report (a section that did not run says so),
the offline script (exit codes, files), and that the fixtures and sources contain no real names, tenants or GUIDs.

## Needs tenant / licence / lab

Everything that calls the services: all of `demo.md`. In the lab (M365 E5 trial, Fabric/Power BI trial): `labadmin` is Global Administrator and therefore Fabric administrator.
No paid capacity or licence is needed. Whether the activity log returns events in the lab tenant (auditing state) was not checked.

## Not verified / not done

1. **No real call was made.** The Power BI admin calls are mocked with Learn-shaped responses; the Fabric call was only tested against a local stand-in. Field names such as `groupUserAccessRight`, `principalType`, `misconfiguredDatasourceUsages` come from the Learn samples; whether the lab tenant returns them as expected is open.
2. **Separate tokens** are used for the two APIs because I did not verify that a Power BI token is accepted by `api.fabric.microsoft.com`.
3. **Get Groups as Admin:** Learn says its `users` property will be removed in a future release while its own orphaned-workspace example still uses `$expand=users`; check the result on the tenant. The scanner (GV005) is the other route.
4. **Lag:** Learn gives up to 15 minutes for a tenant setting and 30 to 60 minutes for activity events; the real delays are to be recorded (demo.md).
5. **Orphaned workspace in the lab:** how to create one (a workspace whose only Admin is removed) was not verified; the fallback is the offline run on the fixture.
6. The blog guide's code uses placeholder cmdlets that do not exist (`Set-Configuration`, `Get-DeploymentStatus`); none of it was used.

## References (Microsoft Learn)

- Get Activity Events: <https://learn.microsoft.com/en-us/rest/api/power-bi/admin/get-activity-events>
- Track user activities (audit): <https://learn.microsoft.com/en-us/power-bi/admin/service-admin-auditing>
- Operation list: <https://learn.microsoft.com/en-us/fabric/admin/operation-list>
- Metadata scanning (overview): <https://learn.microsoft.com/en-us/power-bi/enterprise/service-admin-metadata-scanning>
- Scanner: Get Modified Workspaces <https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-get-modified-workspaces>, Post Workspace Info <https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-post-workspace-info>, Get Scan Result <https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-get-scan-result>
- Get Groups as Admin: <https://learn.microsoft.com/en-us/rest/api/power-bi/admin/groups-get-groups-as-admin>
- List Tenant Settings (Fabric): <https://learn.microsoft.com/en-us/rest/api/fabric/admin/tenants/list-tenant-settings>
- Tenant settings index: <https://learn.microsoft.com/en-us/fabric/admin/tenant-settings-index>
