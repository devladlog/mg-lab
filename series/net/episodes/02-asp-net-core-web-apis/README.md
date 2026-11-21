# DEVLADLOG .NET #2 — ASP.NET Core Web APIs with controllers: Entra ID, problem details, rate limiting

An **expense claims API** with controllers on **.NET 10 (LTS)**, secured with JWT bearer tokens that come from
`dotnet user-jwts` on your machine and from **Microsoft Entra ID** in Azure — same code, only configuration changes.

- **`[ApiController]`**: attribute routing, `[FromBody]` inference, automatic **400 `ValidationProblemDetails`**,
  problem details for 4xx results (`NotFound()`, `Forbid()`)
- **DataAnnotations + `IValidatableObject`**: currency code, allowed categories, no future dates, 90-day limit
- **Domain errors → `IExceptionHandler`**: the workflow throws `ClaimNotFoundException` / `ClaimConflictException`,
  `DomainExceptionHandler` writes 404/409 problem details via `IProblemDetailsService`
- **JWT bearer** configured from `Authentication:Schemes:Bearer` (no hard-coded authority), `MapInboundClaims = false`,
  role claim `roles` (Entra app roles); policy **`Approver`** = app role `Claims.Approve`
- Rule: you **can't approve your own claim** (409), employees only see their own claims (403 on someone else's)
- **Rate limiting**: per-user fixed window on `POST /api/claims`, **429** + `Retry-After` + problem details
- **OpenAPI 3.1** with every status code described (`[ProducesResponseType]`)

| Path | What it is |
|---|---|
| [`src/ExpenseClaims.Api/Program.cs`](src/ExpenseClaims.Api/Program.cs) | Controllers, problem details, exception handler, JWT bearer, `Approver` policy, rate limiter, OpenAPI |
| [`src/ExpenseClaims.Api/Controllers/ClaimsController.cs`](src/ExpenseClaims.Api/Controllers/ClaimsController.cs) | `[ApiController]` with `List`, `Get`, `Submit` (rate limited), `Approve` (policy) |
| [`src/ExpenseClaims.Api/Claims/ExpenseClaim.cs`](src/ExpenseClaims.Api/Claims/ExpenseClaim.cs) | Model + `SubmitClaimRequest` with validation attributes and `IValidatableObject` |
| [`src/ExpenseClaims.Api/Claims/ClaimWorkflow.cs`](src/ExpenseClaims.Api/Claims/ClaimWorkflow.cs) | In-memory store and approval rules; domain exceptions with their HTTP status |
| [`src/ExpenseClaims.Api/Infrastructure/DomainExceptionHandler.cs`](src/ExpenseClaims.Api/Infrastructure/DomainExceptionHandler.cs) | `IExceptionHandler` → 404/409 problem details |
| [`src/ExpenseClaims.Api/Infrastructure/CurrentUser.cs`](src/ExpenseClaims.Api/Infrastructure/CurrentUser.cs) | User id from `oid` (Entra) or `sub` (user-jwts) |
| [`tests/ExpenseClaims.Api.Tests/ClaimsApiFactory.cs`](tests/ExpenseClaims.Api.Tests/ClaimsApiFactory.cs) | `WebApplicationFactory` that keeps the **real JwtBearer handler** and signs Entra-shaped tokens with a per-run key |
| [`tests/ExpenseClaims.Api.Tests/ApiTests.cs`](tests/ExpenseClaims.Api.Tests/ApiTests.cs) | 18 integration tests: 401 (none/expired/wrong audience/wrong key), 400, 403, 404, 409, 429, OpenAPI |
| [`tests/ExpenseClaims.Api.Tests/UnitTests.cs`](tests/ExpenseClaims.Api.Tests/UnitTests.cs) | 9 unit tests: validation rules and workflow |
| [`tests/ExpenseClaims.Api.Tests/ConfigurationTests.cs`](tests/ExpenseClaims.Api.Tests/ConfigurationTests.cs) | The App Service settings keys bind to `JwtBearerOptions` |
| [`deploy/local-demo.sh`](deploy/local-demo.sh) / [`local-demo.output.txt`](deploy/local-demo.output.txt) | Walk-through with `dotnet user-jwts` tokens (401, 400, 201, 403, 200, 409, 429) and its real output |
| [`deploy/deploy-appservice.sh`](deploy/deploy-appservice.sh) | Publish + zip, F1 Linux plan, web app, Entra settings as app settings, zip deploy |
| [`deploy/call-api.sh`](deploy/call-api.sh) | Gets an Entra access token with `az account get-access-token --scope api://<id>/Claims.Submit`, prints `aud/iss/roles`, calls the API |

## Build, test, run

```bash
dotnet test -m:1                                                # Passed: 28, Failed: 0 (~1 s)
dotnet user-jwts create --project src/ExpenseClaims.Api         # first time only: creates the signing key
dotnet run --project src/ExpenseClaims.Api --launch-profile http   # http://localhost:5252
./deploy/local-demo.sh                                          # tokens from dotnet user-jwts, then curl
```

`dotnet user-jwts` (part of the .NET SDK) stores its signing key in user secrets and already wrote the matching
`ValidAudiences`/`ValidIssuer` into `appsettings.Development.json`. The project's `UserSecretsId` is
`mglab-net02-expense-claims`. Tested with .NET SDK 10.0.115 / runtime 10.0.15 on Linux.

