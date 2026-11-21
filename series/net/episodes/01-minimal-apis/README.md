# DEVLADLOG .NET #1 — Minimal APIs on .NET 10, tested and on App Service

A small but production-shaped **project requests API** built with ASP.NET Core Minimal APIs on **.NET 10 (LTS)**:

- **Route groups** (`MapGroup`) with the endpoints in their own static class, not a 300-line `Program.cs`
- **`TypedResults` + `Results<...>`** union return types: compile-time checked, unit-testable, and they feed OpenAPI
- **Built-in validation** (`AddValidation`, new in .NET 10): DataAnnotations plus a cross-field rule in `IValidatableObject`
- **Problem details** everywhere (`AddProblemDetails`, `UseExceptionHandler`, `UseStatusCodePages`)
- An **endpoint filter** on the write endpoints: read-only (maintenance) mode, switched by configuration
- **OpenAPI 3.1** document (`AddOpenApi` / `MapOpenApi`), Development only, with every status code described
- **Health endpoint** and a deploy script for **Azure App Service (Linux, Free F1)**

Business rules (same family as the MG Lab episodes): budget `>= 50,000` is High priority, `>= 250,000` needs a
justification, and you can't approve your own request.

| Path | What it is |
|---|---|
| [`src/ProjectRequests.Api/Program.cs`](src/ProjectRequests.Api/Program.cs) | Host: services, middleware, OpenAPI, health, `MapRequestsApi()` |
| [`src/ProjectRequests.Api/Requests/RequestEndpoints.cs`](src/ProjectRequests.Api/Requests/RequestEndpoints.cs) | Route group, handlers returning `TypedResults`, OpenAPI metadata |
| [`src/ProjectRequests.Api/Requests/ProjectRequest.cs`](src/ProjectRequests.Api/Requests/ProjectRequest.cs) | Models and request DTOs with validation attributes + `IValidatableObject` |
| [`src/ProjectRequests.Api/Requests/PriorityRules.cs`](src/ProjectRequests.Api/Requests/PriorityRules.cs) | Pure business rules (thresholds) |
| [`src/ProjectRequests.Api/Requests/ReadOnlyModeFilter.cs`](src/ProjectRequests.Api/Requests/ReadOnlyModeFilter.cs) | `IEndpointFilter`: 503 + `Retry-After` on writes when `Api:ReadOnly` is true |
| [`src/ProjectRequests.Api/Requests/RequestStore.cs`](src/ProjectRequests.Api/Requests/RequestStore.cs) | In-memory store (singleton, optimistic update). EF Core comes in episode 3 |
| [`tests/ProjectRequests.Api.Tests/HandlerTests.cs`](tests/ProjectRequests.Api.Tests/HandlerTests.cs) | 10 unit tests: handlers called directly, asserting on `TypedResults` types |
| [`tests/ProjectRequests.Api.Tests/ApiTests.cs`](tests/ProjectRequests.Api.Tests/ApiTests.cs) | 12 integration tests with `WebApplicationFactory<Program>` (validation, filter, OpenAPI, 404/409) |
| [`deploy/deploy-appservice.sh`](deploy/deploy-appservice.sh) | `dotnet publish` + zip, then `az` resource group, F1 Linux plan, web app, zip deploy, health check |
| [`deploy/smoke.sh`](deploy/smoke.sh) | The demo walk-through with `curl` (400, 400, 201, 409, 200, 404, list) against any base URL |
| [`deploy/smoke-local.output.txt`](deploy/smoke-local.output.txt) | Real output of `smoke.sh` against the local API |

## Build, test, run

```bash
dotnet test -m:1                                   # Passed: 22, Failed: 0 (10 unit + 12 integration), ~1 s
dotnet run --project src/ProjectRequests.Api       # http://localhost:5207 (Development: /openapi/v1.json)
./deploy/smoke.sh http://localhost:5207            # the walk-through from the video
Api__ReadOnly=true dotnet run --project src/ProjectRequests.Api   # writes -> 503, reads still 200
```

Tested here with .NET SDK 10.0.115 / ASP.NET Core runtime 10.0.15 on Linux. No database or container needed.

## Deploy to Azure App Service (needs a subscription)

