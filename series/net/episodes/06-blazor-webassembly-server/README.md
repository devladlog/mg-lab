# DEVLADLOG .NET #6 — Blazor WebAssembly & Server: three render modes in one Blazor Web App (.NET 10)

The project requests API from episodes 1–5 gets a UI: a **Blazor Web App** where each page picks the render mode that
fits it, and the business rules are written **once** for the API, the server and the browser.

| Page | Render mode | Why |
|---|---|---|
| `/requests` (list) | **Static SSR** + `[StreamRendering]` | Read-only. HTML only: no circuit, no WebAssembly download. "Loading requests…" is streamed first, the table follows in the same response |
| `/requests/{id}` (approve / reject) | **Interactive Server** + .NET 10 `[PersistentState]` | Clicks run on the server over the SignalR circuit; the request loaded during prerendering is persisted in the page instead of being fetched again |
| `/requests/new` (form) | **Interactive WebAssembly** (`.Client` project) | Runs in the browser: live priority preview and full validation (attributes + `IValidatableObject`) with no server round trip; posts straight to the API (CORS) |

- **`ProjectRequests.Contracts`** (new): enums, `PriorityRules`, DTOs and input models with their validation attributes
  moved out of the API into a plain class library (no ASP.NET Core/EF Core), referenced by the API and the WebAssembly
  client. The API still validates everything; the browser just gets the same answer sooner.
- **API changes**: references Contracts; **CORS** default policy for the origins in `Cors:AllowedOrigins`
  (Development: `http://localhost:5180`, methods GET/POST/PUT, header Content-Type); Development applies migrations at
  startup so the demo needs no `dotnet-ef`.