## Deploy with Microsoft Entra ID (needs a tenant + subscription)

1. App registration **contoso-expense-claims-api** (single tenant) → *Expose an API* → App ID URI `api://<client-id>`,
   scope **Claims.Submit**; *Authorized client applications* → add the Azure CLI (`04b07795-8ddb-461a-bbee-02f9e1bf7b46`).
2. *App roles* → **Claims.Approve** (Users/Groups) → *Enterprise applications* → assign it to the approver user (lab: Sam Demo, `sam.demo`).
3. `RG=rg-mglab-net-02 APP=contoso-claims-<unique> TENANT_ID=<tenant> API_CLIENT_ID=<client-id> ./deploy/deploy-appservice.sh`
4. `./deploy/call-api.sh https://<host> <client-id> [claim-id]`

Step-by-step with screens: [`demo.md`](demo.md). `PACKAGE_ONLY=1 ./deploy/deploy-appservice.sh` was verified here
(728 KB zip); the Azure and Entra steps were not run in this container.

## What we learned / gotchas

- **`[Produces("application/json")]` turned our problem responses into `application/json`.** With it on the
  controller, the automatic 400 and the 404 lost their `application/problem+json` content type (two tests failed).
  Removing the attribute fixed it. Clients that switch on the media type care.
- **One class-level `[ProducesResponseType(401)]` removed the 200 from every operation** in `/openapi/v1.json`.
  `GET /api/claims` showed only `401`, although the action returns `ActionResult<IReadOnlyList<ExpenseClaim>>`.
  We now declare the success responses explicitly (`[ProducesResponseType<ExpenseClaim>(200)]`, `201` on submit),
  and a test pins the status codes per operation.
- **`dotnet user-jwts create --role X` writes a `role` claim; Entra writes `roles`.** With `MapInboundClaims = false`
  and `RoleClaimType = "roles"`, `--role` tokens got 403. Use `--claim roles=Claims.Approve` locally.
- **Create the first user-jwts token before starting the API.** On a fresh machine we started `dotnet run`, then ran
  `dotnet user-jwts create`: the signing key didn't exist when the app read its configuration, so every token got
  401 until we restarted the API. `local-demo.sh` now checks for this and tells you to restart.
- **Rate limiting rejects with 503 by default** (`RateLimiterOptions.RejectionStatusCode`). Set 429 explicitly.
- **Invalid requests still use up rate-limit permits**: the limiter runs before model validation, so three 400s
  then a valid claim gave 429 (test `Invalid_submits_also_count_against_the_limit`).
- **The limit is per app instance.** Learn notes the middleware's state is in-memory per instance; scale out to two
  instances and each enforces its own window.
- **`UseRateLimiter()` goes after `UseAuthentication()`** when the partition key is the user; otherwise every
  request lands in the `anonymous` partition.
- **No claim mapping surprises**: with `MapInboundClaims = false` the API reads `oid`, `sub` and `roles` exactly as they
  are in the JWT — the same names you see in the token.

## References
- [Create web APIs with ASP.NET Core (`[ApiController]` behaviours)](https://learn.microsoft.com/aspnet/core/web-api/)
- [Handle errors in ASP.NET Core APIs](https://learn.microsoft.com/aspnet/core/fundamentals/error-handling-api)
- [Handle errors in ASP.NET Core (`IExceptionHandler`, problem details service)](https://learn.microsoft.com/aspnet/core/fundamentals/error-handling)
- [Model validation in ASP.NET Core MVC](https://learn.microsoft.com/aspnet/core/mvc/models/validation)
- [Configure JWT bearer authentication in ASP.NET Core](https://learn.microsoft.com/aspnet/core/security/authentication/configure-jwt-bearer-authentication)
- [Manage JSON Web Tokens in development with dotnet user-jwts](https://learn.microsoft.com/aspnet/core/security/authentication/jwt-authn)
- [Rate limiting middleware in ASP.NET Core](https://learn.microsoft.com/aspnet/core/performance/rate-limit)
- [`RateLimiterOptions.RejectionStatusCode` (default 503)](https://learn.microsoft.com/dotnet/api/microsoft.aspnetcore.ratelimiting.ratelimiteroptions.rejectionstatuscode)
- [Generate OpenAPI documents](https://learn.microsoft.com/aspnet/core/fundamentals/openapi/aspnetcore-openapi)
- [Integration tests in ASP.NET Core](https://learn.microsoft.com/aspnet/core/test/integration-tests)
- [Configure an application to expose a web API](https://learn.microsoft.com/entra/identity-platform/quickstart-configure-app-expose-web-apis)
- [Add app roles and receive them in the token](https://learn.microsoft.com/entra/identity-platform/howto-add-app-roles-in-apps)
- [Access tokens: v1.0 is the default for Entra-only apps](https://learn.microsoft.com/entra/identity-platform/access-tokens)
- [Authorize Azure CLI as a client application (example)](https://learn.microsoft.com/azure/data-api-builder/concept/security/authenticate-entra)
- [Configure an ASP.NET Core app for App Service (`__` for nested settings)](https://learn.microsoft.com/azure/app-service/configure-language-dotnetcore)
- Blog: [ASP.NET Core Web APIs — Complete Guide](https://www.devladlog.com/articles/dotnet/2026-04-20-aspnet-core-web-apis-complete-guide-2026/)
