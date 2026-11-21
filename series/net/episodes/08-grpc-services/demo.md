# Demo shot list — DEVLADLOG .NET #8 gRPC Services

Built and run in the container: `dotnet test` 133 total, 132 passed, 1 skipped; the API on real Kestrel (REST + SignalR on
5207, gRPC over HTTP/2 without TLS on 5208) with the console client doing import / list / get, a FIN SignalR watcher
receiving the gRPC-created FIN row, the wrong-port error, a 1 ms deadline, and the API stopped (`Unavailable` after the
retries); `deploy/smoke.ps1` end to end (output in `deploy/smoke.output.txt`).
**Not verified in the container (no browser, Linux):** the Blazor live board in a browser (screen 2) and the commands on
Windows (`curl.exe`, Windows Terminal). If something behaves differently, report it instead of re-scripting around it.
No Azure, no tenant, no VM, no licences. Cost: €0.

## Lab environment
| What | Details |
|---|---|
| Recording machine | Lab Windows laptop (host): .NET SDK 10.0.1xx, VS Code (C# Dev Kit), PowerShell 7, Windows Terminal, Microsoft Edge or Chrome, `curl.exe` (ships with Windows 10/11). All five screens are recorded here |
| Network | localhost only: API REST + SignalR `http://localhost:5207`, API gRPC `http://localhost:5208` (HTTP/2 only), Blazor app `http://localhost:5180`. Ports must be free |
| Hyper-V lab / Azure / M365 | Not used |

## Setup (before recording)
```powershell
cd series/net/episodes/08-grpc-services
dotnet test                                                   # expect total 133, succeeded 132, skipped 1
Remove-Item src/ProjectRequests.Api/requests.db* -ErrorAction SilentlyContinue
dotnet build src/ProjectRequests.Cli; dotnet build src/ProjectRequests.Watcher

# terminal 1 (API) - creates and migrates requests.db on start (Development); two "Now listening on" lines
cd src/ProjectRequests.Api; dotnet run --launch-profile http
# terminal 2 (Blazor app; only needed for screen 2)
cd src/ProjectRequests.Web; dotnet run --launch-profile http
# terminal 3 (FIN watcher; only needed for screen 2)
cd src/ProjectRequests.Watcher; dotnet run -- --department FIN
# terminal 4: the CLI
cd src/ProjectRequests.Cli
```
Optional dry run: `pwsh ./deploy/smoke.ps1` (expects an empty database; all checks as in `deploy/smoke.output.txt`). Delete
`requests.db*` and restart terminal 1 before recording so ids start at 1.
Browser: InPrivate window, zoom 125 %, close the tab `launchBrowser` opens for the Blazor app. Terminal font size 16+.

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/cli-calls.jpg`** — *Import, list, get: three call shapes*
   - Terminal 4 and terminal 1 side by side (API log visible: `ImportRequests: 6 received, 3 created, 3 error(s)`).
   - `dotnet run -- import sample-import.csv` → `line 4: skipped, budget 'abc' is not a number`, `server received 6 row(s),
     created 3: [1, 2, 3]`, then `line 5: DepartmentCode: Unknown department 'XYZ'.`, `line 6: Justification: A justification
     is required for budgets of 250,000 or more.`, `line 7: RequestedBy: The RequestedBy field is not a valid e-mail address.`
     (exit code 3).
   - `dotnet run -- list` → three rows, `3 request(s)`; `dotnet run -- list --department FIN` → `#3 FIN Standing desks`;
     `dotnet run -- get 2` (with the justification line); `dotnet run -- get 99` → `gRPC error: NotFound - Request 99 not found.`
2. **`screens/import-live.jpg`** — *gRPC writes reach the live board* **(needs the browser: not verified in the container)**
   - Delete `requests.db*` and restart terminal 1 first (ids from 1). Three panes: browser `http://localhost:5180/live`
     ("SignalR: connected · watching all departments"), terminal 3 (FIN watcher), terminal 4.
   - `dotnet run -- import sample-import.csv`: three rows appear on the board (`#1 OPS`, `#2 IT`, `#3 FIN`), the FIN watcher
     prints only `NEW     #3 FIN Standing desks …` (that part was verified in the container).
3. **`screens/wrong-port.jpg`** — *Gotcha: the wrong port*
   - `dotnet run -- --address http://localhost:5207 get 1` → `gRPC error: Internal - Error starting gRPC call.
     HttpRequestException: The HTTP/2 server closed the connection. HTTP/2 error code 'HTTP_1_1_REQUIRED' (0xd) …`
   - `curl.exe --http1.1 -s -o NUL -w "%{http_code}" http://localhost:5208/healthz` → `400` (Linux curl: 400). Optional:
     `curl.exe --http2-prior-knowledge http://localhost:5208/healthz` → `Healthy`.
   - Then the right port: `dotnet run -- get 1` works.
4. **`screens/deadline.jpg`** — *Unavailable and DeadlineExceeded*
   - `dotnet run -- --deadline 0.001 list` → `gRPC error: DeadlineExceeded -`.
   - Ctrl+C terminal 1 (wait until it has stopped), then `dotnet run -- get 1` → after about 1.5 s
     `gRPC error: Unavailable - Error connecting to subchannel.` (three attempts with backoff; time it if you like with
     `Measure-Command { dotnet run --no-build -- get 1 }`). Restart terminal 1 afterwards.
5. **`screens/tests.jpg`** — *A real gRPC client, in memory*
   - VS Code terminal in the episode folder: `Clear-Host; dotnet test`. In frame: both test apps passed, `total: 133`,
     `succeeded: 132`, `skipped: 1` (compare `deploy/tests.output.txt`). Optional: Testing view with `GrpcServiceTests` (20),
     `CliTests` (7) and `CancellationStatusInterceptorTests` (5) expanded.

**Masking:** nothing sensitive on screen (localhost, fictional `contoso.com` people). The connection ids in the watcher are
random per run. Close other tabs and the bookmarks bar; no account avatar in the browser chrome.

## Tear-down
- Ctrl+C in all terminals (API, Blazor app, watcher).
- `Remove-Item src/ProjectRequests.Api/requests.db*`
