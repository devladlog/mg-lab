# DEVLADLOG .NET #8 — gRPC Services: a contract-first second front door for the project requests API (.NET 10)

Episodes 6 and 7 gave the API a Blazor app and a live board. This episode gives it a **second front door for programs**:
a gRPC service on its own port, defined by one `.proto` file, using the same database and the same validation as the REST
endpoints, plus a console client with deadlines and retries. Same fictional scenario as before (`contoso`, `alex.demo`,
departments FIN / IT / OPS).

| Piece | What it does |
|---|---|
| **`requests.proto`** (`ProjectRequests.Grpc`) | The contract, written first and compiled **once** (`GrpcServices="Both"`): messages, the service base class for the API and the client for the CLI. Three calls, one of each shape: `GetRequest` (unary), `ListRequests` (server streaming), `ImportRequests` (client streaming). `google.protobuf.StringValue` / `Timestamp` for "can be null"; enums with the mandatory zero value |
| **`DecimalValue`** (`ProjectRequests.Grpc`) | Protobuf has no `decimal`. `units` + `nanos` (the format Learn documents) with two implicit operators in a partial class. `RequestMapping` converts between the shared DTOs (REST, SignalR, Blazor) and the protobuf messages |
| **`RequestsGrpcService`** (API) | `GetRequest` → `NOT_FOUND` / `INVALID_ARGUMENT` as `RpcException`; `ListRequests` writes one message per row and filters by department; `ImportRequests` reads the stream, validates every row with the **same DataAnnotations model** as `POST /api/requests` and creates it through the **same `CreateCoreAsync`** (so the episode 7 SignalR push happens too). A bad row is reported with its position in `ImportReply.Errors` and does not stop the import. Every awaited call gets `context.CancellationToken` |
| **`CancellationStatusInterceptor`** (API) | A server interceptor (`AddGrpc(o => o.Interceptors.Add<…>())`): an `OperationCanceledException` caused by the call's own token becomes `DeadlineExceeded` (server deadline passed) or `Cancelled` (client went away), instead of `Unknown` |
| **Two Kestrel endpoints** (`appsettings.Development.json`) | `http://localhost:5207` HTTP/1 (REST + SignalR, unchanged) and `http://localhost:5208` **HTTP/2 only** (gRPC). Without TLS an HTTP/2 endpoint must be `Http2` only |
| **`ProjectRequests.Cli`** (`requests-cli`) | `get <id>`, `list [--department FIN]`, `import <file.csv>`; `--address`, `--deadline <seconds>`. `ChannelFactory` builds the channel once with a **retry policy for the two read methods only**; every call has a UTC deadline; `RpcException` → `gRPC error: NotFound - …` and exit code 2. `import` skips unparseable CSV lines on the client and maps the server's row numbers back to file line numbers |
| **Episode 7 stays** | The SignalR hub, `ProjectRequests.Feed`, the `/live` board and the FIN watcher are unchanged: a gRPC import shows up on the board |

| Path | What it is |
|---|---|
| [`src/ProjectRequests.Grpc/`](src/ProjectRequests.Grpc/) | `Protos/requests.proto`, `DecimalValue.cs`, `RequestMapping.cs` |
| [`src/ProjectRequests.Api/Rpc/`](src/ProjectRequests.Api/Rpc/) | `RequestsGrpcService.cs`, `CancellationStatusInterceptor.cs` |
| [`src/ProjectRequests.Api/Requests/RequestEndpoints.cs`](src/ProjectRequests.Api/Requests/RequestEndpoints.cs) | `Create` now calls the shared `CreateCoreAsync` |
| [`src/ProjectRequests.Api/Program.cs`](src/ProjectRequests.Api/Program.cs), [`appsettings.Development.json`](src/ProjectRequests.Api/appsettings.Development.json) | `AddGrpc`, `MapGrpcService`, the two endpoints |
| [`src/ProjectRequests.Cli/`](src/ProjectRequests.Cli/) | `Program.cs`, `Commands.cs`, `ChannelFactory.cs`, `CsvRows.cs`, `sample-import.csv` (7 lines: 3 good, 1 bad number, 3 rejected by the server) |
| [`tests/ProjectRequests.Api.Tests/GrpcServiceTests.cs`](tests/ProjectRequests.Api.Tests/GrpcServiceTests.cs) | 20 tests: a real gRPC client against the real service in memory (`GrpcTestKit.cs`) |
| [`tests/ProjectRequests.Api.Tests/CliTests.cs`](tests/ProjectRequests.Api.Tests/CliTests.cs) | 7 tests: CSV parsing, the three commands, and the retry policy against a handler that fakes `UNAVAILABLE` |
| [`tests/ProjectRequests.Api.Tests/CancellationStatusInterceptorTests.cs`](tests/ProjectRequests.Api.Tests/CancellationStatusInterceptorTests.cs) | 5 tests with a hand-made `ServerCallContext` |
| [`deploy/smoke.ps1`](deploy/smoke.ps1) / [`deploy/smoke.output.txt`](deploy/smoke.output.txt) | Runs the real CLI and the real SignalR watcher against the running API; its real output |
| [`deploy/tests.output.txt`](deploy/tests.output.txt) | Real output of `dotnet test` |

