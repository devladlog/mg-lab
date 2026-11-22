# DEVLADLOG .NET #4 — Dependency injection on .NET 10: lifetimes, captive dependencies, keyed services, options

Episode 3's project requests API (EF Core 10, SQLite locally) gets a feature that needs every part of the built-in
container: a **daily digest of requests still waiting for a decision**, sent by a background worker to a channel
chosen in configuration. Along the way:

- **Lifetimes you can see**: `GET /diagnostics/lifetimes` (Development only) shows transient, scoped and singleton
  probes — and the `DbContext` — from the endpoint and from a scoped consumer, request after request.
- **The captive dependency, three ways**: a singleton that takes the scoped `RequestsDbContext` in its constructor is
  rejected by scope validation (`ValidateScopes` + `ValidateOnBuild`), refuses to start in **Development**, and in
  **Production** starts fine and then **serves stale data** from a `DbContext` that never dies. All three are tests.
- **A `BackgroundService` done right**: the worker is a singleton, so it takes `IServiceScopeFactory` and creates
  **one async scope (one DbContext) per run**; `IOptionsMonitor` instead of the scoped `IOptionsSnapshot`;
  `PeriodicTimer` on an injected `TimeProvider`; one failed send is logged instead of stopping the host.
- **Keyed services** (.NET 8+): `INotificationChannel` has a `"log"` and a `"webhook"` implementation; a scoped factory
  registration resolves whichever key `Notifications:Channel` names. The webhook channel is a **typed `HttpClient`**.
- **Options that fail fast**: `NotificationOptions` is validated with data annotations (`[AllowedValues]`, `[Range]`)
  plus `IValidatableObject`, and **`ValidateOnStart()`** — a webhook channel without an https URL stops the app at
  startup, with the reason in the log.
- **Tests that swap services, not code**: `ConfigureTestServices` replaces `TimeProvider` with `FakeTimeProvider`,
  the `"log"` channel with a recording one, and the webhook's primary handler with a capturing one.

| Path | What it is |
|---|---|
| [`src/ProjectRequests.Api/Program.cs`](src/ProjectRequests.Api/Program.cs) | Composition root: one `Add…` extension per feature, Development-only diagnostics |
| [`src/ProjectRequests.Api/Notifications/NotificationsSetup.cs`](src/ProjectRequests.Api/Notifications/NotificationsSetup.cs) | Options + `ValidateOnStart`, keyed channels, typed `HttpClient`, the worker as singleton + hosted service, `POST /api/digest/send` |
| [`src/ProjectRequests.Api/Notifications/DigestWorker.cs`](src/ProjectRequests.Api/Notifications/DigestWorker.cs) | `BackgroundService`: `PeriodicTimer(interval, TimeProvider)`, `CreateAsyncScope()` per run, catch-and-log |
| [`src/ProjectRequests.Api/Notifications/PendingDigest.cs`](src/ProjectRequests.Api/Notifications/PendingDigest.cs) | Scoped `PendingDigestBuilder` (DbContext + `IOptionsSnapshot`): grouped EF Core query |
| [`src/ProjectRequests.Api/Notifications/Channels.cs`](src/ProjectRequests.Api/Notifications/Channels.cs) | `INotificationChannel`, `LogNotificationChannel`, `WebhookNotificationChannel` (typed client) |
| [`src/ProjectRequests.Api/Notifications/NotificationOptions.cs`](src/ProjectRequests.Api/Notifications/NotificationOptions.cs) | Options class with annotations and a cross-field rule |
| [`src/ProjectRequests.Api/Diagnostics/Lifetimes.cs`](src/ProjectRequests.Api/Diagnostics/Lifetimes.cs) | Transient/scoped/singleton probes, `ProbeConsumer`, `GET /diagnostics/lifetimes` |
| `src/ProjectRequests.Api/Data`, `Requests`, `Migrations` | Unchanged from [episode 3](../03-entity-framework-core/) |
| [`tests/ProjectRequests.Api.Tests/LifetimeTests.cs`](tests/ProjectRequests.Api.Tests/LifetimeTests.cs) | 5 tests: lifetimes over HTTP, scope validation message, Development refuses to start, Production stale data, `AddDbContext` is scoped |
| [`tests/ProjectRequests.Api.Tests/NotificationTests.cs`](tests/ProjectRequests.Api.Tests/NotificationTests.cs) | 8 tests: startup validation (2), key → channel (2), webhook via `IHttpClientFactory`, worker on `FakeTimeProvider`, worker survives a failed send, worker = hosted service |
| `tests/…/ApiTests.cs`, `DataTests.cs`, `ConfigurationTests.cs` | Episode 3's 26 tests, still green |
| [`deploy/local-demo.sh`](deploy/local-demo.sh) / [`deploy/local-demo.output.txt`](deploy/local-demo.output.txt) | Lifetimes, two requests, send the digest now — and its real output |
| [`deploy/startup-validation.output.txt`](deploy/startup-validation.output.txt) | Real output of `Notifications__Channel=webhook dotnet run`: `OptionsValidationException`, exit code 134 on Linux (-532462766, 0xE0434352, on Windows) |
| [`deploy/deploy-appservice.sh`](deploy/deploy-appservice.sh) | F1 Linux web app with SQLite in `/home`; `break` / `fix` phases for the ValidateOnStart demo |

