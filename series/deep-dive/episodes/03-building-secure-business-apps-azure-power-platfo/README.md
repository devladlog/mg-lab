# DEVLADLOG Deep Dive #3 — Building secure business apps (Azure + Power Platform + .NET)

Contoso's purchase requests move from a shared spreadsheet to a Power Apps canvas app. The app is only the screen:
every rule lives in a .NET 10 API that trusts nothing but the caller's Microsoft Entra token. Alex submits a
7,500 EUR request, Sam (approver) is refused because it is above the finance threshold, Jordan (finance approver)
approves it, and nobody, Sam included, can approve their own request. Every step, including the refused one, is in
an append-only audit table that even the API's own identity cannot change.

```
Power Apps canvas app ──► custom connector (OAuth 2.0, user's token) ──► ASP.NET Core API on App Service F1 ──► Azure SQL (free offer)
  Alex  (Requester)                                                      JWT: issuer, audience, scp, roles      Entra-only auth
  Sam   (Approver)                                                       policies + business rules              managed identity, data rights only
  Jordan(Approver + Finance.Approver)                                    audit every decision                   DENY UPDATE/DELETE on AuditEntries
```

- **Identity end to end.** The connector calls the API with the signed-in user's token. The API validates issuer,
  audience, signature and lifetime itself, then requires the delegated scope `PurchaseRequests.ReadWrite` (so an
  app-only token with roles is refused) and the app roles `Requester`, `Approver`, `Finance.Approver`.
- **Rules in the API, not in the app.** Segregation of duties, the finance threshold, "already decided", and who may
  read what are pure functions in [`ApprovalRules.cs`](src/PurchaseRequests.Api/Domain/ApprovalRules.cs). Someone
  else's request answers 404, not 403.
- **No secrets.** SQL has Microsoft Entra-only authentication; the web app connects with its system-assigned managed
  identity (`Authentication=Active Directory Default`). The app refuses to start with a password in its connection
  string. Basic-auth publishing (FTP/SCM) is off.
- **Least privilege in the database.** The identity gets `db_datareader` + `db_datawriter`, no DDL. The schema is
  deployed by an admin from [`sql/001-schema.sql`](sql/001-schema.sql), which a test keeps identical to the EF Core
  model. The audit table is append-only for the app (`DENY UPDATE, DELETE`).

| Path | What it is |
|---|---|
| [`src/PurchaseRequests.Api/Security/EntraJwt.cs`](src/PurchaseRequests.Api/Security/EntraJwt.cs) | JWT bearer for one tenant: v1 and v2 issuers, client ID and `api://` audiences, `MapInboundClaims = false` |
| [`src/PurchaseRequests.Api/Security/Policies.cs`](src/PurchaseRequests.Api/Security/Policies.cs) | `Read` / `Submit` / `Decide` policies (scope + oid + roles), fallback policy, `Caller` from the token only |
| [`src/PurchaseRequests.Api/Domain/ApprovalRules.cs`](src/PurchaseRequests.Api/Domain/ApprovalRules.cs) | Segregation of duties, finance threshold, read rule |
| [`src/PurchaseRequests.Api/Endpoints/RequestEndpoints.cs`](src/PurchaseRequests.Api/Endpoints/RequestEndpoints.cs) | Minimal API: submit, mine, pending, get, decide, audit; strict JSON (unknown properties = 400); audit entries in the same transaction; optimistic concurrency |
| [`src/PurchaseRequests.Api/ServiceSetup.cs`](src/PurchaseRequests.Api/ServiceSetup.cs) | Composition: problem details, per-user rate limit on writes, `nosniff` + `no-store`, HSTS, health check |
| [`src/PurchaseRequests.Api/Data/AppDbContext.cs`](src/PurchaseRequests.Api/Data/AppDbContext.cs) | EF Core model + `SqlConnectionGuard` (no passwords outside Development) |
| [`sql/001-schema.sql`](sql/001-schema.sql), [`sql/002-grant-app.sql`](sql/002-grant-app.sql) | Schema (generated from the model) and the managed identity's grants |
| [`infra/main.bicep`](infra/main.bicep) | App Service plan **F1** (Linux, .NET 10), web app with system identity, SQL server (Entra-only), database on the **free offer** (`useFreeLimit`, `AutoPause`), Log Analytics + App Insights |
| [`connector/apiDefinition.swagger.json`](connector/apiDefinition.swagger.json) | Custom connector, OpenAPI 2.0, six operations, OAuth 2.0 |
| [`tests/PurchaseRequests.Tests`](tests/PurchaseRequests.Tests) | 58 xUnit tests |