## Build, test, run

```bash
dotnet test                       # total: 133, failed: 0, succeeded: 132, skipped: 1 (~21 s)
                                  # Api.Tests 103 (71 from ep. 7 + 32 new), Web.Tests 30 (unchanged)
                                  # skipped = episode 5's opt-in SQL Server test

# terminals (REST/SignalR on 5207, gRPC on 5208; the Kestrel endpoints are in appsettings.Development.json)
cd src/ProjectRequests.Api && dotnet run --launch-profile http
cd src/ProjectRequests.Cli && dotnet run -- import sample-import.csv     # then: list | list --department FIN | get 2
pwsh ./deploy/smoke.ps1           # CLI + watcher + wrong-port + deadline against the running API (empty database)
```

Verified in the container (SDK 10.0.115, ASP.NET Core 10.0.15, Grpc.AspNetCore.Server / Grpc.Net.Client / Grpc.Tools 2.85.0,
Google.Protobuf 3.36.2): `dotnet test` 133/0/1; the API on **real Kestrel** (HTTP/2 without TLS on 5208) with the CLI doing
import / list / get; a SignalR watcher for FIN receiving only the FIN row of a gRPC import; the wrong-port and deadline
cases below; the API stopped and `get 1` giving `Unavailable` after about 1.6 s (three attempts with backoff).
`deploy/smoke.ps1` against the running API. **Not verifiable here (no browser):** the Blazor live board showing the
imported rows in a browser (episode 7's board is covered by bUnit tests, not yet seen in a browser). **Not done:** TLS
(development uses plain `http` on the HTTP/2-only port, as Learn describes; production needs TLS), gRPC-Web,
bidirectional streaming, authentication, Azure hosting.

## What we learned / gotchas

- **Plain `http` needs an HTTP/2-only endpoint.** Learn: an endpoint with several protocols (`Http1AndHttp2`, the default)
  can't be used without TLS because there is no negotiation; connections default to HTTP/1.1 and gRPC calls fail. So
  development has two ports. In the container we saw the other direction too: the CLI pointed at the HTTP/1 port gets
  `Internal - Error starting gRPC call. HttpRequestException: The HTTP/2 server closed the connection. HTTP/2 error code
  'HTTP_1_1_REQUIRED' (0xd)`; `curl --http1.1` to the gRPC port gets `400`; a plain HTTP/1.1 `POST` to a gRPC method path on
  the REST port gets `415` problem+json. `curl --http2-prior-knowledge http://localhost:5208/healthz` works: the REST
  health check is reachable over HTTP/2 on that port too.
- **gRPC errors are status codes, not HTTP codes.** `RpcException(new Status(StatusCode.NotFound, …))` on the server, a
  caught `RpcException` on the client (Learn: error handling). We used `NotFound`, `InvalidArgument`, `Unavailable`,
  `DeadlineExceeded`, `Cancelled`. Validation problems of the *import* are data (`ImportReply.Errors`), not a failed call.
- **Optional values.** A `string` field can't be `null` (it reads `""`), an unset `int32` reads `0`. `google.protobuf.StringValue`
  generates a nullable `string`, and a message-typed field (`Timestamp decided_at`) is `null` until set (Learn:
  Protobuf messages). Tests pin both: `Missing_optional_values_arrive_as_null_not_as_empty_strings`.
  The `department` filter uses `""` for "all" for the same reason.
- **Money is not a double.** `DecimalValue` (units + nanos, `sfixed32` nanos, same sign as units) from Learn. Nine decimal
  places at most, and other languages have to know the format (Learn says so). `12,345.67` travels as `12345` + `670000000`
  (`Decimal_budgets_survive_the_wire_without_rounding`).
- **Name clashes after code generation.** The generated `Requests` class collides with the namespace `ProjectRequests.Api.Requests`
  in the API's tests (`using RequestsClient = ProjectRequests.Grpc.Requests.RequestsClient;`), the generated enums `Priority` /
  `RequestStatus` collide with the Contracts enums of the same names, and `Grpc.Net.Client` can't be used as a namespace
  from inside `ProjectRequests.Grpc` without a `using`. The proto enum values `PRIORITY_HIGH` become `Priority.High` (prefix
  dropped, observed).
- **Deadlines: client first, server keeps going.** Learn: no default deadline; the client aborts and throws `DeadlineExceeded`,
  the server's `ServerCallContext.CancellationToken` fires but **the method keeps running** unless the awaited work takes the
  token. `A_deadline_stops_the_client_and_cancels_the_token_the_server_received`: the client fails after about 0.5 s while the
  slow server work (which ignores the token) runs for 2 s, and the token did fire. A past deadline fails immediately
  (`A_deadline_in_the_past_fails_immediately`).
- **A cancelled handler is `Unknown` unless you map it.** In our first run of that test (before the interceptor) the client got
  `Unknown: Exception was thrown by handler. TaskCanceledException` (in-memory server, Development): the
  `OperationCanceledException` raised by the cancelled token escaped the handler. `CancellationStatusInterceptor` maps it. Which side's
  status the client reports can depend on who noticed first, so the test asserts the client-side `DeadlineExceeded` for a
  server that never answers in time, and the interceptor is unit-tested on its own. The server can't tell "client deadline
  expired a few ms before mine" from "client cancelled", so that case is logged as `Cancelled`.
- **Retries: configure once, only what is safe to repeat.** Learn: retries are set in the channel's `ServiceConfig`
  (`MaxRetryAttempts` alone enables nothing); a call is retried only if the status matches, attempts remain, the call isn't
  *committed* (response headers received, or the buffer limit exceeded) and the deadline hasn't passed; the deadline counts
  across all attempts; server-streaming calls don't retry after the first message; retried calls carry
  `grpc-previous-rpc-attempts`. We retry `Unavailable` for `GetRequest` and `ListRequests` and **not** for `ImportRequests`
  (a retried import could create the rows twice). The tests use a `DelegatingHandler` that answers the first calls with a
  trailers-only `UNAVAILABLE` response and check 3 attempts with headers `[null, "1", "2"]`, the stop at `MaxAttempts`, and
  that import is attempted once. That handler exists only in the tests; the demo uses the real server.
- **`EnableDetailedErrors` leaks.** Learn: it returns exception messages to clients and can leak sensitive information.
  `Production` gives `Unknown` with a generic message, `Development` includes the text (two tests, with an exploding
  `IRequestEvents`).
- **Same rules, one creation path.** REST and gRPC both go through `CreateProjectRequest` (DataAnnotations +
  `IValidatableObject`) and `RequestEndpoints.CreateCoreAsync`; `The_same_rules_apply_over_REST_and_gRPC` compares the field
  names REST rejects with the ones the import reports.
- **Message size.** Learn: incoming messages are limited to 4 MB by default (server and client), outgoing unlimited; set it with
  `AddGrpc(o => o.MaxReceiveMessageSize = …)`. Not changed here.
- **The browser.** Learn: browsers can't make HTTP/2 gRPC calls; gRPC-Web (`Grpc.AspNetCore.Web` on the server, `Grpc.Net.Client.Web`
  in Blazor WebAssembly) supports unary and server streaming but not client or bidirectional streaming. Learn also names
  broadcast to many clients as a case for SignalR rather than gRPC. The Blazor app therefore stays on REST + SignalR.
