# DEVLADLOG Code #5 — Design patterns in practice (.NET 10 dependency injection)

The Contoso project requests from episodes 1-4 now get **routed to named approvers**. Instead of drawing UML, we build
four classic patterns with the tools every .NET app already has (`Microsoft.Extensions.DependencyInjection`, the
options pattern and the Generic Host), run them, and break them on purpose:

- **Strategy**: one `IApprovalRoute` class per route (`standard`, `high`, `board`). `RouteCatalog` receives every
  route as `IEnumerable<IApprovalRoute>`, so a new route is one class + one registration, and nothing asks the
  container for services at run time (no service locator). Choosing the key stays a plain function.
- **Decorator**: `Metered -> Caching -> JsonFile` approver directory. The inner layers are **keyed services**, so the
  only `IApproverDirectory` you can resolve without a key is the outer one: nobody can skip the cache by accident.
- **Observer**: `AuditObserver` (scoped), `OutboxObserver` (writes one notification file per request) and
  `BudgetTallyObserver` (singleton). They run in registration order; one failing observer doesn't stop the others.
- **Options pattern**: thresholds and due days come from `appsettings.json`, validated with data annotations and a
  cross-field rule, **at startup** (`ValidateOnStart`), not on first use.
- **The gotcha**: a "stateless" observer registered as a singleton captures a scoped `AuditTrail`. In the default
  Production environment it runs with no error and the audit trail stays empty; in Development the host refuses to build.

Same rules as the rest of the series: `>= 50,000` EUR is High (Manager, then Finance); `>= 250,000` goes to the
Board (Finance first, Board last) and needs a justification. All people are fictional (`Alex Demo`, `Sam Demo`, ...).

| Path | What it is |
|---|---|
| [`Directory.Build.props`](Directory.Build.props) | `net10.0`, nullable, warnings as errors, `latest-recommended` analyzers, code style in build |
| [`src/Contoso.Approvals.Patterns/Model.cs`](src/Contoso.Approvals.Patterns/Model.cs) | `ProjectRequest`, `RoutePlan`, `RequestRouted` (the event), `SubmitResult` |
| [`src/Contoso.Approvals.Patterns/Options.cs`](src/Contoso.Approvals.Patterns/Options.cs) | `ApprovalPolicyOptions`, `ApproverDirectoryOptions`, `OutboxOptions` with data annotations |
| [`src/Contoso.Approvals.Patterns/Routing/`](src/Contoso.Approvals.Patterns/Routing) | Strategy: `IApprovalRoute`, `StandardRoute`, `HighValueRoute`, `BoardRoute`, `RouteKeys.For`, `RouteCatalog` |
| [`src/Contoso.Approvals.Patterns/Approvers/`](src/Contoso.Approvals.Patterns/Approvers) | Decorator: `IApproverDirectory`, `JsonFileApproverDirectory`, `CachingApproverDirectory` (`TimeProvider`), `MeteredApproverDirectory`, `DirectoryStats` |
| [`src/Contoso.Approvals.Patterns/Events/Observers.cs`](src/Contoso.Approvals.Patterns/Events/Observers.cs) | Observer: `IRequestObserver`, `AuditTrail` + `AuditObserver`, `OutboxObserver`, `BudgetTally` + `BudgetTallyObserver` |
| [`src/Contoso.Approvals.Patterns/ApprovalService.cs`](src/Contoso.Approvals.Patterns/ApprovalService.cs) | The client of all three patterns; publishes to every observer, isolates failures |
| [`src/Contoso.Approvals.Patterns/ServiceCollectionExtensions.cs`](src/Contoso.Approvals.Patterns/ServiceCollectionExtensions.cs) | The composition root: `AddApprovals`, `AddApprovalCore`, `AddRequestObservers` |
| [`src/Contoso.Approvals.Patterns.Cli/`](src/Contoso.Approvals.Patterns.Cli) | Generic Host console app used in the video; `Mistakes.cs` is the captive-dependency registration (wrong on purpose) |
| [`samples/requests.json`](samples/requests.json) / [`samples/approvers.json`](samples/approvers.json) | 8 fictional requests in 2 batches / approvers per department |
| [`tests/Contoso.Approvals.Patterns.Tests/`](tests/Contoso.Approvals.Patterns.Tests) | 27 xUnit tests: route boundaries, decorator order and expiry (`FakeTimeProvider`), observer order and isolation, keyed resolution, options validation, the captive dependency in Production vs Development |
| [`demo/run-all.sh`](demo/run-all.sh) | Runs the four CLI modes from the video and checks each result |
| [`demo/expected-output.txt`](demo/expected-output.txt) | Real output of the tests, the four modes and one outbox file |

## Build, test, run