## Test locally (no Azure, no tenant)

```bash
dotnet test tests/PurchaseRequests.Tests -m:1          # Passed: 58 (about 6 s)
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep   # no warnings
UPDATE_SCHEMA=1 dotnet test tests/PurchaseRequests.Tests --filter SchemaTests        # regenerate sql/001-schema.sql after a model change
```

How the tests work: `WebApplicationFactory<Program>` runs the real app (real JWT bearer handler, real policies, real
rate limiter) in memory. Two things are swapped: the database is SQLite in memory, and the token signing keys come
from a test RSA key instead of the tenant's metadata endpoint. The tests mint real RS256 tokens shaped like Entra
access tokens (v1 and v2, `scp`, `roles`, `oid`), so wrong audience, other tenant, `common` issuer, unknown key,
expired token, missing scope, scope as a substring and missing role are all checked against the production
validation settings. `ContractTests` compiles the Bicep and checks Entra-only SQL, the free-offer settings, F1,
HTTPS-only and no basic auth; it also checks that every connector operation exists in the API with the same name,
route and method, and the other way round. `SchemaTests` generates the SQL Server DDL offline and compares it with
`sql/001-schema.sql`.

Tested with .NET SDK 10.0.115, `Microsoft.AspNetCore.Authentication.JwtBearer` 10.0.15,
`Microsoft.EntityFrameworkCore.SqlServer` 10.0.15 (brings `Microsoft.Data.SqlClient` 6.1.7 and `Azure.Identity`
1.17.1), xUnit 2.9.3, Bicep CLI 0.49.2.

## Deploy (needs an Azure subscription and the lab tenant)

The full runbook (app registration, app roles, SQL grants, connector, canvas app) is in [`demo.md`](demo.md). Azure part:

```bash
az deployment group create -g rg-mglab-deep-dive-03 -f infra/main.bicep -p infra/main.bicepparam \
   -p apiClientId=<API client id> sqlAdminLogin="SQL Admins - Purchase Requests" sqlAdminObjectId=<group object id>
dotnet publish src/PurchaseRequests.Api -c Release -o publish && (cd publish && zip -r ../app.zip .)
az webapp deploy -g rg-mglab-deep-dive-03 -n <webAppName> --src-path app.zip --type zip
# then, as the SQL Entra admin in SSMS: sql/001-schema.sql, then sql/002-grant-app.sql
```

## What we learned / gotchas

- **The token version is the API's choice.** Entra issues the access token version the *API* registration requests:
  `null` or `1` gives v1.0 (issuer `https://sts.windows.net/{tid}/`, audience = App ID URI), `2` gives v2.0 (issuer
  `https://login.microsoftonline.com/{tid}/v2.0`, audience = client ID). Validate the wrong pair and a perfectly
  good token gets 401. The API accepts both pairs for one tenant only; `common` and other tenants are refused
  (tests `V1_token_…`, `V2_token_…`, `Token_from_another_tenant_is_401`, `Multi_tenant_common_issuer_is_401`).
- **Claim mapping breaks role checks.** With the default `MapInboundClaims = true`, `roles`, `scp` and `oid` arrive
  under long schema URIs, so `RequireRole` and the scope check fail and every call is 403. We turn mapping off and set
  `RoleClaimType = "roles"`; `With_default_claim_mapping_the_same_valid_token_is_403` shows the failure.
- **App roles need an assignment.** Creating the roles isn't enough: assign users in *Enterprise applications → Users
  and groups*, otherwise the `roles` claim is empty and the API answers 403.
- **Scope is a space-separated string.** `scp` is one claim like `"User.Read PurchaseRequests.ReadWrite"`; a
  substring check would accept `PurchaseRequests.ReadWriteAll` (test `Scope_must_match_exactly…`).
