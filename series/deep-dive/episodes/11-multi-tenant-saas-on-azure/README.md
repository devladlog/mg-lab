# DEVLADLOG Deep Dive #11 — Multi-tenant SaaS on Azure (Entra tenants + EF Core filter + SQL row-level security)

Contoso's purchase-request platform (episodes 3, 4 and 7) is now offered to other companies. **Northwind Traders** and
**Adventure Works** sign in with their own Microsoft Entra tenants and use **one shared app and one shared database**.
The episode builds the part that decides whether that is safe: how a request becomes "tenant X", and three independent
locks that keep tenant X's rows away from everyone else.

```
Customer tenant (Entra)        Tenant API (ASP.NET Core, App Service)                     Azure SQL (one database)
 user signs in ──token(tid)──► 1. JWT: issuer must be login.microsoftonline.com/{tid}/v2.0
                                  for the token's OWN tid, and tid must be onboarded
                               2. TenantContext = tid claim (never a header, route or body)
                               3. EF Core query filter  TenantId == tid   (reads)
                                  SaveChanges stamps/refuses TenantId     (writes)   ──► 4. connection opens:
                               5. rate limit + plan quota per tenant                        sp_set_session_context
                                                                                         6. SECURITY POLICY: filter + block
                                                                                            predicates read SESSION_CONTEXT
```

- **One identity rule.** The tenant comes from the signed token's `tid` and from nowhere else. Learn: "Always check
  that the `tid` in a token matches the tenant ID used to store data with the application" and never authorize with
  `email`, `preferred_username`, `unique_name` or `upn`. A contract test fails the build if the source reads a tenant
  from a header or one of those claims.
- **Multitenant issuer validation.** Signing keys come from the shared `organizations` metadata; its issuer is a
  template, so `TenantIssuer` validates it in code: v2.0 token, issuer exactly `…/{tid}/v2.0` for the token's own `tid`,
  and that tenant is in the catalog (or is the provider's home tenant).
- **Three locks for data.** EF Core filter (reads) → `SaveChanges` stamps and refuses (writes) → SQL Server
  **row-level security** (both, enforced by the database, fail-closed when no tenant is set).
- **Onboarding is a platform action, not a side effect of consent.** A platform admin calls `PUT /admin/tenants/{tid}`.
  Learn warns never to use the `tenant` value returned on the admin-consent redirect to identify anyone.
- **Per-tenant limits.** Rate limiting partitions by `tid` (users of one customer share a bucket) and sizes it by plan;
  a plan quota stops one tenant filling the shared database. Both are the "noisy neighbour" controls for a shared stamp.
- **No secrets.** SQL is Entra-only; the web app reaches it with its system-assigned managed identity; the app gets only
  table rights and a column `DENY UPDATE` on `TenantId`.

| Path | What it is |
|---|---|
| [`src/TenantApi/Tenancy/`](src/TenantApi/Tenancy) | `TenantIssuer` (multitenant issuer check), `TenantContext` (tid claim only), `TenantDirectory` (cached catalog lookup), `PlanCatalog` (limits per plan; unknown plan = smallest plan) |
| [`src/TenantApi/Data/`](src/TenantApi/Data) | `AppDbContext` (tenant in the key, query filter, stamping/refusing writes), `TenantSessionContextInterceptor` (sets `SESSION_CONTEXT` on connection open) |
| [`src/TenantApi/Endpoints/`](src/TenantApi/Endpoints), [`Policies.cs`](src/TenantApi/Policies.cs), [`ServiceSetup.cs`](src/TenantApi/ServiceSetup.cs) | `/me`, `/requests`, `/admin/tenants`; scope policy; `Platform.Admin` only from the home tenant; per-tenant rate limiter |
| [`sql/001-schema.sql`](sql/001-schema.sql), [`002-rls.sql`](sql/002-rls.sql), [`003-grant-app.sql`](sql/003-grant-app.sql) | Tables (tenant first in the key), the security policy, least-privilege grants for the managed identity |
| [`sql/verify-rls.sql`](sql/verify-rls.sql) | Runs in a real database inside a transaction it rolls back: A sees 2, B sees 1, none sees 0, cross-tenant insert fails with 33504 |
| [`infra/main.bicep`](infra/main.bicep), [`main.bicepparam`](infra/main.bicepparam) | App Service **F1** (Linux, .NET 10), Azure SQL logical server (Entra-only) + database with the **free offer**, no passwords |
| [`scripts/SaasLab.psm1`](scripts/SaasLab.psm1) | Graph bodies for the two multitenant app registrations, admin-consent URL, device-code sign-in for any tenant, token claim viewer, API client that keeps status codes |
| [`scripts/New-SaasApps.ps1`](scripts/New-SaasApps.ps1) | Creates `contoso-saas-api` and `contoso-saas-cli` in the provider tenant (`az rest` to Graph, `-WhatIf`) |
| [`tests/TenantApi.Tests/`](tests/TenantApi.Tests), [`tests/SaasLab.Tests.ps1`](tests/SaasLab.Tests.ps1) | 57 xUnit tests, 11 Pester tests |

## Test locally (no Azure, no tenant)

```bash
dotnet test tests/TenantApi.Tests -m:1                 # Passed: 57, Failed: 0 (about 25 s after restore)
pwsh -NoProfile -c 'Invoke-Pester ./tests'             # Tests Passed: 11, Failed: 0
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep     # no warnings
```

How the tests work (.NET SDK 10.0.115, EF Core 10.0.15, ASP.NET Core JwtBearer 10.0.15, xUnit 2.9.3):
- **API tests** (31) run the real app through `WebApplicationFactory`: real JWT bearer pipeline with RS256 tokens signed
  by a test key, real tenant resolution, authorization, rate limiting and EF Core. Only two things differ from
  production: the database is **SQLite in memory** (there is no Docker and no SQL Server here) and the signing keys come
  from the test key instead of Entra's metadata endpoint. Covered: each tenant sees only its rows; another tenant's id is
  a 404, identical to a missing id; `X-Tenant-Id`, a query string and a body field cannot choose the tenant; unknown
  tenant 401; suspended tenant 403; issuer of another tenant on a token whose `tid` is yours 401; v1.0 token, wrong
  audience, wrong key 401; missing scope 403; onboarding takes effect on the next call (cache eviction); `Platform.Admin`
  in a customer tenant 403; plan quota 409 for one tenant only; the rate limit is shared by the users of one tenant and
  does not touch another tenant.
- **Data tests** (11): query filter fails closed with no tenant; writes are stamped; a row for another tenant and a
  write with no tenant are refused (sync and async); `TenantId` cannot be modified; **`IgnoreQueryFilters` and raw SQL
  skip the filter** (shown on purpose: this is why the database repeats the rule); the same `Id` can exist in two tenants.
  The session-context interceptor runs against a real SQLite connection that EF opens itself, with the command text
  swapped (SQLite has no `SESSION_CONTEXT`): it proves *when* the command runs and *which tenant* it carries.
- **T-SQL tests** (10): all four scripts are parsed with Microsoft's own `ScriptDom` (`TSql160Parser`,
  `Microsoft.SqlServer.TransactSql.ScriptDom` 170.191.0). The EF model and `001-schema.sql` must have the same tables
  and columns; every `ITenantScoped` table must have a filter and `AFTER INSERT` / `AFTER UPDATE` block predicates in the
  policy, and nothing else may be under it; the interceptor's command is `sp_set_session_context` with the same key the
  policy reads and `@read_only = 1`; the app user has no `CONTROL`/`ALTER` and a column `DENY UPDATE (TenantId)`.
