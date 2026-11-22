# Demo shot list - DEVLADLOG Code #9 JavaScript and Node.js patterns

## Lab environment
| Item | What this episode needs |
|---|---|
| VMs / tenant / Azure | none. The screens show the real project: Node.js, the real HTTP approvals service in this folder, VS Code |
| Licences / cost | none |
| Recording machine | The Windows lab laptop (host): Node.js 22 LTS or later, VS Code, Windows Terminal with PowerShell 7, opened in the episode folder under a neutral path (e.g. `C:\lab\...`) |

Everything was built and tested in the container (26 tests passed, all demo commands run). **No tenant, no cloud resources.**
The approvals service is part of the project (it is the thing being built), not a stand-in for a cloud service.
Reference output for every screen: [`demo/expected-output.txt`](demo/expected-output.txt).
Not yet run on Windows: rehearse once (Ctrl+C handling, the test glob, the Windows firewall prompt for `node.exe`
listening on 127.0.0.1: allow it before recording, off camera).

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Node.js 22+ | `node --version` (built on 22.23.5) | free |
| VS Code, Windows Terminal | dark theme, font 18 pt or larger | free |
| Two terminal panes | side by side, ~100 columns each | - |
| Masking | prompt and path only: use `function prompt { "> " }` in PowerShell | - |

## Setup
```powershell
cd C:\lab\mg-lab\series\programming-languages\episodes\09-javascript-node-js-patterns
function prompt { "> " }
npm test            # rehearsal: tests 26, pass 26, fail 0
```

## Screens (match the `screen` scenes in script.yaml)
1. **`screens/timings.jpg`** - *One at a time, five at a time, shared* (scene `timings`)
   - Left pane: `node src/cli.js serve --port 5090 --latency 300 --fail-first operations`
   - Right pane, one after another: `node src/cli.js intake samples/requests.csv --concurrency 1 --no-cache`,
     `... --concurrency 5 --no-cache`, `... --concurrency 5`
   - Frame: the three summary pairs (`9 ready, 5 rejected, 0 failed`, then `concurrency N, ... ms`). Times will differ from the
     reference (3641 / 711 / 691 ms); roughly 3.5 s, 0.7 s, 0.7 s is expected. The cached run must say `5 API calls, 5 shared`.
     Left pane shows `operations: 503 (first call fails on purpose)` then a 200: that is the retry.
2. **`screens/ctrlc.jpg`** - *Control C reaches the server* (scene `ctrlc`)
   - Restart the left pane with `--latency 1000`. Right pane: `node src/cli.js intake samples/requests.csv --concurrency 5 --no-cache`,
     Ctrl+C after about half a second, then `$LASTEXITCODE`.
   - Recorded with the kit (`record.json`, `Start-WtLayout.ps1`): the Ctrl+C is **sent, not pressed**. The right pane
     runs `Send-CtrlC -AfterMs 500 { node src/cli.js intake ... }`, typed on screen as is;
     `series/tools/rec/Send-CtrlC.ps1` generates a real CTRL_C_EVENT on that console 0.5 s after node starts, Node
     turns it into SIGINT and the client's own handler runs. The screen prepare rehearses it once off camera.
   - Frame: `stopped: interrupted (Ctrl+C)`, `130`, and five `ABORTED by the client` lines on the left.
3. **`screens/gotchas.jpg`** - *Four traps, one script* (scene `gotchas`)
   - `npm run -s gotchas` (about 1 s). Frame: all four numbered results.
4. **`screens/tests.jpg`** - *Tests without installing anything* (scene `tests`)
   - `npm test`, then VS Code with `tests/client.test.js` open at the test "a caller abort is passed through untouched...".
   - Frame: `tests 26`, `pass 26`, `fail 0`. Node prints the absolute path in failures only; passing output has none.

Stop the server with Ctrl+C between takes (it prints `SIGINT: closing, N calls served`).

## Tear-down
```powershell
Remove-Item -Recurse -Force out    # intake output folder
```
Nothing else was created: no node_modules (no dependencies), no cloud resources.