- **`RendererInfo` on every page** ("Rendered by: Static / Server / WebAssembly · interactive: …") so the demo shows
  where each page runs, and buttons stay disabled until the page is interactive (Learn's recommendation).

| Path | What it is |
|---|---|
| [`src/ProjectRequests.Contracts/`](src/ProjectRequests.Contracts/) | `Enums.cs`, `PriorityRules.cs`, `Requests.cs` (DTOs, `CreateProjectRequest : IValidatableObject`, …) |
| [`src/ProjectRequests.Web/Program.cs`](src/ProjectRequests.Web/Program.cs) | `AddInteractiveServerComponents` + `AddInteractiveWebAssemblyComponents`; typed `HttpClient` for `IRequestsApi` (also needed to prerender WebAssembly pages) |
| [`src/ProjectRequests.Web/Components/Pages/Requests.razor`](src/ProjectRequests.Web/Components/Pages/Requests.razor) | Static SSR list with stream rendering |
| [`src/ProjectRequests.Web/Components/Pages/RequestDetail.razor`](src/ProjectRequests.Web/Components/Pages/RequestDetail.razor) | Interactive Server page: `[PersistentState]`, approve/reject with the version the user saw, 409 shown |
| [`src/ProjectRequests.Web.Client/Pages/NewRequest.razor`](src/ProjectRequests.Web.Client/Pages/NewRequest.razor) | Interactive WebAssembly form: `EditForm` + `DataAnnotationsValidator`, `PriorityRules` preview on `oninput` |
| [`src/ProjectRequests.Web.Client/Services/RequestsApiClient.cs`](src/ProjectRequests.Web.Client/Services/RequestsApiClient.cs) | `IRequestsApi` + `RequestsApiClient`: enums as strings, problem details → `ApiResult` |
| [`src/ProjectRequests.Web.Client/Program.cs`](src/ProjectRequests.Web.Client/Program.cs) + `wwwroot/appsettings.json` | Browser-side `HttpClient` to the API; the API URL is public configuration |
| [`src/ProjectRequests.Api/Program.cs`](src/ProjectRequests.Api/Program.cs) | Episode 5's API + `AddCors`/`UseCors` |
| [`tests/ProjectRequests.Api.Tests/`](tests/ProjectRequests.Api.Tests/) | Episode 5's 53 xUnit v3 tests (now against Contracts) + `CorsTests` (5) = 58 |
| [`tests/ProjectRequests.Web.Tests/`](tests/ProjectRequests.Web.Tests/) | bUnit + host tests (19): `NewRequestTests` (7), `RequestDetailTests` (3), `RequestsPageTests` (1), `RequestsApiClientTests` (4), `WebHostTests` (4, `WebApplicationFactory` of the Blazor host) |
| [`deploy/smoke.ps1`](deploy/smoke.ps1) / [`deploy/smoke.output.txt`](deploy/smoke.output.txt) | Checks the two running apps (SSR, prerender markers, persisted state, public client config, CORS preflight) and its real output |
| [`deploy/tests.output.txt`](deploy/tests.output.txt) | Real output of `dotnet test` |

## Build, test, run

```bash
dotnet test                       # MTP mode (global.json) -> total: 77, failed: 0, succeeded: 76, skipped: 1 (~12 s)
                                  # skipped = episode 5's opt-in SQL Server test

# two terminals
cd src/ProjectRequests.Api && dotnet run --launch-profile http     # http://localhost:5207, SQLite, migrates on start
cd src/ProjectRequests.Web && dotnet run --launch-profile http     # http://localhost:5180
pwsh ./deploy/smoke.ps1                                            # creates 2 requests, checks both apps
```

Verified in the container: the three test runs in a row (77/0/1), both apps started with `dotnet run` and checked with
`deploy/smoke.ps1` and `curl` (static SSR with a `<blazor-ssr>` streamed chunk; `/requests/1` and `/requests/new`
prerendered with the server / webassembly markers; `Blazor-Server-Component-State` in the page; CORS preflight allowed
for `http://localhost:5180` only, also with the origin overridden on the command line). A Release publish of the web
app was measured: `dotnet.native.wasm` 3.0 MB, 0.98 MB as `.br`; `System.Private.CoreLib` 1.77 MB / 0.55 MB.
**Not verifiable here (no browser in the container):** the interactive part — the circuit, the WebAssembly runtime
starting, and that the interactive render does *not* call the API a second time. That's what the demo records.
Tested with .NET SDK 10.0.115, ASP.NET Core 10.0.15, bUnit 2.15.2, xunit.v3 4.0.3.

## What we learned / gotchas

- **WebAssembly pages are prerendered on the server, with the server's services.** With `IRequestsApi` registered only
  in the `.Client` project, `/requests/new` returns 500 before the browser gets anything:
  `InvalidOperationException: Cannot provide a value for property 'Api' on type 'ProjectRequests.Web.Client.Pages.NewRequest'.
  There is no registered service of type 'ProjectRequests.Web.Client.Services.IRequestsApi'.` Learn documents both fixes
  (register on the server too, or disable prerendering for the component). We register it in both `Program.cs` files;
  `WebHostTests.Without_a_server_registration_the_WebAssembly_page_fails_to_prerender` pins it.
- **Prerendering runs `OnInitializedAsync` twice** (Learn): once on the server, once interactive — two API calls per page
  view. `[PersistentState]` (.NET 10) on a public property persists it into the page; `WebHostTests` checks the API is
  called once during prerender and the state marker is in the HTML.
- **CORS is enforced by the browser, not the server.** Our first test expected the API to refuse a `DELETE` preflight. It
  doesn't: it answers `204` with `Access-Control-Allow-Methods: GET,POST,PUT` and the browser blocks the call. `curl` or
  any server-side caller ignores CORS completely — it protects users in browsers, it isn't API access control.
- **A port or a scheme is a different origin.** `CorsTests` checks that `http://localhost:5181` and
  `https://localhost:5180` get no `Access-Control-Allow-Origin`.
- **The client's `wwwroot/appsettings.json` is public.** `smoke.ps1` downloads it from the web app like a browser does.
  Learn: never store secrets or credentials in any web root file. Here it only holds the API's base URL.
- **Stream rendering needs an awaited call that actually yields.** With a fake API returning `Task.FromResult`, the page
  rendered in one go and the "Loading requests…" test failed. A 300 ms delay in the fake (like a real HTTP call) made the
  `<blazor-ssr>` streamed chunk appear.
- **bUnit + xUnit v3: `TestContext` is ambiguous** (`Bunit.TestContext` vs `Xunit.TestContext`, error CS0104) as soon as
  both namespaces are imported. The tests use a `Ct` helper spelled `Xunit.TestContext.Current.CancellationToken`.
- **bUnit needs to be told the renderer.** Components that read `RendererInfo` need `SetRendererInfo(new RendererInfo("WebAssembly", true))`
  (or `"Server"`, `"Static"`) — which is also how we test the "disabled while prerendering" state.
- **Moving types to a shared library didn't touch the migrations.** The enums are stored as strings
  (`HasConversion<string>()`), so the migrations and model snapshots don't reference the enum types; the API's 53 tests
  and `HasPendingModelChanges` stayed green after the move.

## Choosing a render mode (from Learn's hosting model comparison)
- **Static SSR**: fastest initial load, nothing to keep alive; no interactivity.
- **Interactive Server**: small download, app code stays on the server, full .NET API; every interaction is a network
  hop, no offline, each browser tab holds a circuit (server resources scale with users).
- **Interactive WebAssembly**: work moves to the client, no hop per click; larger download, browser capabilities only,
  and code sent to the client can be inspected — anything secret stays behind an API.

## References
- [Blazor render modes (static SSR, Interactive Server/WebAssembly/Auto, `RendererInfo`, prerendering default)](https://learn.microsoft.com/aspnet/core/blazor/components/render-modes)
- [Blazor hosting models (Server vs WebAssembly trade-offs, circuits)](https://learn.microsoft.com/aspnet/core/blazor/hosting-models)
- [Prerendered state persistence and `[PersistentState]`](https://learn.microsoft.com/aspnet/core/blazor/state-management/prerendered-state-persistence)
- [What's new in ASP.NET Core in .NET 10: declarative state persistence](https://learn.microsoft.com/aspnet/core/release-notes/aspnetcore-10.0)
- [Razor component lifecycle (`OnInitializedAsync` runs twice when prerendering)](https://learn.microsoft.com/aspnet/core/blazor/components/lifecycle)
- [Streaming rendering](https://learn.microsoft.com/aspnet/core/blazor/components/rendering#streaming-rendering)
- [Call a web API from Blazor (server `HttpClient` for prerendering, CORS error text)](https://learn.microsoft.com/aspnet/core/blazor/call-web-api)
- [Prerender Razor components: client-side services fail to resolve during prerendering](https://learn.microsoft.com/aspnet/core/blazor/components/prerender#client-side-services-fail-to-resolve-during-prerendering)
- [Blazor configuration (wwwroot settings are visible to users)](https://learn.microsoft.com/aspnet/core/blazor/fundamentals/configuration)
- [Enable CORS in ASP.NET Core](https://learn.microsoft.com/aspnet/core/security/cors)
- [bUnit documentation](https://bunit.dev/)
- Blog: [Blazor WebAssembly & Server — Complete Guide](https://www.devladlog.com/articles/dotnet/2026-04-24-blazor-webassembly-server-complete-guide-2026/) (the current article is generic and should be replaced with this episode's code)
