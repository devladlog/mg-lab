# Demo shot list — DEVLADLOG .NET #7 SignalR Real-Time Communication

Built and run in the container: `dotnet test` 101 total, 100 passed, 1 skipped; API + console watcher on Kestrel over
real WebSockets, including a graceful API restart with automatic reconnect and group rejoin, and a second API instance
on port 5217; `deploy/smoke.ps1` against the running API and Blazor app (output in `deploy/smoke.output.txt`).
**Not verified in the container (no browser):** the Blazor WebAssembly live board connecting from
`http://localhost:5180` to the hub, the WebSocket frames in DevTools, and the board's reconnect banner. Those are the
screens below — if one behaves differently, report it instead of re-scripting around it.
No Azure (Azure SignalR Service is only discussed; scale-out is shown with two local instances), no tenant, no VM,
no licences. Cost: €0.

## Lab environment
| What | Details |
|---|---|
| Recording machine | Lab Windows laptop (host): .NET SDK 10.0.1xx, VS Code (C# Dev Kit), PowerShell 7, Windows Terminal, Microsoft Edge or Chrome with DevTools. All five screens are recorded here |
| Network | localhost only: API `http://localhost:5207` (hub `/hubs/requests`), second API instance `http://localhost:5217` (screen 4 only), Blazor app `http://localhost:5180`. Ports must be free; CORS allows exactly `http://localhost:5180` |
| Hyper-V lab / Azure / M365 | Not used |

## Setup (before recording)
```powershell
cd series/net/episodes/07-signalr-real-time-communication
dotnet test                                                   # expect total 101, succeeded 100, skipped 1
Remove-Item src/ProjectRequests.Api/requests.db* -ErrorAction SilentlyContinue
dotnet build src/ProjectRequests.Watcher

# terminal 1 (API) - creates and migrates requests.db on start (Development)
cd src/ProjectRequests.Api; dotnet run --launch-profile http
# terminal 2 (Blazor app)
cd src/ProjectRequests.Web; dotnet run --launch-profile http
# terminal 3 (watcher, Finance only) - keep it visible for screens 2-4
cd src/ProjectRequests.Watcher; dotnet run -- --department FIN
```
Optional dry run: `pwsh ./deploy/smoke.ps1` (starts its own watcher, creates two requests; all checks True). If you run
it, delete `requests.db*` and restart terminal 1 before recording so ids start at 1.
Browser: InPrivate window, zoom 125 %, close the tabs `launchBrowser` opens. Windows Terminal font size 16+.

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/live-board.jpg`** — *Submit here, it appears there*
   - Two browser windows side by side. Right: `http://localhost:5180/live`, DevTools → Network → filter **WS** →
     reload → select `requests?id=…` (host `localhost:5207`) → **Messages**. Header shows
     "SignalR: **connected · watching all departments**", "Rendered by: WebAssembly · interactive: True".
   - Left: `http://localhost:5180/requests/new`. Title `Data platform`, Requested by `alex.demo@contoso.com`,
     Department `Information Technology`, Budget `80000` → **Submit**.
   - In frame on the right: new highlighted row `#1 Data platform IT 80,000 High Submitted` at the top, the Events
     list line `#1 created · IT · High · Submitted`, and a WebSocket frame
     `{"type":1,"target":"RequestCreated","arguments":[{"id":1,…,"priority":"High","status":"Submitted",…}]}`.
   - Terminal 3 (FIN watcher) shows nothing for this IT request (keep it out of frame or use it as setup for screen 2).
2. **`screens/watcher-groups.jpg`** — *Groups: Finance only*
   - Terminal 3 beside the browser. Create `Laptop refresh`, `Finance`, `12000` on `/requests/new`: cyan
     `NEW     #2 FIN Laptop refresh  12,000  Standard Submitted` in the terminal, new row on `/live`.
   - Open `http://localhost:5180/requests/2`, click **Approve** (Decided by `sam.approver@contoso.com`): green
     `UPDATED #2 FIN … Approved by sam.approver@contoso.com` in the terminal; on `/live` the row's status turns
     **Approved** at the same moment.
3. **`screens/reconnect.jpg`** — *Stop the server. Start it again.*
   - Three panes: terminal 1 (API), terminal 3 (watcher), `/live`.
   - Ctrl+C in terminal 1. Watcher: `connection: Reconnecting`. Board: "SignalR: **connection lost, reconnecting…**".
   - Wait ~5 s, then `dotnet run --launch-profile http` in terminal 1. At the next attempt (default delays 0, 2, 10,
     30 s) the watcher prints `connection: Connected` and `reconnected as <new id>, watching FIN again`; the board shows
     connected and the event line `reconnected: reloading the list`. *(Verified in the container for the watcher: about
     12 s after a graceful stop. The board's behaviour is covered by bUnit tests, not yet seen in a browser.)*
   - Create a FIN request (`Badge readers`, `30000`): it arrives in both.
   - If the API is down longer than ~42 s the clients give up (`connection: Disconnected`); reload the page / restart
     the watcher and redo the take.
4. **`screens/scale-out.jpg`** — *Instance B writes, the board on A stays quiet*
   - Terminal 4 in `src/ProjectRequests.Api`: `dotnet run --launch-profile http -- --urls http://localhost:5217`
     (verified: listens on 5217 and shares `requests.db`).
   - Terminal 5:
     ```powershell
     Invoke-RestMethod -Method Post http://localhost:5217/api/requests -ContentType application/json `
       -Body '{"title":"Written on B","budget":5000,"requestedBy":"alex.demo@contoso.com","departmentCode":"FIN"}'
     ```
   - In frame: the 201 response in terminal 5, the watcher and `/live` showing **nothing**. Then F5 on `/live`: the
     `Written on B` row is there (it was in the database all along).
   - Ctrl+C terminal 4.
5. **`screens/tests.jpg`** — *A real hub, a real client, in memory*
   - VS Code terminal in the episode folder: `Clear-Host; dotnet test`. In frame: both test apps passed, `total: 101`,
     `succeeded: 100`, `skipped: 1` (compare `deploy/tests.output.txt`). Optional: Testing view with
     `ProjectRequests.Api.Tests` → `LiveUpdatesTests` expanded (10 tests).

**Masking:** nothing sensitive on screen (localhost, fictional `contoso.com` people). The connection ids in the
watcher are random per run. Close other tabs and the bookmarks bar; no account avatar in the browser chrome.

## Tear-down
- Ctrl+C in all terminals (API instances, Blazor app, watcher).
- `Remove-Item src/ProjectRequests.Api/requests.db*`