```bash
PACKAGE_ONLY=1 ./deploy/deploy-appservice.sh       # publish + zip only (verified locally: 368 KB zip, runs)
az login
APP=contoso-requests-<unique> ./deploy/deploy-appservice.sh
./deploy/smoke.sh https://<app-host>
az webapp config appsettings set -g rg-mglab-net01 -n <app> --settings Api__ReadOnly=true
az group delete --name rg-mglab-net01 --yes       # tear down
```

The plan is **Free F1, Linux** (`--sku F1 --is-linux`, runtime `DOTNETCORE:10.0`), so the demo costs nothing.

## What we learned / gotchas

- **`dotnet add package Microsoft.AspNetCore.OpenApi` picked version 11.0.0** for our `net10.0` project (the day we
  built this, .NET 11 was already on NuGet). Restore succeeded, then the build failed with *`IServiceCollection` does
  not contain a definition for `AddOpenApi`* plus warning CS9057 (analyzer built for a newer compiler). The 11.0.0
  package only ships a `net11.0` library. Fix: pin the major version — `dotnet add package Microsoft.AspNetCore.OpenApi
  --version 10.0.15` (same for `Microsoft.AspNetCore.Mvc.Testing`).
- **The cross-field rule runs last.** `IValidatableObject.Validate` only runs when every attribute passed, so a body
  with a bad title *and* a missing justification first reports only the title. Documented on Learn ("class-level
  validation runs after property validation and only if property validation succeeds"); a test pins the behaviour.
- **`ProblemHttpResult` doesn't describe its status code in OpenAPI.** `Results<Ok<T>, NotFound>` documents 200 and
  404 automatically, but the 409 we return through `TypedResults.Problem(...)` was missing from `/openapi/v1.json`
  until we added `.ProducesProblem(409)`. Same for the 400 from validation and the 503 from the filter
  (`.ProducesValidationProblem()`, `.ProducesProblem(503)` on the group). A test checks the document.
- **No more `public partial class Program`.** In .NET 10 a source generator makes `Program` public, so
  `WebApplicationFactory<Program>` works out of the box.
- **Unknown JSON properties are silently ignored** by default (`UnmappedMemberHandling.Skip`), validation doesn't
  reject them. Set `JsonUnmappedMemberHandling.Disallow` if you need strict bodies.
- **Changing an App Service app setting restarts the app** (documented). With the in-memory store that means toggling
  read-only mode wipes the data: fine for a demo, and exactly why episode 3 moves to Entity Framework Core.
- **Linux app settings use `__` for nesting**: `Api:ReadOnly` becomes `Api__ReadOnly`.

## References
- [Minimal APIs quick reference](https://learn.microsoft.com/aspnet/core/fundamentals/minimal-apis)
- [Create responses in Minimal API apps (`TypedResults`, `Results<T1,TN>`)](https://learn.microsoft.com/aspnet/core/fundamentals/minimal-apis/responses)
- [Route handlers and route groups](https://learn.microsoft.com/aspnet/core/fundamentals/minimal-apis/route-handlers)
- [Filters in Minimal API apps](https://learn.microsoft.com/aspnet/core/fundamentals/minimal-apis/min-api-filters)
- [Validation in ASP.NET Core (`AddValidation`, `IValidatableObject`)](https://learn.microsoft.com/aspnet/core/fundamentals/validation)
- [What's new in ASP.NET Core in .NET 10 (validation, `Program` source generator)](https://learn.microsoft.com/aspnet/core/release-notes/aspnetcore-10.0)
- [Generate OpenAPI documents](https://learn.microsoft.com/aspnet/core/fundamentals/openapi/aspnetcore-openapi)
- [Unit and integration tests in Minimal API apps](https://learn.microsoft.com/aspnet/core/fundamentals/minimal-apis/test-min-api)
- [Quickstart: Deploy an ASP.NET web app to App Service (Azure CLI)](https://learn.microsoft.com/azure/app-service/quickstart-dotnetcore?pivots=development-environment-cli)
- [Configure an App Service app (app settings, restart, `__` on Linux)](https://learn.microsoft.com/azure/app-service/configure-common)
- Blog: [Minimal APIs — Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-05-minimal-apis-complete-guide-2026/)
