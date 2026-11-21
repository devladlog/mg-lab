# DEVLADLOG Dynamics 365 #11 — Dynamics 365 Administration

The admin side of the Contoso story from [episodes 1-10](../). The environment, the roles from
[episode 2](../02-security-roles-teams/) and the Sales and Service data are in place; now somebody has to keep the
environment healthy. The Power Platform admin center does the clicking. **adminkit**, a small Python tool, answers
the questions an admin asks every week and writes them down as rules, so a schedule can ask them for you:

- **settings**: reads the single row of the `organization` table (auditing, audit retention, plug-in trace log, session
  and inactivity timeout) and compares it with the team policy in [`admin.json`](admin.json): S001 auditing off (error),
  S002 retention below the team minimum (warning), S003 user access auditing off (info), S004 plug-in trace log left on
  *All* (warning), S005 no timeouts (info)
- **jobs**: failed and stuck **system jobs** (`asyncoperation`): J001 failed in the last 7 days, grouped by operation type
  and message (error); J002 still open after 24 h and not postponed on purpose (warning)
- **admins**: who holds **System Administrator**, through users and through teams: A001 too many enabled people (error),
  A002 disabled user still holds it (warning), A003 a team holds it (warning), A004 application users hold it (info)
- **audit-on**: turns environment auditing on and sets the retention. Dry run by default, `--apply` writes, the new
  values are read back and compared

All report commands exit 1 on errors. All of them run offline on the saved Web API responses in [`sample/`](sample/) with
`--from-json`, and against a real environment without it. The limits in `admin.json` (3 people, 90 days, 24 h) are this
team's policy and fictional lab values, not Microsoft limits.

| Path | What it is |
|---|---|
| [`admin.json`](admin.json) | Team policy: role name, audit requirement and minimum retention, allowed trace-log settings, job window and stuck hours, max human admins |
| [`src/adminkit/settings.py`](src/adminkit/settings.py) | Organization row fetch, report, rules S001-S005, `audit-on` (validation, update-only PATCH, read-back) |
| [`src/adminkit/jobs.py`](src/adminkit/jobs.py) | One `$filter` for failed + open jobs, grouping, postponed-job exemption, rules J001-J002 |
| [`src/adminkit/admins.py`](src/adminkit/admins.py) | `roles` with `$expand` of `systemuserroles_association` and `teamroles_association`, people vs application users, rules A001-A004 |
| [`src/adminkit/cli.py`](src/adminkit/cli.py), [`webapi.py`](src/adminkit/webapi.py), [`auth.py`](src/adminkit/auth.py), [`findings.py`](src/adminkit/findings.py) | CLI; Web API client (429 + Retry-After, formatted values, update-only PATCH); MSAL token provider, as in episodes 1-8; the finding type and exit code |
| [`sample/`](sample/) | `organization.json`, `system-jobs.json`, `system-administrators.json`: fictional responses in Web API shape for the offline runs |
| [`tests/`](tests/) | 28 pytest tests; the Web API is a recording stub (tests only: the demo runs against the real environment) |

## Run and test (no tenant)

```bash
cd series/dynamics-365/episodes/11-dynamics-365-administration
python3 -m pip install --user -r requirements.txt
python3 -m pytest -q tests                                                             # 28 passed
cd src
python3 -m adminkit settings --from-json ../sample/organization.json                  # exit 1: auditing off
python3 -m adminkit jobs --from-json ../sample/system-jobs.json --now 2027-01-15T12:00:00Z   # exit 1: 2 errors
python3 -m adminkit admins --from-json ../sample/system-administrators.json            # exit 1: 4 people
```
```
ERROR   J001  Workflow: 3 failed in 7 d, last 2027-01-15T08:00:03Z: Plug-in error: The account number is required.
ERROR   J001  Bulk Delete: 1 failed in 7 d, last 2027-01-12T10:01:00Z: The bulk delete job could not finish: ...
WARNING J002  Import / Nightly import of price list: still open after 38 h (status 20)
2 error(s), 1 warning(s), 0 info
```

## Against an environment (needs tenant)

Prerequisites: an environment where the signed-in identity is **System Administrator** (or System Customizer for
`audit-on`), see [demo.md](demo.md).

```bash
export DATAVERSE_URL=https://<org>.crm4.dynamics.com
cd src
python3 -m adminkit settings
python3 -m adminkit jobs
python3 -m adminkit admins
python3 -m adminkit audit-on --days 365            # dry run
python3 -m adminkit audit-on --days 365 --apply
```

The Power Platform CLI covers the tenant side that the Web API of one environment does not. Usage lines checked with
`pac` 2.16.1 in the build container (they need a signed-in profile to run):

```powershell
pac admin list --type Trial                      # environments, optionally by type (Trial, Sandbox, Production, ...)
pac admin list-roles --environment <id or url>   # security roles of one environment
pac admin self-elevate --environment <id>        # tenant admins: give yourself System Administrator there
```