- **Minimal hosting and test configuration.** Program reads configuration before `Build()`, so
  `ConfigureAppConfiguration` in `WebApplicationFactory` came too late (all tests failed on the tenant check). Host
  settings via `UseSetting` are visible early.
- **F1 has no VNet integration, so SQL needs "Allow Azure services".** That rule (`0.0.0.0`) admits connections from
  *any* Azure-hosted client, other customers included (Learn's warning). Here the protection is Entra-only auth plus
  a database user only for our identity. Production: Basic tier or higher, VNet integration, private endpoint, and
  delete the rule.
- **Learn's quickstarts grant `db_ddladmin` to the app and say that isn't a production practice.** We grant data
  rights only and deploy the schema separately.
- **Free offer is not free hosting.** The database gets 100,000 vCore seconds, 32 GB data and 32 GB backup per month
  (up to 10 free databases per subscription), and with `AutoPause` it pauses until next month instead of billing.
  App Service F1 is free but shared, without SLA, and stops the app with HTTP 403 when its CPU quota is used up.
- **.NET 8 is out of support** (10 Nov 2026), so this episode targets .NET 10 (LTS); App Service Linux offers
  `DOTNETCORE|10.0`.
- **Not verified in the lab yet (needs tenant):** the connector's OAuth configuration against this API, the real
  token version and claims the connector obtains, the SQL grant script in the real database (including that EF Core's
  inserts work with the `DENY` on `AuditEntries`), and F1 cold-start behaviour. The canvas app is built in the
  maker portal from the formulas in `demo.md`; it is not in this folder.

## References

- [Protected web API: accepted token version](https://learn.microsoft.com/entra/identity-platform/scenario-protected-web-api-app-configuration) · [Access tokens: token formats (requestedAccessTokenVersion)](https://learn.microsoft.com/entra/identity-platform/access-tokens#token-formats)
- [STS token version, issuer and audience for v1/v2 (ASP.NET Core docs)](https://learn.microsoft.com/aspnet/core/blazor/security/blazor-web-app-with-entra#sts-token-version)
- [App roles in the `roles` claim and assignment through Enterprise applications](https://learn.microsoft.com/azure/data-api-builder/concept/security/authenticate-entra#step-1-register-an-application-in-microsoft-entra-id)
- [Managed identity from App Service to Azure SQL, `Active Directory Default`](https://learn.microsoft.com/azure/app-service/tutorial-connect-msi-sql-database) · [Passwordless connection and least-privilege note](https://learn.microsoft.com/azure/azure-sql/database/azure-sql-dotnet-entity-framework-core-quickstart#connect-the-app-service-to-azure-sql-database)
- [Microsoft Entra-only authentication for Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/authentication-azure-ad-only-authentication)
- [Azure SQL Database free offer](https://learn.microsoft.com/azure/azure-sql/database/free-tier) · [Free offer FAQ](https://learn.microsoft.com/azure/azure-sql/database/free-tier-faq)
- [Azure SQL firewall: "Allow Azure services" includes other customers](https://learn.microsoft.com/azure/azure-sql/database/firewall-configure#connections-from-inside-azure)
- [App Service limits (Free tier, VNet integration from Basic)](https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits#azure-app-service-limits) · [Quotas: 403 when the Free CPU quota is exceeded](https://learn.microsoft.com/azure/app-service/web-sites-monitor)
- [Deploy ASP.NET Core to App Service (.NET 10 runtime)](https://learn.microsoft.com/azure/app-service/quickstart-dotnetcore) · [Configure ASP.NET Core on Linux App Service](https://learn.microsoft.com/azure/app-service/configure-language-dotnetcore)
- [Custom connector from an OpenAPI definition](https://learn.microsoft.com/connectors/custom-connectors/define-openapi-definition) · [Entra ID authentication for custom connectors](https://learn.microsoft.com/connectors/custom-connectors/azure-active-directory-authentication)
- [Ending support in 2026: .NET 8 (LTS) on November 10, 2026](https://learn.microsoft.com/lifecycle/end-of-support/end-of-support-2026#end-of-servicing)
- Blog: [Building Secure Business Apps — Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-04-07-end-to-end-secure-business-app-azure-powerapps-sharepoint-dotnet/)
