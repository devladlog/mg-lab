# Demo shot list - DEVLADLOG Code #10 Performance profiling

## Lab environment
| Item | What this episode needs |
|---|---|
| VMs / tenant / Azure | none. The screens show the real project on the laptop: Node.js, the V8 profiler, VS Code |
| Licences / cost | none |
| Recording machine | The Windows lab laptop (host): Node.js 22 LTS or later, VS Code, Windows Terminal with PowerShell 7, opened in the episode folder under a neutral path (e.g. `C:\lab\...`) |

Built and tested in the container (14 tests passed, every command below run there). **No tenant, no cloud resources.**
Reference output: [`demo/expected-output.txt`](demo/expected-output.txt). That capture comes from a shared, loaded container:
**the numbers on the laptop will differ** (it will be much quieter and faster). Before recording:
1. Run every command once and check the *shape* the narration describes: line 36 (`toLocaleString`) first and line 30
   (`seen.some`) second in the hot-lines table, the JSON line small, `buildReportSlow` at the top of the function table at
   about 80 %, the loop delay of the slow version in the hundreds of milliseconds, the LRU under 1 MB.
2. If the laptop is fast enough that a number in the narration is wrong (the hook says "a noticeable fraction of a second",
   the `after` scene says "six hundred" milliseconds, the memory scene says "about fifty megabytes"), change `--rows` (try
   5000) or edit the narration to the numbers on screen. Never read a number that is not on screen.
3. If the order of the top two lines is swapped on the laptop, say so in the take and swap the two sentences in the `profile`
   narration.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Node.js 22+ | `node --version` (built on 22.23.5) | free |
| VS Code | dark theme, font size 18 pt or larger, built-in `.cpuprofile` viewer (see screen 3: not verified in the container) | free |
| Terminal | dark theme, font 18 pt or larger, ~110 columns | - |
| Masking | prompt and path only: `function prompt { "> " }` in PowerShell | - |

## Setup
```powershell
cd C:\lab\mg-lab\series\programming-languages\episodes\10-performance-profiling
function prompt { "> " }
npm test                         # rehearsal: tests 14, pass 14, fail 0
node src/cli.js profile slow --rows 3000     # creates profiles\slow.cpuprofile, needed for screen 3
```
Close other heavy applications while recording: the benchmark and event-loop numbers are sensitive to a busy machine.

## Screens (match the `screen` scenes in script.yaml)
1. **`screens/onerun.jpg`** - *One timing proves nothing* (scene `onerun`)
   - `node demo/one-run-benchmark.js`. Frame: the twelve `run N` lines and the two summary lines. On a quiet laptop the spread may be
     small; if all twelve are within a few percent, say so in the take instead (or run it while a browser tab plays a video) and
     change the narration to match what is on screen.
2. **`screens/profile.jpg`** - *The profiler names the lines* (scene `profile`, also a Short)
   - `node src/cli.js profile slow --rows 3000`. Frame: both tables. The first table must show `buildReportSlow  report.js:25`
     on top; the second `report.js:36 ... toLocaleString` and `report.js:30 ... seen.some`.
3. **`screens/vscode-profile.jpg`** - *Open the .cpuprofile in VS Code* (scene `vscode`). Needs the laptop; **not captured in the container**.
   - Open `profiles\slow.cpuprofile` in VS Code. Learn documents that a `.cpuprofile` opens in VS Code and lists functions with
     cumulative time. If the built-in viewer does not appear on the laptop, say so in the take and drop this screen (the
     narration then needs one sentence less; Chrome DevTools > Performance/Profiles can load the same file).
   - Then in the terminal: `node --cpu-prof --cpu-prof-dir=cpuprof src/run-report.js slow 3000`, `dir cpuprof`
     (file name `CPU.<date>.<time>.<pid>.0.001.cpuprofile`), and `node src/cli.js top (Get-ChildItem cpuprof\*.cpuprofile).FullName`.
4. **`screens/after.jpg`** - *Before and after, with numbers* (scene `after`)
   - `node src/cli.js bench --rows 2000 --runs 7`, then `node src/cli.js lag slow --rows 3000`, then `node src/cli.js lag fast --rows 3000`.
   - Frame: slow median vs fast median, and the two `event loop delay max` figures. The idle baseline is about 10 to 30 ms.
5. **`screens/memory.jpg`** - *The cache that never forgets* (scene `memory`)
   - `node --expose-gc src/cli.js memory`. Frame: the `unbounded` and `lru(1000)` lines.

## Tear-down
```powershell
Remove-Item -Recurse -Force profiles, cpuprof
```
Nothing else was created: no node_modules (no dependencies), no cloud resources.