- **In-memory tests.** `TestServer` is a supported gRPC server (Learn); `GrpcChannel.ForAddress(baseAddress, new GrpcChannelOptions
  { HttpClient = factory.CreateDefaultClient() })` is enough. No extra package besides `Grpc.Net.Client`.
- **PowerShell traps in the smoke script.** `Cli` is an alias of `Clear-Item`, and variable names are case-insensitive
  (`$rest` overwrote the `$Rest` parameter). Both bit us once.

## References
- [gRPC services with ASP.NET Core (Kestrel: HTTP/2, TLS, protocol negotiation)](https://learn.microsoft.com/aspnet/core/grpc/aspnetcore)
- [Create Protobuf messages for .NET apps (scalar types, `Timestamp`, wrappers, decimals)](https://learn.microsoft.com/aspnet/core/grpc/protobuf)
- [Create gRPC services and methods (unary, server / client / bidirectional streaming)](https://learn.microsoft.com/aspnet/core/grpc/services)
- [Reliable gRPC services with deadlines and cancellation](https://learn.microsoft.com/aspnet/core/grpc/deadlines-cancellation)
- [Transient fault handling with gRPC retries (when retries are valid, committed calls, streaming, `grpc-previous-rpc-attempts`)](https://learn.microsoft.com/aspnet/core/grpc/retries)
- [Error handling with gRPC (`RpcException`, status codes)](https://learn.microsoft.com/aspnet/core/grpc/error-handling)
- [gRPC for .NET configuration (server and client options, 4 MB limit, `EnableDetailedErrors`, interceptors)](https://learn.microsoft.com/aspnet/core/grpc/configuration)
- [Troubleshoot gRPC on .NET (insecure services need an HTTP/2-only port)](https://learn.microsoft.com/aspnet/core/grpc/troubleshoot)
- [Configure endpoints for the Kestrel web server (`HttpProtocols`)](https://learn.microsoft.com/aspnet/core/fundamentals/servers/kestrel/endpoints#configure-http-protocols)
- [gRPC on .NET supported platforms (TestServer, Blazor WebAssembly needs gRPC-Web)](https://learn.microsoft.com/aspnet/core/grpc/supported-platforms)
- [gRPC-Web in ASP.NET Core gRPC apps (limits)](https://learn.microsoft.com/aspnet/core/grpc/grpcweb)
- [Compare gRPC services with HTTP APIs (browser support, broadcast and SignalR)](https://learn.microsoft.com/aspnet/core/grpc/comparison)
- Blog: [gRPC Services — Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-16-grpc-services-complete-guide-2026/) (the current article is generic and should be replaced with this episode's code)