- **Contract tests** (5): no `IgnoreQueryFilters` or raw SQL in `src`; no tenant from headers/routes/`email`-type claims;
  `TenantContext` is the only reader of `tid`; Bicep has no passwords, Entra-only SQL, the free offer with `AutoPause`.
- **Pester** (11): the Graph request bodies, the admin-consent URL, the device-code loop (pending, decline, slow-down)
  with `Invoke-RestMethod` mocked, the claim decoder, `Invoke-SaasApi` with `Invoke-WebRequest` mocked.

**What the tests cannot prove (needs the lab):** that the policy really filters and blocks in SQL Server / Azure SQL
(`sql/verify-rls.sql` does, in the demo), the Bicep deployment, the Graph calls, consent in a second tenant.

## Deploy and run (needs the lab Azure subscription and tenant)

Full runbook, costs, masking and tear-down in [`demo.md`](demo.md). Short version:

```bash
./scripts/New-SaasApps.ps1                                         # az login first; prints the two client IDs
az group create -n rg-mglab-deep-dive-11 -l westeurope
az deployment group create -g rg-mglab-deep-dive-11 -f infra/main.bicep -p apiClientId=<api id> sqlAdminLogin=<UPN> sqlAdminObjectId=<object id>
# then sql/001..003 as the SQL admin, dotnet publish + az webapp deploy, PUT /admin/tenants/{tid} per customer
```

## What we learned / gotchas

- **The home tenant is not a customer.** Our first test run failed with 401 on every admin call: the issuer check
  required every tenant to be in the catalog, and the provider's own staff sign in from the home tenant. `TenantIssuer`
  now accepts the home tenant explicitly, and `/me` and `/requests` still answer 403 for it ("no tenant data").
- **A role is only as trustworthy as the tenant that assigned it.** App roles are assigned in each customer's own copy of
  the enterprise app, so a customer admin can give `Platform.Admin` to a user of theirs. The admin policy therefore also
  requires `tid` = home tenant. (This is our design reasoning, tested in `OnboardingTests`; Learn's claims-validation
  article makes the related point that tenant checks alone are not enough and subject and actor must be validated too.)
