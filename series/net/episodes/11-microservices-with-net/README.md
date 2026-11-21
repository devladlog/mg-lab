# DEVLADLOG .NET #11 — Microservices with .NET: split a service, then break it on purpose (.NET 10)

Same fictional scenario as the earlier episodes (`contoso`, `alex.demo`, departments FIN / IT / OPS). This episode takes the
**budget check** out of the project requests API and makes it a service of its own, puts a **gateway** in front, and then
stops that service on camera to see what the callers do. Each episode folder is self-contained: this is a new, smaller
solution (it does not copy the Blazor / SignalR / gRPC parts of episodes 6-8).

| Service | Port | What it owns |
|---|---|---|
| **Contoso.Gateway** | 5311 | One front door. YARP routes `/api/requests/**` and `/api/budgets/**` to the services by *name*; `/health/services` shows what answers |
| **Contoso.Requests.Service** | 5312 | The requests (EF Core + SQLite file). On `POST /api/requests` it saves the request as `Pending`, asks Budget, and ends as `Reserved`, `Declined` or (Budget unreachable) still `Pending` with `202 Accepted`. A background worker finishes pending requests later |
| **Contoso.Budget.Service** | 5313 | The department limits and the reservations (in memory: this service's private data). Reservations are stored under the caller's `Idempotency-Key` |
| **Contoso.ServiceDefaults** | - | Shared by all: service discovery, the standard resilience handler with one extra rule, `/alive` + `/health`, trace ids in log lines. The same idea as the Aspire "ServiceDefaults" project, without needing Aspire |

| Path | What it is |
|---|---|
| [`src/Contoso.ServiceDefaults/`](src/Contoso.ServiceDefaults/) | `ServiceDefaults.cs` (`AddServiceDefaults`, `MapDefaultEndpoints`), `RetryPolicy.cs` (retry writes only with an idempotency key) |
| [`src/Contoso.Budget.Service/`](src/Contoso.Budget.Service/) | `BudgetLedger.cs` (limits, reservations, idempotency, one lock), `Faults.cs` (demo-only fault injection, off by default), `Program.cs` |
| [`src/Contoso.Requests.Service/`](src/Contoso.Requests.Service/) | `Budget/BudgetClient.cs` (the only code that knows Budget exists), `Requests/RequestEndpoints.cs`, `Requests/BudgetRechecker.cs` (worker), `Data/RequestsDb.cs`, `Program.cs` (resilience tuning from configuration) |
| [`src/Contoso.Gateway/`](src/Contoso.Gateway/) | `appsettings.json` (YARP routes and clusters), `DownstreamHealth.cs`, `Program.cs` |
| [`tests/Contoso.Microservices.Tests/`](tests/Contoso.Microservices.Tests/) | 30 tests (below). `Lab.cs` starts the real Budget and Requests services in memory and wires the Budget `HttpClient` to the real Budget service |
| [`deploy/smoke.ps1`](deploy/smoke.ps1) / [`deploy/smoke.output.txt`](deploy/smoke.output.txt) | Starts the **three real processes** on real Kestrel and checks the whole story through the gateway (17 checks); its real output |
| [`deploy/tests.output.txt`](deploy/tests.output.txt) | Real output of `dotnet test` |

## Build, test, run

```bash
dotnet test                       # total: 30, failed: 0, succeeded: 30 (about 25 s on an idle machine, 60 s on the shared one)
dotnet build Contoso.Microservices.slnx
pwsh ./deploy/smoke.ps1           # three real processes, 17 checks, about 90 s (waits for the circuit and the re-check worker)

# by hand, three terminals (Development environment; ports are in launchSettings.json)
cd src/Contoso.Budget.Service   && dotnet run --launch-profile http
cd src/Contoso.Requests.Service && dotnet run --launch-profile http     # creates requests.db on start
cd src/Contoso.Gateway          && dotnet run --launch-profile http
curl -X POST http://localhost:5311/api/requests -H "Content-Type: application/json" -d '{"title":"Standing desks","departmentCode":"FIN","amount":12000,"requestedBy":"alex.demo@contoso.com"}'
```

What the 30 tests cover (`dotnet test`, xUnit v3 on Microsoft.Testing.Platform, as in episodes 5-8):

- **Budget service (9):** reserve within the limit; over the limit is 422; missing or invalid `Idempotency-Key` is 400; the same key returns
  the first answer and reserves once; the same key for a different reservation is 409; unknown department / bad amount; **fifty parallel
  reservations never exceed the limit** (exactly 20 of 1,000 against OPS's 20,000); a **lost answer** (reservation made, response 503, twice)
  reserves once when the retry carries the same key.
- **Requests service (13):** reserve through the real Budget service; declined when over budget; transient 503s retried (3 attempts);
  **lost answers retried without reserving twice**; Budget down gives `202 Pending` and the service stays healthy; the **circuit opens** and
  the second call never touches the wire; the **circuit closes again** after the break duration; the re-check finishes pending requests;
  same `Idempotency-Key` creates one request; eight parallel posts with one key create one request; validation and 404; trace id stored; `/alive` and `/health`.
- **Retry rule (3):** a `GET` is retried three times, a `POST` without a key is tried once, a `POST` with a key is retried.
- **Gateway (5):** both routes reach their services (service discovery turns the names into the addresses in `appsettings.json`); the list
  route without a trailing path matches; unknown path is 404; a service that is down gives 502 on its route while the other route still works; `/health/services` is `Healthy`, then `Degraded` (still HTTP 200) when one service is down.
- The only fake in the tests is the **network** between the services (`Lab.cs`: a counting handler that can pretend the service is down; `PortRouter` for the gateway).

Verified in the container (SDK 10.0.115, ASP.NET Core 10.0.15, Yarp.ReverseProxy 2.3.0, Microsoft.Extensions.Http.Resilience / ServiceDiscovery /
ServiceDiscovery.Yarp 10.11.1, EF Core SQLite 10.0.15): `dotnet test` 30/0/0; `deploy/smoke.ps1` all 17 checks on three real Kestrel processes, including
stopping and restarting the Budget service, the re-check worker, a lost answer, and **one trace id found in the logs of all three processes**.
**Not done / not verified here:** Windows (the commands are written for it, but the container is Linux), any message broker (the services call
each other directly, so they are still coupled in time), authentication, containers / Kubernetes / Azure hosting, the Aspire AppHost and dashboard.
No Azure resources are needed (cost: nothing).

## What we learned / gotchas

- **Each microservice owns its data.** Learn (architecture guide): the data is private to the service and reached only through its API or by
  messaging, so schema changes don't ripple. Requests never reads budget numbers; it asks. The price (also Learn): no single transaction across
  services, so the whole flow lives with eventual consistency: a request can be `Pending` for a while.
- **The standard resilience handler retries every HTTP method.** Learn says so, and that a retried POST can duplicate data. `ServiceDefaults` keeps
  the handler but wraps its `ShouldHandle`: retry when the failure is transient *and* the call is a read or carries an `Idempotency-Key`
  (`DisableForUnsafeHttpMethods()` from Learn would have turned writes off completely). The header name is our own convention here, the platform does not define it.
- **Idempotency is what makes the retry safe, and the test proves it.** With fault injection the Budget service can *make* the reservation and
  then lose the answer. A retry without a key would reserve again; with the key it gets the first reservation back (`Lost_answers_are_retried_without_reserving_twice`: 12,000 reserved, not 36,000).
- **Defaults for a laptop.** The standard handler's circuit breaker needs 100 calls in 30 s (Learn: minimum throughput 100, sampling 30 s, failure ratio 10 %,
  break 5 s) and the retry delay is 2 s, so nothing visible happens in a demo. `Requests.Service/Program.cs` tunes it from `appsettings.json`
  (`Resilience:*`: 3 retries 300 ms apart, attempt timeout 2 s, breaker after 5 calls, break 15 s). Without that the circuit never opens.
- **A service that is back is not called again until the circuit lets a probe through.** `The_circuit_lets_a_probe_through_after_the_break...` shows it,
  and so did the real run (the re-check worker took about 13 s after Budget was restarted).
- **`RemoveAllResilienceHandlers` is experimental** (`EXTEXP0001`, and Learn lists it as such). The gateway's health probe must not retry, so
  it removes the default handler with a `#pragma warning disable EXTEXP0001`.
- **Readiness is about *your* dependencies.** `/health` on Requests checks its database only (`AddDbContextCheck`); the Budget service is deliberately not in it,
  or an outage in Budget would make orchestrators pull Requests out of rotation as well. Learn: liveness = the process runs, readiness = it can take traffic. The gateway's
  `/health/services` reports a down service as `Degraded`, which is HTTP 200 with the default status codes (Learn: `Degraded` returns 200).
- **YARP answers 502 when a destination can't be reached**; an unknown path never reaches a cluster (404). `/api/requests/{**catch-all}` also matches `/api/requests` itself (tested).
- **Service discovery for YARP.** `AddServiceDiscoveryDestinationResolver()` (package `Microsoft.Extensions.ServiceDiscovery.Yarp`) lets the YARP config say `http://requests/`.
  It worked here; I did not find it on the Learn pages I read, so treat the package as "seen working", not "Learn-verified".
- **Save first, ask second.** Creating the request as `Pending` before calling Budget means an outage never loses a request; the worker finishes it with the *same* key.
- **Three `Program` classes can't all be public.** Each service has top-level statements; the test project references all three, so each service exposes a
  differently named marker class (`BudgetServiceMarker` ...) for `WebApplicationFactory`.
- **Logs.** The `HttpClient` category logs two lines per call at Information, which drowned the demo; set to `Warning`. Polly's retry / circuit events are logged
  at Warning/Error and are the interesting lines. `ActivityTrackingOptions.TraceId | SpanId` plus `IncludeScopes` puts the trace id on every line; the W3C
  trace context flows through `HttpClient` and YARP without any code of ours (visible in the smoke run). The in-memory tests don't exercise that (no real HTTP handler).
- **Cold start.** On the busy shared container the very first request took 12 s (JIT); warm the services up before recording.
- `dotnet test -m:1` doesn't work with Microsoft.Testing.Platform (`Unknown option '--m'`); use `dotnet build -m:1` first if the machine is busy.

## References

- Microservices architecture: <https://learn.microsoft.com/dotnet/architecture/microservices/architect-microservice-container-applications/microservices-architecture>
- Data sovereignty per microservice: <https://learn.microsoft.com/dotnet/architecture/microservices/architect-microservice-container-applications/data-sovereignty-per-microservice>
- Build resilient HTTP apps (standard handler, defaults, retries for HTTP methods, `RemoveAllResilienceHandlers`): <https://learn.microsoft.com/dotnet/core/resilience/http-resilience>
- Service discovery in .NET: <https://learn.microsoft.com/dotnet/core/extensions/service-discovery>
- Get started with YARP / configuration files: <https://learn.microsoft.com/aspnet/core/fundamentals/servers/yarp/getting-started>, <https://learn.microsoft.com/aspnet/core/fundamentals/servers/yarp/config-files>
- Health checks in ASP.NET Core (liveness / readiness, `Degraded`): <https://learn.microsoft.com/aspnet/core/host-and-deploy/health-checks>
- Blog Complete Guide: <https://www.devladlog.com/articles/dotnet/2026-05-30-microservices-with-net-complete-guide-2026/>
