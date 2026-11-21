# Demo shot list — DEVLADLOG .NET #6 Blazor WebAssembly & Server

Built and run in the container: `dotnet test` 77 total, 76 passed, 1 skipped (three runs in a row); both apps started
with `dotnet run` and checked with `deploy/smoke.ps1` (output in `deploy/smoke.output.txt`).
**Not verified in the container (no browser):** the live circuit, the WebAssembly runtime starting in the browser, the
CORS error in the console, and the single "Loading request" log line after the page becomes interactive. Those are
exactly the screens below — if one behaves differently, report it instead of re-scripting around it.
No Azure, no tenant, no VM, no licences. Cost: €0.

## Lab environment
| What | Details |
|---|---|
| Recording machine | Lab Windows laptop (host): .NET SDK 10.0.1xx, VS Code (C# Dev Kit), PowerShell 7, Microsoft Edge or Chrome with DevTools. All four screens are recorded here |
| Network | localhost only: API `http://localhost:5207`, Blazor app `http://localhost:5180`. Ports must be free; the CORS policy allows exactly `http://localhost:5180` |
| Hyper-V lab / Azure / M365 | Not used |

## Setup (before recording)
```powershell
cd series/net/episodes/06-blazor-webassembly-server
dotnet test                                                   # expect total 77, succeeded 76, skipped 1
Remove-Item src/ProjectRequests.Api/requests.db* -ErrorAction SilentlyContinue

# terminal 1 (API) - creates and migrates requests.db on start (Development)
cd src/ProjectRequests.Api; dotnet run --launch-profile http
# terminal 2 (Blazor app) - keep it visible for screen 1, it logs "Loading request ..."
cd src/ProjectRequests.Web; dotnet run --launch-profile http
# terminal 3
pwsh ./deploy/smoke.ps1                                       # creates requests #1 and #2, all checks True
```
Browser: new profile or InPrivate window, zoom 125 %, DevTools docked right, **Disable cache** ticked in Network.
`launchBrowser` in the launch profiles opens tabs automatically; close them and use the prepared window.

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/interactive-server.jpg`** — *Clicks travel over the circuit*
   - Clear terminal 2. Open `http://localhost:5180/requests/2` with a full reload (Ctrl+F5).
   - DevTools → Network → filter **WS** → select `_blazor?id=…` → **Messages**.
   - In frame: page with `#2 · Data platform`, "Rendered by: **Server** · interactive: **True**"; terminal 2 with exactly
     **one** `Loading request 2 from the API (Static)` line for this page load.
   - Click **Approve**: new messages in the WebSocket, status turns **Approved**, the buttons disappear.
   - Optional B-roll for the persist scene: comment out `[PersistentState]` in `RequestDetail.razor`, restart terminal 2,
     reload `/requests/1`: expect two lines (`(Static)` then `(Server)`). Restore the attribute and restart. *(Expected
     from Learn's documentation; not verifiable in the container.)*
2. **`screens/webassembly.jpg`** — *Dot net, running in the browser*
   - Network tab, filter **All**, Disable cache on. Hard reload `http://localhost:5180/requests/new`.
   - In frame: `_framework/` requests including `dotnet.native.*.wasm`, `System.Private.CoreLib.*.wasm`,
     `ProjectRequests.Contracts.*.wasm`, `ProjectRequests.Web.Client.*.wasm`; the page header switching from
     "Rendered by: Static" to "Rendered by: **WebAssembly** · interactive: **True**" (capture both, or cut).
   - Clear the network log (🚫). Type `49999` then `50000` in **Budget**: preview flips **Standard → High**, the network
     log stays **empty**.
   - Title `Laptop refresh`, Requested by `alex.demo@contoso.com`, Department `Finance`, Budget `300000`, no
     justification → **Submit**: "A justification is required for budgets of 250,000 or more." and still no request.
   - Justification `Replaces the 2019 fleet` → **Submit**: `OPTIONS` preflight then `POST http://localhost:5207/api/requests`
     `201`, page shows "Request #3 created · High priority."
3. **`screens/cors-blocked.jpg`** — *Remove the origin, and the browser refuses*
   - Stop terminal 1 (Ctrl+C) and restart the API with another allowed origin (verified in the container: the
     preflight then has no `Access-Control-Allow-Origin`):
     `dotnet run --launch-profile http -- --Cors:AllowedOrigins:0=http://localhost:5999`
   - On `/requests/new` submit a valid request. In frame: **Console** with
     `Access to fetch at 'http://localhost:5207/api/requests' from origin 'http://localhost:5180' has been blocked by CORS policy …`
     and in Network the failed `POST`/preflight without `Access-Control-Allow-Origin`. The page shows
     "Could not reach the API: …" (the component catches the `HttpRequestException`; the exact message text comes
     from the browser).
   - Restart the API normally (`dotnet run --launch-profile http`) and submit again → 201.
4. **`screens/tests.jpg`** — *Seventy-seven tests, one command*
   - VS Code terminal in the episode folder: `Clear-Host; dotnet test`. In frame: both test apps passed,
     `total: 77`, `succeeded: 76`, `skipped: 1` (compare `deploy/tests.output.txt`). Optional: Testing view with
     `ProjectRequests.Web.Tests` → `NewRequestTests` expanded.

**Masking:** nothing sensitive is on screen (localhost, fictional `contoso.com` people). Close other browser tabs and
bookmarks bar; no account avatar in the browser chrome.

## Tear-down
- Ctrl+C in terminals 1 and 2.
- `Remove-Item src/ProjectRequests.Api/requests.db*`
- If `[PersistentState]` was commented out for the optional B-roll, `git checkout -- src/ProjectRequests.Web/Components/Pages/RequestDetail.razor`.