```bash
dotnet test DesignPatterns.slnx -m:1                       # Passed: 27, Failed: 0 (~1 s)
dotnet run --project src/Contoso.Approvals.Patterns.Cli    # 2 batches, 8 requests, writes ./outbox/PR-*.txt
dotnet run --project src/Contoso.Approvals.Patterns.Cli -- --Policy:BoardThreshold=10000      # exit 1 at startup
dotnet run --project src/Contoso.Approvals.Patterns.Cli -- --Demo:CaptiveAudit=true            # runs, audit trail empty
dotnet run --project src/Contoso.Approvals.Patterns.Cli -- --Demo:CaptiveAudit=true --environment Development  # refuses to build
./demo/run-all.sh                                          # all four, with ok/FAIL checks (exit 0)
```

Tested here with .NET SDK 10.0.115 on Linux, `Microsoft.Extensions.Hosting` / `DependencyInjection` /
`Options.DataAnnotations` 10.0.15, 5 consecutive green runs. No cloud resources, no database: the "slow" source is a
JSON file read on every lookup. `outbox/` is git-ignored.

## What we learned / gotchas

- **A captive dependency is silent in Production.** `AuditObserver` looks stateless, so someone registers it as a
  singleton. It holds the scoped `AuditTrail` it got first (from the root provider) forever. With the default
  environment (Production, because nothing sets `DOTNET_ENVIRONMENT`) the CLI ran with exit code 0 and both batches
  reported `0 entries [MISSING, expected 4]`. With `--environment Development`, `Build()` threw an
  `AggregateException`: *"Cannot consume scoped service '...AuditTrail' from singleton '...IRequestObserver'"*.
  Learn: scope validation is on in Development only. Our tests build the provider with
  `ValidateScopes = true, ValidateOnBuild = true` so the mistake fails in CI regardless of environment.
- **Resolving one service when several are registered gives you the last one, silently.**
  `GetRequiredService<IRequestObserver>()` returned `BudgetTallyObserver`; `IEnumerable<IRequestObserver>` returned
  all three in registration order (Learn: service registration). Observers must be consumed as a collection.
- **`ValidateOnStart` only runs when the host starts.** With a plain `BuildServiceProvider()` (no host), the impossible
  policy built fine and threw `OptionsValidationException` on the first `.Value`. The CLI calls `host.StartAsync()`.
- **The host logs the startup failure itself.** With `Logging:LogLevel:Default = Warning`, the Generic Host still
  wrote `fail: ...Host[11] Hosting failed to start` plus the stack trace before our own message. We left it: it's
  what production logs will show.
- **Decorator order changes what you measure.** Metered outside the cache counted 3 of 3 calls; inside it counted 1
  (only misses). Pinned by `Decorator_order_changes_what_you_measure`.
- **Our cache only hit 3 of 13 times on the samples**, because the key is (department, role) and the 8 requests
  cover 4 departments. That's the honest number; the expiry behaviour is tested with `FakeTimeProvider`.
- **A namespace called `Directory` breaks `Directory.Exists`.** Our first folder/namespace `...Patterns.Directory`
  made every `Directory.*` call in the tests resolve to our namespace (CS0234). Renamed to `...Patterns.Approvers`.
- **Content root is the current folder.** `Host.CreateApplicationBuilder` sets `ContentRootPath` to the current
  directory (Learn), and `appsettings.json` is loaded from there, not from the build output. Because we run the CLI
  from the episode folder, it sets `ContentRootPath = AppContext.BaseDirectory`; `samples/` paths stay relative to
  where you run it.
- **Not everything needs a pattern.** Choosing the route key is one expression (`RouteKeys.For`); the strategies earn
  their place because each route has its own roles, due days and rules (the Board's justification warning).

## References
- [.NET dependency injection (keyed services, scope validation)](https://learn.microsoft.com/dotnet/core/extensions/dependency-injection/overview)
- [Service registration (multiple implementations, `IEnumerable<T>`, last registration wins, `TryAdd*`)](https://learn.microsoft.com/dotnet/core/extensions/dependency-injection/service-registration)
- [Dependency injection guidelines (captive dependency, avoid service locator, keep factories fast and synchronous)](https://learn.microsoft.com/dotnet/core/extensions/dependency-injection/guidelines)
- [Service lifetimes (scoped from singleton)](https://learn.microsoft.com/dotnet/core/extensions/dependency-injection/service-lifetimes)
- [Options pattern in .NET (validation, `ValidateOnStart`)](https://learn.microsoft.com/dotnet/core/extensions/options)
- [`Host.CreateApplicationBuilder` (defaults: content root, scope validation in Development)](https://learn.microsoft.com/dotnet/api/microsoft.extensions.hosting.host.createapplicationbuilder)
- [Runtime environments (Production is the default; `DOTNET_ENVIRONMENT` for console apps)](https://learn.microsoft.com/aspnet/core/fundamentals/environments)
- [`ServiceProviderOptions.ValidateScopes`](https://learn.microsoft.com/dotnet/api/microsoft.extensions.dependencyinjection.serviceprovideroptions.validatescopes)
- Blog: [Design Patterns in Practice — Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-06-28-design-patterns-in-practice-complete-guide-2025/)