## Build, test, run

```bash
dotnet tool restore
dotnet test -m:1                         # Passed: 39, Failed: 0 (13 new + episode 3's 26), ~4 s

cd src/ProjectRequests.Api
dotnet dotnet-ef database update --context SqliteRequestsDbContext
dotnet run --launch-profile http         # Development: digest every minute, StaleAfterDays 0 (all pending requests)
cd ../.. && ./deploy/local-demo.sh       # lifetimes x2, two requests, POST /api/digest/send

cd src/ProjectRequests.Api && Notifications__Channel=webhook dotnet run   # refuses to start: OptionsValidationException
```

Tested with .NET SDK 10.0.115 / runtime 10.0.15, EF Core 10.0.15, Microsoft.Extensions.TimeProvider.Testing 10.11.1.
No third-party container: everything here is `Microsoft.Extensions.DependencyInjection`.

## Deploy to Azure App Service (needs a subscription)

```bash
PACKAGE_ONLY=1 ./deploy/deploy-appservice.sh               # verified here: 18 MB zip; Production: /healthz Healthy,
                                                           # /diagnostics/lifetimes 404, POST /api/digest/send 200
az login
APP=contoso-requests-<n> ./deploy/deploy-appservice.sh     # F1 Linux, SQLite in /home, log channel, 1-minute digest
APP=contoso-requests-<n> ./deploy/deploy-appservice.sh break   # webhook without URL -> app refuses to start
APP=contoso-requests-<n> ./deploy/deploy-appservice.sh fix
az group delete --name rg-mglab-net04 --yes
```

SQLite in `/home` keeps this episode about DI; it's a demo choice for one F1 instance, not a recommendation —
episode 3 is the production path (Azure SQL, managed identity). The Azure steps were **not run in this container**.

## What we learned / gotchas

- **In Production a captive dependency doesn't fail — it lies.** With `ValidateScopes`/`ValidateOnBuild` (on by
  default only in Development since .NET 9) the host refuses to build. In Production the same registration starts,
  the singleton keeps the first `DbContext` forever, and after an approval through the API it still returned
  `Submitted`: its change tracker hands back the instance it already tracks (identity resolution). Test:
  `Production_host_starts_anyway_and_the_captive_DbContext_serves_stale_data`. If you can afford it, turn validation
  on everywhere with `UseDefaultServiceProvider`.
- **`IOptionsSnapshot` is scoped** too, so it's another way to build a captive dependency. The singleton worker uses
  `IOptionsMonitor`; the scoped digest builder uses `IOptionsSnapshot`.
- **`OrderBy` after a constructor projection can't be translated.** Our first digest query ended with
  `.Select(g => new DigestLine(...)).OrderBy(l => l.Department)` and EF Core threw "could not be translated" — it
  can't map a constructor parameter back to the property. Ordering by `g.Key` *before* the `Select` fixed it.
- **`FakeTimeProvider.Advance` fires a periodic timer once per elapsed period.** Advancing 4 days on a 1-day
  `PeriodicTimer` produced 4 digests, not 1. The tests use a 4-day interval and advance exactly one interval.
