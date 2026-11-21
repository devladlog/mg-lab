# Demo shot list — DEVLADLOG .NET #9 Performance Optimization

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / containers | none (the shared Hyper-V lab is not used) |
| Azure | **none**: no resource group, no cost. Everything runs on the recording laptop against a local SQLite file |
| Lab tenant / licences | none |
| Recording machine | The Windows lab laptop (Windows Terminal, PowerShell 7). Software: **.NET SDK 10.0.1xx**, `curl.exe` (ships with Windows), **dotnet-counters** (`dotnet tool install -g dotnet-counters`), Git. Close other heavy apps and plug the laptop in (power plan "Best performance") before the benchmark and load-test screens, and don't touch the machine while they run |
| Clone | `git clone https://github.com/devladlog/mg-lab` then `cd mg-lab\series\net\episodes\09-performance-optimization` |

Every screen shows the real app, the real BenchmarkDotNet run, the real load generator and the real `dotnet-counters`.
Nothing is mocked. (Mocks and an in-memory test server appear only in the automated tests, never on screen.)

Built and verified in the build container (Linux, .NET SDK 10.0.115): `dotnet test` **30 passed**; the benchmarks, the
load test, `deploy/Measure-Endpoints.ps1`, the EF Core SQL log and `dotnet-counters collect` were all run for real and
their output is in `deploy/` (files marked `.container` / `.sample`). **Not run on Windows**: the laptop run itself.
Expect different absolute numbers; if a number on screen disagrees with the script, the script's narration only uses
shapes (allocation ratios, order of magnitude), but **check the allocation figures the narrator mentions on the real run**.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| `dotnet --version` is 10.0.1xx | `global.json` pins 10.0.100 with roll-forward to the latest feature band | free |
| `dotnet tool install -g dotnet-counters` | once, before recording; `dotnet-counters --version` | free |
| Ports 5209 free | the API and `Measure-Endpoints.ps1` use `http://localhost:5209` | — |
| Terminal font 18-20 pt, dark theme | SQL log and result tables must be readable at 1080p | — |
| Masking | the BenchmarkDotNet banner prints the machine's CPU model and OS build; the prompt shows the Windows user name. Use a neutral prompt (`function prompt { "PS> " }`) and crop the host banner. No tenant names or URLs appear in this episode | — |

## Setup (before recording, not on camera)
```powershell
cd series\net\episodes\09-performance-optimization
dotnet test                                   # expect: total: 30, failed: 0, succeeded: 30
dotnet build -c Release                       # warms the NuGet cache and the build
Remove-Item src\ProjectRequests.Perf.Api\perf.db* -ErrorAction SilentlyContinue
function prompt { "PS> " }
```
Do one complete dry run of the four screens first: the first start of the API seeds 20,000 rows (a few seconds).

## Screens (match `screen` scenes in script.yaml)

### 1. `sql-log` — "Count the queries" (terminal, 2 panes)
1. Left pane: `dotnet run --project src\ProjectRequests.Perf.Api --launch-profile http` (Development: the slow endpoint
   is on and EF Core logs every command). Wait for "Application started".
2. Right pane: `curl.exe "http://localhost:5209/api/slow/requests?take=2"` — left pane scrolls **5** `Executed DbCommand`
   blocks: `Requests ... LIMIT`, then `Requesters ... WHERE Id =`, `Departments ... WHERE Id =`, twice.
3. Right pane: `curl.exe "http://localhost:5209/api/requests?department=FIN&pageSize=2"` — **2** commands: `COUNT(*)`
   and one `SELECT` with `INNER JOIN "Requesters"`.
4. Optional: repeat the same call: **no new log lines** (output cache hit). Reference: `deploy/sql-log.sample.txt`.
5. Stop the API (`Ctrl+C`) before screen 2, so the benchmarks have the CPU to themselves.

### 2. `benchmarks` — "Prove it: BenchmarkDotNet" (terminal)
```powershell
dotnet run -c Release --project src\ProjectRequests.Perf.Benchmarks -- --filter "*QueryBenchmarks*"
```
Takes several minutes with the default job (the container needed ~2.5 min with `--job short`). Record the whole run, cut
the waiting, and show the **final summary table** (6 rows in two groups `list` / `sum`; columns Mean, Ratio, Gen0, Allocated).
Reference shape (container, ShortRun): N+1 tracked 6,010 KB allocated; Include tracked 578 KB; Include no-tracking 400 KB;
projection 175 KB; sum load-everything 24 MB vs in-database 3 MB. Optional second run for the JSON gotcha:
`--filter "*JsonBenchmarks*"` (35 KB as string either way, 17.6 KB as UTF-8 bytes). Delete `BenchmarkDotNet.Artifacts\` afterwards.

### 3. `loadtest` — "Before, after, cached" (PowerShell)
```powershell
pwsh .\deploy\Measure-Endpoints.ps1          # ~50 s: starts the API three ways, 8 workers x 8 s each, stops it
```
Three blocks of output (BEFORE N+1 / AFTER projection, cache off / AFTER + output cache on). Reference shape
(container): ~49 req/s -> ~849 req/s -> ~32,789 req/s; p99 424 ms -> 30 ms -> 2 ms. Don't run anything else meanwhile.

### 4. `counters` — "Watch your own counters" (terminal, 2 panes)
1. Pane A: `dotnet run --project src\ProjectRequests.Perf.Api --launch-profile http`
2. Pane B: `dotnet-counters monitor -n ProjectRequests.Perf.Api --counters ProjectRequests.Perf`
   (if the process name isn't found, use `dotnet-counters ps` and `--process-id`).
3. Pane C: 8 times `curl.exe -s -o NUL http://localhost:5209/api/summary`, then
   `curl.exe -s -X POST -H "Content-Type: application/json" -d "{\"title\":\"Counter demo\",\"budget\":75000,\"departmentCode\":\"fin\",\"requesterId\":7}" http://localhost:5209/api/requests`,
   then `/api/summary` again. Pane B: `mglab.perf.requests.created` ticks, `mglab.perf.summary.computed` ticks **once, after the write**.
   Counters refresh every second: wait a second between the POST and the read so the two ticks are visible.
   Reference: `deploy/dotnet-counters.sample.csv`. The first `/api/summary` after a start also computes once.

## Gotcha scene (no screen, covered by the README)
`gotchas` bullets are all real and reproducible from the tests/benchmarks; see the README "What we learned".

## Tear-down
```powershell
# Ctrl+C the API; stop any stray: Get-Process dotnet | Where-Object { $_.MainWindowTitle -eq '' } (check before killing)
Remove-Item src\ProjectRequests.Perf.Api\perf.db* -ErrorAction SilentlyContinue
Remove-Item BenchmarkDotNet.Artifacts -Recurse -ErrorAction SilentlyContinue
```
No Azure resources, nothing else to delete. `dotnet tool uninstall -g dotnet-counters` only if the laptop didn't have it before.