- **A filter in app code is not a security boundary.** `IgnoreQueryFilters()` and raw SQL both bypass it (there is a test
  that shows it). That is the reason for the policy in the database, and for a test that forbids those calls in `src`.
- **Row-level security applies to everyone.** Learn: it also applies to `dbo`, `db_owner` and the table owner, so the
  database admin sees zero rows until the session context is set; to see all rows for troubleshooting the policy
  must be written to allow it. `ALTER SECURITY POLICY … STATE = OFF` leaves the table unprotected; to change a predicate
  use `ALTER FILTER/BLOCK PREDICATE` (Learn: ALTER SECURITY POLICY, examples D and E).
- **`@read_only = 1` matters with pooling.** Learn: it keeps the value from changing "until the connection is closed
  (returned to the connection pool)". The interceptor is a single shared instance that reads the tenant from the context
  that opened the connection: a new interceptor instance per scope would make EF Core build a new internal service
  provider each time.
- **The key helps.** With `TenantId` in the primary key, EF Core itself refuses to modify it (tested), the same `Id` in two
  tenants is two rows, and every lookup starts inside one tenant. The extra `CrossTenantWriteException` check on modified
  `TenantId` is a second lock for the day the key changes.
- **Block predicates have a gap on update.** Learn: the optimizer does not check `AFTER UPDATE` when the predicate
  columns were not changed. That is why the app also gets `DENY UPDATE` on `TenantId` (the same pattern as Learn's
  middle-tier example).
- **Don't read the tenant from the consent redirect.** Learn (admin consent): never use the `tenant` value of the
  response to authenticate or authorize; it can be sent by bad actors. Onboarding is a separate, authenticated platform call.
- **Consent covers both registrations.** The API lists the CLI in `knownClientApplications`, so one consent in the customer
  tenant covers client and API (Learn: multitenant conversion, "Multiple tiers in a single tenant"). Learn also says
  all resources must exist in the customer tenant before a client can be consented.
- **Free database offer:** a limit of 10 free databases per subscription, no SLA, `AutoPause` stops it at the monthly
  allowance instead of billing (Learn: free tier FAQ). F1 has no VNet integration, so the SQL firewall admits Azure
  services; production needs Basic or higher with a private endpoint.
- **Not verified in the lab yet:** the deployment (F1 with `DOTNETCORE|10.0` is carried over from episode 3); the three
  SQL scripts and `verify-rls.sql` against SQL Server 2022 / Azure SQL (parsed only); the Graph bodies (`New-SaasApps.ps1`
  is syntax-checked and its bodies are unit-tested, not run); whether `api://<appId>` is accepted as the Application ID
  URI of a multitenant app (Learn says multitenant URIs must be globally unique and gives a verified-domain pattern; if the
  portal refuses it, the script's PATCH needs `https://<verified domain>/<name>`); device-code sign-in and consent against
  a second tenant; `Platform.Admin` appearing in the `roles` claim of a device-code token.

## References

- [Architect multitenant solutions on Azure](https://learn.microsoft.com/azure/architecture/guide/multitenant/overview) · [Tenancy models](https://learn.microsoft.com/azure/architecture/guide/multitenant/considerations/tenancy-models) · [Map requests to tenants](https://learn.microsoft.com/azure/architecture/guide/multitenant/considerations/map-requests) · [Deployment Stamps pattern](https://learn.microsoft.com/azure/architecture/patterns/deployment-stamp) · [Storage and data approaches](https://learn.microsoft.com/azure/architecture/guide/multitenant/approaches/storage-data)
- [Convert single-tenant app to multitenant (issuer values, /common and /organizations, consent, knownClientApplications)](https://learn.microsoft.com/entra/identity-platform/howto-convert-app-to-be-multi-tenant) · [Validate claims: tenant, subject, actor](https://learn.microsoft.com/entra/identity-platform/claims-validation) · [Admin consent endpoint](https://learn.microsoft.com/entra/identity-platform/v2-admin-consent) · [Device authorization grant](https://learn.microsoft.com/entra/identity-platform/v2-oauth2-device-code)
- [Row-level security (filter and block predicates, SESSION_CONTEXT, middle-tier example)](https://learn.microsoft.com/sql/relational-databases/security/row-level-security) · [ALTER SECURITY POLICY](https://learn.microsoft.com/sql/t-sql/statements/alter-security-policy-transact-sql) · [Database engine errors 31000 to 41399 (33504)](https://learn.microsoft.com/sql/relational-databases/errors-events/database-engine-events-and-errors-31000-to-41399)
- [Azure SQL Database free tier](https://learn.microsoft.com/azure/azure-sql/database/free-tier) · [Free tier FAQ](https://learn.microsoft.com/azure/azure-sql/database/free-tier-faq)
- Blog: [Multi-Tenant SaaS on Azure — Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-08-11-multi-tenant-saas-on-azure-architecture-identity-data-isolation/)
