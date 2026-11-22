# Demo shot list — DEVLADLOG Code #3 Async and await, done properly

## Lab environment
| What | Details | Cost |
|---|---|---|
| Machine | The Windows recording laptop (host). **No VM, no tenant, no Azure resources.** | — |
| .NET SDK 10.0.1xx | `dotnet --version` (built and tested with 10.0.115) | free |
| Windows Terminal | dark theme, font 18 pt or larger, one window split in two panes (Alt+Shift+D), ~200 columns total | free |
| VS Code + C# Dev Kit | only to show code if wanted; screens are terminal captures | free |
| Port | `http://localhost:5080` free (the API's launch profile) | — |

Everything was built and tested in the container (`dotnet test`: **27 passed**, 10 runs in a row;
`./demo/expect-errors.sh`: exit code 0). Every screen is the real code running on the recording laptop: the Finance
API (an ASP.NET Core app we build in this episode) in one terminal pane and the console client in the other. The
API's 300 ms per lookup is a fixed delay inside the API so timings are reproducible; the HTTP calls, cancellation and
aborts are real. Reference output: [`demo/expected-output.txt`](demo/expected-output.txt).

## Setup (once, before recording)
```powershell
cd series\programming-languages\episodes\03-async-await-patterns
dotnet test AsyncPatterns.slnx -m:1          # expect Passed: 27 (also restores and builds everything)
dotnet build src\Contoso.Approvals.Cli -m:1  # so the client starts instantly with --no-build
function prompt { '> ' }                      # short prompt in BOTH panes (hides user name and path)
```
- Left pane: `dotnet run --project src\Contoso.Approvals.Api` → wait for `Now listening on: http://localhost:5080`.
- Right pane: the client commands below. Run each once as a rehearsal (first run JIT-compiles), then `cls` both panes.
- **Check Ctrl+C once on Windows** before recording: `dotnet run --no-build --project src\Contoso.Approvals.Cli -- sequential`,
  press Ctrl+C after ~1.5 s, expect `Ctrl+C: cancelling...` and `Cancelled after ...`. (In the container this was tested
  with SIGINT.) If `dotnet run` itself stops first, run the built app directly:
  `dotnet src\Contoso.Approvals.Cli\bin\Debug\net10.0\Contoso.Approvals.Cli.dll sequential`.

## Screens (match the `screen` scenes in script.yaml)

The timings quoted in the frames below are the ones in the recorded takes; they vary by a few milliseconds per run
(the container's reference run is in `demo/expected-output.txt`).

1. **`screens/sequential.jpg`** — *Baseline: one request at a time* (scene `sequential`)
   - Right: `dotnet run --no-build --project src\Contoso.Approvals.Cli -- sequential`
   - Frame: left pane with API lines `budget CC-300 start (in flight 1)` / `done 305 ms`; right pane ending with
     `sequential: 12 requests in 3.79 s, 9 within budget, 3 over budget` and `api saw: ... MaxInFlight = 2 ...`.

2. **`screens/bounded.jpg`** — *Fast, and fair to the API* (scene `bounded`)
   - Right: `... -- unbounded` then `... -- bounded`.
   - Frame: `all at once (Task.WhenEach): 12 requests in 0.36 s` + `MaxInFlight = 24`, then
     `bounded, 4 at a time: 12 requests in 1.03 s` + `MaxInFlight = 8`. Left pane: a line with `(in flight 24)`.
     If both runs don't fit, capture two frames and cut between them.

3. **`screens/cancel.jpg`** — *Proof from the server side* (scene `cancel`)
   - Recorded with the kit (`record.json`, `Start-WtLayout.ps1`): a two-pane Windows Terminal plays the commands
     below. The Ctrl+C is **sent, not pressed**: the client runs as
     `Send-CtrlC -AfterMs 3000 { dotnet run --no-build --project src\Contoso.Approvals.Cli -- sequential }`, typed on
     screen as is; `series/tools/rec/Send-CtrlC.ps1` generates a real CTRL_C_EVENT on that console 3 s after the start
     (1.87 s into the batch in the take) and the client's own `Console.CancelKeyPress` handler runs. The screen prepare
     rehearses it once off camera and stops if the Ctrl+C would miss the batch.
   - The left pane starts the API on camera, so its first lines are the ASP.NET startup messages.
   - Right: `... -- timeout --timeout-ms 150`, then `... -- waitasync --timeout-ms 150`, then
     `Send-CtrlC -AfterMs 3000 { ... -- sequential }` (the Ctrl+C is sent, nobody presses a key).
   - Frame: right pane `TimeoutException after 172 ms: Gave up after 150 ms.` (Aborted = 1),
     `TimeoutException after 164 ms: The operation has timed out.` (Aborted = 0), `Ctrl+C: cancelling...`,
     `Cancelled after 1.87 s.` (Calls = 14, Aborted = 2).
     Left pane: `ABORTED by the client after 148 ms`, then `start` + `done 302 ms` (the WaitAsync call kept running),
     then two `ABORTED by the client after 1 ms` lines (the Ctrl+C).

4. **`screens/deadlock.jpg`** — *The deadlock, on demand* (scene `deadlock`), API not needed
   - `dotnet build demo\Analyzers -m:1 --no-incremental -v q` → the three `error CS4014 / CA2016 / CA1849` lines.
   - `dotnet run --no-build --project src\Contoso.Approvals.Cli -- deadlock` →
     `1. .Wait() on async code -> DEADLOCK (2013 ms, the work needed 100)`, `2. ... completed`, `3. ... completed`.
   - (Git Bash/WSL alternative: `./demo/expect-errors.sh` prints all of it, plus the `ok` checks.)

The `gotcha`, `timeout` and `retry` scenes are code slides; their proof is screen 3 and the tests
`Gotcha_WaitAsync_stops_waiting_but_not_the_work` and `Retry_backs_off_200_then_400_ms_and_the_test_takes_no_real_time`.

## Masking
- Prompt shortened (`function prompt { '> ' }`); no user name or absolute path on screen. The Windows Terminal tab
  title can show the path: set it with `$Host.UI.RawUI.WindowTitle = 'api'` / `'client'`.
- All data is fictional (`*.demo@contoso.com`, `PR-2026-01xx`, cost centers `CC-100`..`CC-400`). Nothing to blur.

## Tear-down
- Ctrl+C in the API pane.
- `Get-ChildItem -Recurse -Directory -Include bin,obj | Remove-Item -Recurse -Force`
- Nothing was created outside the folder.