- **Development settings leak into tests.** `WebApplicationFactory` runs in Development, so `appsettings.Development.json`
  (`StaleAfterDays: 0`) applied and a brand-new request showed up as "stale". The factory now pins
  `Notifications:StaleAfterDays=3` and a 4-day interval so the real clock never fires the worker during a test.
- **A `BackgroundService` exception stops the host** (`BackgroundServiceExceptionBehavior.StopHost`, the default since
  .NET 6). One failed webhook call must not take the API down, so each run is wrapped in try/catch-and-log. We removed
  the catch to check: the "survives a failed send" test fails.
- **`ValidateOnStart` turns a 3 a.m. surprise into a failed deploy.** Without it, a missing `WebhookUrl` would only
  surface when the first digest runs (or the first time someone reads the options). With it, `dotnet run` exits with
  code 134 on Linux (-532462766 on Windows) and the exact message (`deploy/startup-validation.output.txt`).
- **Keyed + typed `HttpClient`**: typed clients are transient and `IHttpClientFactory` manages the handler under them,
  so the `"webhook"` key is registered as a transient factory over the typed client, resolved inside a scope —
  never captured by the singleton worker.
- **The last registration wins**, keyed or not (Learn documents it for `GetKeyedService`). That's what lets
  `ConfigureTestServices` replace the `"log"` channel or `TimeProvider` without touching `Program.cs`.
- **When to bring a third-party container**: Learn recommends the built-in one unless you need property injection,
  child containers, custom lifetime management, `Func<T>` lazy initialization or convention-based registration. This
  episode needed none of them.

## References
- [Dependency injection in .NET: keyed services, scope validation](https://learn.microsoft.com/dotnet/core/extensions/dependency-injection/overview)
- [Service lifetimes (scoped, AddDbContext is scoped)](https://learn.microsoft.com/dotnet/core/extensions/dependency-injection/service-lifetimes)
- [Dependency injection guidelines (captive dependency, disposal, replacing the container)](https://learn.microsoft.com/dotnet/core/extensions/dependency-injection-guidelines)
- [Dependency injection in ASP.NET Core](https://learn.microsoft.com/aspnet/core/fundamentals/dependency-injection)
- [Minimal APIs: ValidateScopes and ValidateOnBuild in Development](https://learn.microsoft.com/aspnet/core/fundamentals/minimal-apis#validatescopes-and-validateonbuild)
- [Breaking change (.NET 9): HostBuilder enables ValidateOnBuild/ValidateScopes in Development](https://learn.microsoft.com/aspnet/core/breaking-changes/9/hostbuilder-validation)
- [Options pattern in ASP.NET Core (validation, ValidateOnStart, IOptionsSnapshot vs IOptionsMonitor)](https://learn.microsoft.com/aspnet/core/fundamentals/configuration/options)
- [Use scoped services within a BackgroundService](https://learn.microsoft.com/dotnet/core/extensions/scoped-service)
- [Background tasks with hosted services in ASP.NET Core](https://learn.microsoft.com/aspnet/core/fundamentals/host/hosted-services)
- [Unhandled exceptions from a BackgroundService stop the host (.NET 6)](https://learn.microsoft.com/dotnet/core/compatibility/core-libraries/6.0/hosting-exception-handling)
- [IHttpClientFactory: typed clients are transient; avoid typed clients in singletons](https://learn.microsoft.com/dotnet/core/extensions/httpclient-factory)
- [`AddKeyedSingleton` (last registration wins)](https://learn.microsoft.com/dotnet/api/microsoft.extensions.dependencyinjection.servicecollectionserviceextensions.addkeyedsingleton)
- [Tracking vs. no-tracking queries / identity resolution](https://learn.microsoft.com/ef/core/change-tracking/identity-resolution)
- [Configure an ASP.NET Core app for App Service (log stream)](https://learn.microsoft.com/azure/app-service/configure-language-dotnetcore)
- [App Service environment variables (`HOME` = shared storage `/home`)](https://learn.microsoft.com/azure/app-service/reference-app-settings)
- Blog: [Dependency Injection & DI Containers — Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-08-dependency-injection-di-containers-complete-guide-2026/)