## What we learned / gotchas

- **Auditing is off until you turn it on, and it has three levels.** Learn (*Configure auditing*): `isauditenabled`
  defaults to false; the environment switch comes first, then the table (*Audit changes to its data*) and the column
  (*Enable auditing*). `audit-on` only sets the environment level. Changes to the audit configuration are themselves
  audited.
- **Two Learn pages disagree on the default retention.** The admin guide (*Manage Dataverse auditing*) says *Default:
  Forever*; the developer page (*Configure auditing*) says the default of `auditretentionperiodv2` is 30, valid values
  1 to 365,000 days, -1 forever. So `settings` reads the real value instead of assuming, and S002 judges that.
- **A new retention period is not retroactive.** Learn: each audit log is stamped with the retention in force when it was
  written; changing the setting applies to new records only.
- **Tenant admins are not System Administrators.** Learn (*Manage admin roles with PIM*): Global, Power Platform and
  Dynamics 365 admins are no longer given the role automatically; they must elevate themselves in the environment
  (`pac admin self-elevate`), and the elevation is logged to Microsoft Purview. So `admins` shows who holds the role in
  *Dataverse*, not who could get it.
- **Microsoft's own application users hold System Administrator too.** Learn (*System and application users*) lists many
  (for example the provisioning and dataflows services), and `pac admin create-service-principal` gives the new
  application user *System Administrator* by default and prints the client secret in clear text. That is why `admins`
  counts people and application users apart (A001 vs A004) instead of raising an error for every service.
- **Plug-in trace log: off when done.** Learn (*Tracing and logging*): trace logging takes up organization storage, turn
  it on only for troubleshooting; a daily bulk delete job removes trace records older than 24 hours, and Microsoft might
  disable logging if the table passes 100 GB. S004 flags *All*.
- **Trial environments have no backups.** Learn (*Back up and restore environments*, *About trial environments*): trial
  and subscription-based trial environments are not backed up and manual backup is not supported; production, sandbox,
  developer and Teams keep 7 days, and production managed environments can extend to 28. Our demo environment is a
  trial, so the episode shows the admin center's backup page only to say this, and does not take a backup.
- **System jobs wait on purpose too.** `postponeuntil` is a column on the job; J002 skips jobs postponed to the future,
  otherwise recurring jobs would look stuck.
- **Not verified on Learn** (so demo.md step 4 checks them against the real environment): that the `roles` query with
  `$expand=systemuserroles_association(...),teamroles_association(...)` is accepted in exactly this form (Learn names both
  relationships but shows no expand example), and that a role named *System Administrator* exists once per business
  unit (the tool merges them). If the live response differs, the code and tests are fixed from it.

## References
- [Manage Dataverse auditing](https://learn.microsoft.com/power-platform/admin/manage-dataverse-auditing) (three levels, retention Forever / custom up to 24,855 days in the admin center, retention not retroactive, roles needed)
- [Configure auditing](https://learn.microsoft.com/power-apps/developer/data-platform/auditing/configure) (organization columns, default 30, -1 forever, 1 to 365,000)
- [Organization table reference](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/organization) (isauditenabled, plugintracelogsetting choices, session and inactivity timeout columns)
- [System Job (AsyncOperation) table reference](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/asyncoperation) (statuscode choices, operationtype, friendlymessage, postponeuntil, completedon)
- [User (SystemUser) table reference](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/systemuser) (accessmode, isdisabled, applicationid, systemuserroles_association) and [Team table](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/team) (teamroles_association, teamtype)
- [Manage admin roles with Microsoft Entra Privileged Identity Management](https://learn.microsoft.com/power-platform/admin/manage-high-privileged-admin-roles) (no automatic System Administrator, self-elevate, logged to Purview)
- [System and application users](https://learn.microsoft.com/power-platform/admin/system-application-users), [Access controls for Dataverse and Power Platform](https://learn.microsoft.com/azure/azure-sovereign-clouds/public/access-controls-dataverse-power-platform) (minimize System Administrator holders)
- [Tracing and logging](https://learn.microsoft.com/power-apps/developer/data-platform/logging-tracing) (storage, 24-hour cleanup job, 100 GB)
- [Back up and restore environments](https://learn.microsoft.com/power-platform/admin/backup-restore-environments) and [About trial environments](https://learn.microsoft.com/power-platform/admin/trial-environments)
- [pac admin](https://learn.microsoft.com/power-platform/developer/cli/reference/admin) (list, list-roles, self-elevate, create-service-principal) and [Service principals in Power Platform admin](https://learn.microsoft.com/power-platform/admin/powerplatform-api-create-service-principal) (limitations)
- [Page results by using OData](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/query/page-results) and [Service protection API limits](https://learn.microsoft.com/power-apps/developer/data-platform/api-limits) (429, Retry-After)
- Blog: [Dynamics 365 Administration — Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-11-10-dynamics-365-administration-complete-guide-2025/)
