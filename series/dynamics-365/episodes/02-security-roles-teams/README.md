# DEVLADLOG Dynamics 365 #2 — Security Roles & Teams

**rolecheck** explains *why* a user can or can't do something to a Dataverse record, following the documented
algorithm step by step ([How access to a record is determined](https://learn.microsoft.com/power-platform/admin/how-record-access-determined)):

1. **Privilege check** — some role, direct or through a team, grants the privilege on the table (level ignored).
2. **Access check** — any of: **ownership** (user or their team owns it), **role access** by level
   (Business Unit / Parent: Child / Organization; for a team's role, measured from the *team's* business unit),
   **shared access** (user, team or organization). A team role at User level whose *Member's privilege inheritance*
   is **Team privileges only** works only on records that team owns.

It also lists **who has access** to a record, runs a **least-privilege audit** (exit code 1 on High findings, for
pipelines), **exports** the real model from an environment, and **verifies** the model against Dataverse's own
`RetrievePrincipalAccess`. It uses the Project Request table from [episode 1](../01-dataverse-deep-dive/).

| Path | What it is |
|---|---|
| [`src/rolecheck/model.py`](src/rolecheck/model.py) | Business units, tables, roles (`isinherited`), users, teams (owner / access / Entra security / Entra Office), records, shares; validation |
| [`src/rolecheck/access.py`](src/rolecheck/access.py) | `explain()` and `who_has_access()` — the documented algorithm, every path and every reason |
| [`src/rolecheck/audit.py`](src/rolecheck/audit.py) | Findings: Organization-level Delete/Assign/Share, users with no privileges, team-only users, unreadable team-owned records, unused roles |
| [`src/rolecheck/export.py`](src/rolecheck/export.py) | Read-only export via Web API: business units, roles + `RetrieveRolePrivilegesRole`, users/teams with N:N expands, records, `RetrieveSharedPrincipalsAndAccess` |
| [`src/rolecheck/verify.py`](src/rolecheck/verify.py) | `RetrievePrincipalAccess` for a user + record, compared privilege by privilege with the model |
| [`src/rolecheck/webapi.py`](src/rolecheck/webapi.py), [`auth.py`](src/rolecheck/auth.py) | GET-only Web API client (paging, 429 + Retry-After), MSAL token provider |
| [`sample/contoso-security.json`](sample/contoso-security.json) | Fictional Contoso: 4 business units, 5 roles, 7 users, 3 teams (one of each kind), 6 records, 1 share |
| [`tests/`](tests/) | 33 pytest tests (export and verify use a stub API shaped like the Learn examples) |

## Run and test (no tenant)

```bash
cd series/dynamics-365/episodes/02-security-roles-teams
python3 -m pip install --user -r requirements.txt
python3 -m pytest -q tests                                     # 33 passed
cd src
python3 -m rolecheck explain --user "Bruno Example" --record PR-0001 --privilege Write
python3 -m rolecheck explain --user "Eva Placeholder" --record PR-0004 --privilege Read
python3 -m rolecheck who --record PR-0001 --privilege Read
python3 -m rolecheck audit; echo "exit=$?"                     # 3 findings, 1 high -> exit=1
```

## Against an environment (needs tenant, read-only)

```bash
export DATAVERSE_URL=https://<org>.crm4.dynamics.com           # + AZURE_* for an app user, or interactive sign-in
cd src
python3 -m rolecheck export --table mgl_projectrequest --out ../lab.json      # don't commit lab.json (real names)
python3 -m rolecheck audit --model ../lab.json
python3 -m rolecheck verify --model ../lab.json --user "<test user>" --record <record guid>
```
The account needs read access to business units, roles, users, teams and the table (System Administrator or a
reader role in a lab). `verify` returns exit code 2 when the model and Dataverse disagree.

## What we learned / gotchas

- **Sharing doesn't replace a role.** Shared access counts only after the privilege check: a user in an access team
  the record is shared with, but without any role granting Read on the table, is denied (Eva in the sample).
- **A team's role is measured from the team's business unit**, not the member's: Parent: Child from *Sales* reaches
  *Sales Portugal*; Business Unit at *Sales* doesn't.
- **Member's privilege inheritance** (`role.isinherited`): *Team privileges only* (0) limits a team role's User-level
  privileges to records owned by that team; *Direct User (Basic) access level and Team privileges* (1) is the default
  for new roles. Both cases are tested.
- **`RetrieveUserPrivileges` only returns the Basic depth for privileges inherited through teams**, regardless of the
  real depth. The exporter reads each role with `RetrieveRolePrivilegesRole` (which returns `Depth`) and the team
  memberships separately, and never calls `RetrieveUserPrivileges` (tested).
- `roles(<id>)/roleprivileges_association` lists privilege *names* without depth, so it's not enough for an audit.
- Privilege names follow `prv` + verb + table SchemaName (`prvAppendTomgl_ProjectRequest`); match `AppendTo` before
  `Append`. A `RecordFilter` depth (filtered record ownership, preview) is skipped with a warning.
- Organization-owned tables only have Organization or None, so access is just the privilege check.

**Not modelled** (the verify step exists to catch these): hierarchy security (manager/position), access inherited
through related records (cascading shares), modernized business units (roles from other business units),
column-level security, filtered record ownership.

## References
- [How access to a record is determined](https://learn.microsoft.com/power-platform/admin/how-record-access-determined)
- [Security roles and privileges](https://learn.microsoft.com/power-platform/admin/security-roles-privileges) (access levels, Member's privilege inheritance)
- [Manage teams](https://learn.microsoft.com/power-platform/admin/manage-teams) and [Manage group teams](https://learn.microsoft.com/power-platform/admin/manage-group-teams)
- [Security concepts for developers](https://learn.microsoft.com/power-apps/developer/data-platform/security-concepts)
- [Use access teams and owner teams](https://learn.microsoft.com/power-apps/developer/data-platform/use-access-teams-owner-teams-collaborate-share-information)
- [Verifying access in code](https://learn.microsoft.com/power-apps/developer/data-platform/security-access-coding) (`RetrievePrincipalAccess`, `RetrieveSharedPrincipalsAndAccess`, the `RetrieveUserPrivileges` note)
- [RetrieveRolePrivilegesRole function](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/reference/retrieveroleprivilegesrole), [RolePrivilege complex type](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/reference/roleprivilege)
- [Role table reference](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/role) (`isinherited`), [Team table reference](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/team) (`teamtype` 0–3)
- [Ownership-based security in Dataverse](https://learn.microsoft.com/power-platform/admin/wp-security-cds)
- Blog: [Security Roles & Teams — Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-11-14-security-roles-teams-complete-guide-2025/)
