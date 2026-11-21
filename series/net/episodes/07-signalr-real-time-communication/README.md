# DEVLADLOG .NET #7 — SignalR Real-Time Communication: a live board for the project requests API (.NET 10)

Episode 6's Blazor app showed requests as they were when you loaded the page. This episode makes it **live**: the API
pushes every new request, budget change and decision to whoever is watching — a Blazor WebAssembly **live board** in
the browser and an approver's **console watcher** — over ASP.NET Core SignalR, with nothing polling.

| Piece | What it does |
|---|---|
| **`RequestsHub : Hub<IRequestsClient>`** (API) | Strongly typed hub at `/hubs/requests`. `Watch(department)` puts the connection in **one** group: `all` or `dept:FIN`/`dept:IT`/`dept:OPS` (validated against the database; unknown codes get a `HubException`). Per-connection state in `Context.Items`, never in hub fields (a new hub instance per call) |
| **`IRequestEvents` → `SignalRRequestEvents`** (API) | The REST endpoints call it **after** a successful `SaveChanges` (create, budget change, decision); it pushes through `IHubContext<RequestsHub, IRequestsClient>` to `all` + `dept:<code>`. Best effort: a push failure is logged, never turned into a 500 for a write that's already committed |
| **`IRequestsClient` + `RequestsHubContract`** (Contracts) | The client-method names and hub path, shared by server and clients (`nameof(IRequestsClient.RequestCreated)`) |
| **`ProjectRequests.Feed`** (new library) | `RequestsFeed` wraps one `HubConnection`: string-enum JSON protocol, `WithAutomaticReconnect()` (0, 2, 10, 30 s), and **calls `Watch` again in `Reconnected`** because a reconnect is a new connection without groups. Raises `Resubscribed` so the UI reloads what it missed. Used in the browser and in the console |
| **`/live` page** (Web.Client, Interactive WebAssembly) | Connects **first**, then loads the list, and merges both through `BoardState` (a decided request is never overwritten by an older "Submitted" copy). Department filter re-watches on the server. Connection state on screen ("connection lost, reconnecting…"). Creates the feed in `OnAfterRenderAsync`, so prerendering never opens a connection |
| **`ProjectRequests.Watcher`** (new console) | `dotnet run -- --department FIN`: colour lines for NEW / UPDATED, connection state, retries the **first** start itself (automatic reconnect doesn't) |
| **CORS for the hub** | Separate named policy `signalr` with `RequireCors`: origins from `Cors:AllowedOrigins`, `GET/POST/DELETE`, any header, **credentials allowed** (Learn's SignalR requirements). The REST endpoints keep episode 6's stricter default policy |

| Path | What it is |
|---|---|
| [`src/ProjectRequests.Api/Live/`](src/ProjectRequests.Api/Live/) | `RequestsHub.cs`, `RequestEvents.cs`, `LiveSetup.cs` (`AddSignalR().AddJsonProtocol(...)`, CORS policy, `MapHub(...).RequireCors(...)`) |
| [`src/ProjectRequests.Api/Requests/RequestEndpoints.cs`](src/ProjectRequests.Api/Requests/RequestEndpoints.cs) | Episode 6's endpoints + `IRequestEvents` after each committed write |
| [`src/ProjectRequests.Contracts/Live.cs`](src/ProjectRequests.Contracts/Live.cs) | `IRequestsClient`, `RequestsHubContract` |
| [`src/ProjectRequests.Feed/RequestsFeed.cs`](src/ProjectRequests.Feed/RequestsFeed.cs) | `IRequestsFeed`, `RequestsFeed`, `IRequestsFeedFactory` |
| [`src/ProjectRequests.Web.Client/Pages/LiveBoard.razor`](src/ProjectRequests.Web.Client/Pages/LiveBoard.razor) + [`Services/BoardState.cs`](src/ProjectRequests.Web.Client/Services/BoardState.cs) | The live board and its merge rules |
| [`src/ProjectRequests.Watcher/Program.cs`](src/ProjectRequests.Watcher/Program.cs) | Console SignalR client |
| [`tests/ProjectRequests.Api.Tests/LiveUpdatesTests.cs`](tests/ProjectRequests.Api.Tests/LiveUpdatesTests.cs) | 10 end-to-end tests: real hub + real `HubConnection` over TestServer's WebSocket client (`HubTestKit.cs`) |
| [`tests/ProjectRequests.Api.Tests/CorsTests.cs`](tests/ProjectRequests.Api.Tests/CorsTests.cs) | Episode 6's 5 + 3 hub CORS tests |
| [`tests/ProjectRequests.Web.Tests/`](tests/ProjectRequests.Web.Tests/) | Episode 6's 19 + `LiveBoardTests` (7, bUnit with `FakeRequestsFeed`) + `BoardStateTests` (3) + 1 `WebHostTests` (`/live` prerender) = 30 |
| [`deploy/smoke.ps1`](deploy/smoke.ps1) / [`deploy/smoke.output.txt`](deploy/smoke.output.txt) | Runs the real watcher against the running apps, creates/decides requests, checks negotiate, hub CORS and `/live`; and its real output |
| [`deploy/tests.output.txt`](deploy/tests.output.txt) | Real output of `dotnet test` |

## Build, test, run

```bash
dotnet test                       # total: 101, failed: 0, succeeded: 100, skipped: 1 (~26 s)
                                  # Api.Tests 71 (58 from ep. 6 + 13 new), Web.Tests 30 (19 + 11 new)
                                  # skipped = episode 5's opt-in SQL Server test

# three terminals
cd src/ProjectRequests.Api && dotnet run --launch-profile http        # http://localhost:5207, hub at /hubs/requests
cd src/ProjectRequests.Web && dotnet run --launch-profile http        # http://localhost:5180, live board at /live
cd src/ProjectRequests.Watcher && dotnet run -- --department FIN      # console client
pwsh ./deploy/smoke.ps1                                               # watcher + REST + negotiate + CORS + /live
```

Verified in the container (SDK 10.0.115, ASP.NET Core 10.0.15, Microsoft.AspNetCore.SignalR.Client 10.0.15):
`dotnet test` 101/0/1; the API + watcher on Kestrel over **real WebSockets** (the hub logs `Connected: … (WebSockets)`;
the FIN watcher got the FIN create and decision, not the IT create); **stopping the API (SIGTERM, graceful) and
restarting it**: the watcher printed `Reconnecting`, then `reconnected as <new id>, watching all departments again`
about 12 s later (attempts at 0 and 2 s failed, the 10 s one succeeded) and received the next request; a second
instance on port 5217 sharing `requests.db` (`dotnet run --launch-profile http -- --urls http://localhost:5217`);
`deploy/smoke.ps1` against both running apps. **Not verifiable here (no browser):** the live board's WebAssembly
connection to the hub from `http://localhost:5180` and the WebSocket frames in DevTools — that's what the demo records.

## What we learned / gotchas

- **`ConfigureHttpJsonOptions` doesn't reach SignalR.** The REST API sends `"High"`; the hub, by default, sends enums as
  numbers. `AddJsonProtocol(o => o.PayloadSerializerOptions.Converters.Add(new JsonStringEnumConverter()))` on the
  server **and** the same on the .NET client (Learn: the client has its own `AddJsonProtocol`). Pinned by
  `Enums_travel_as_strings_on_the_wire`.
- **A mismatched client fails silently.** A `HubConnection` without the converter binding `RequestDto`: the message is
  dropped, the handler never runs, the connection stays `Connected`, nothing is thrown at your code — only a client log
  entry. `A_client_without_the_enum_converter_silently_drops_the_message` pins exactly that.
- **Reconnect = new connection = no groups.** Learn: group membership isn't preserved when a connection reconnects, and
  the `Reconnected` handler gets a new connection ID. The test restarts the server under two clients: `RequestsFeed`
  (calls `Watch` in `Reconnected`) gets the next FIN request; a plain `WithAutomaticReconnect()` connection reconnects
  fine and receives **nothing**.
- **Messages sent while you were away are gone.** SignalR doesn't queue them for a dropped client. The board reloads
  the list after `Resubscribed`, and connects *before* its first load so nothing falls between "loaded" and "listening".
- **`WithAutomaticReconnect` doesn't retry the first start** (Learn). The watcher loops on `StartAsync` itself; the
  board shows "Live updates unavailable".
- **Two instances, two islands.** `A_write_handled_by_another_instance_is_not_pushed`: same database, request created
  through instance B, the client on instance A never hears of it. Groups and connections live in each process. Learn's
  fix is a backplane — Azure SignalR Service (recommended for apps hosted on Azure; no sticky sessions needed for the
  app) or Redis (still needs sticky sessions). Not deployed here; the free tier is 20 concurrent connections and 20,000
  messages per unit per day.
- **SignalR needs a different CORS policy than our REST API.** Learn: specific origins, `GET`/`POST`/`DELETE`
  (long polling cleans up with `DELETE`), and credentials allowed even without authentication (cookie-based sticky
  sessions). Episode 6's policy (`Content-Type` header only, no credentials) would not do; we added a named policy on
  the hub endpoint only. CORS doesn't apply to WebSockets at all (Learn), so it isn't access control for the hub.
- **Only `HubException` messages reach the client.** Anything else becomes "An unexpected error occurred invoking
  'Watch' on the server." (unless `EnableDetailedErrors`). We throw `HubException("Unknown department 'XYZ'.")` on
  purpose; the test checks the text arrives.
- **Hubs are transient.** A new instance per invocation: the current group is kept in `Context.Items`, and the
  `RequestsDbContext` is injected as a hub *method* parameter (scoped per invocation).
- **Send to `all` + `dept:X` without duplicates** by keeping each connection in exactly one group.
- **Testing a real hub in memory**: `HttpConnectionOptions.HttpMessageHandlerFactory = _ => server.CreateHandler()`
  for negotiate and `WebSocketFactory = … server.CreateWebSocketClient().ConnectAsync(…)` for the socket. Looking the
  server up through a lambda let one test "restart" the API under a connected client.

## References
- [Overview of ASP.NET Core SignalR](https://learn.microsoft.com/aspnet/core/signalr/introduction)
- [Use hubs in SignalR (strongly typed hubs, `HubException`, DI in hub methods, hubs are per call)](https://learn.microsoft.com/aspnet/core/signalr/hubs)
- [Send messages from outside a hub (`IHubContext`)](https://learn.microsoft.com/aspnet/core/signalr/hubcontext)
- [Manage users and groups (membership not preserved on reconnect, in memory per server)](https://learn.microsoft.com/aspnet/core/signalr/groups)
- [SignalR .NET client (`WithAutomaticReconnect` 0/2/10/30 s, new connection ID, first start not retried)](https://learn.microsoft.com/aspnet/core/signalr/dotnet-client)
- [SignalR configuration (`AddJsonProtocol` on server and .NET client)](https://learn.microsoft.com/aspnet/core/signalr/configuration)
- [Security considerations in SignalR (CORS requirements, `RequireCors`, WebSockets, exceptions, 32 KB buffers)](https://learn.microsoft.com/aspnet/core/signalr/security)
- [SignalR hosting and scaling (sticky sessions, Azure SignalR Service, Redis backplane)](https://learn.microsoft.com/aspnet/core/signalr/scale)
- [Azure SignalR Service limits (Free tier: 20 connections, 20,000 messages/unit/day)](https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits#azure-signalr-service-limits)
- [Azure SignalR Service: client disconnections and reconnection](https://learn.microsoft.com/azure/azure-signalr/signalr-concept-client-disconnections)
- [Razor component lifecycle (`OnAfterRender` isn't called during prerendering)](https://learn.microsoft.com/aspnet/core/blazor/components/lifecycle)
- Blog: [SignalR Real-Time Communication — Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-12-signalr-real-time-communication-complete-guide-2026/) (the current article is generic and should be replaced with this episode's code)
