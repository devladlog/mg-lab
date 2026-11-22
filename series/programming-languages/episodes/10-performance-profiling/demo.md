# Demo shot list - DEVLADLOG Code #10 Performance profiling

## Lab environment
| Item | What this episode needs |
|---|---|
| VMs / tenant / Azure | none. The screens show the real project on the laptop: Node.js, the V8 profiler, VS Code |
| Licences / cost | none |
| Recording machine | The Windows lab laptop (host): Node.js 22 LTS or later (the takes were recorded on v24.16.0), VS Code, Windows Terminal with PowerShell 7, opened in the episode folder under a neutral path (e.g. `C:\lab\...`) |

Built and tested in the container (14 tests passed, every command below run there). **No tenant, no cloud resources.**
Reference output: [`demo/expected-output.txt`](demo/expected-output.txt). That capture comes from a shared, loaded container:
**the numbers on the laptop will differ** (it will be much quieter and faster). Before recording:
1. Run every command once and check the *shape* the narration describes: line 36 (`toLocaleString`) first and line 30
   (`seen.some`) second in the hot-lines table, the JSON line small or absent, `buildReportSlow` at the top of the function
   table with most of the time, the loop delay of the slow version several times that of the fast one, the LRU under 1 MB.
   Recorded takes (laptop, Windows, Node v24.16.0): line 36 at 67.5 %, line 30 at 10.2 %, the JSON line not among the four
   lines listed, `buildReportSlow` at 85.6 %; loop delay max 91 ms slow and 25 ms fast; LRU +0.4 MB.
2. The narration quotes the recorded takes, so a retake with other numbers means editing the narration (or changing `--rows`)
   until it matches the screen again. Never read a number that is not on screen. What it quotes now:
   - hook: "about a tenth of a second" (3,000 rows built in 74 ms and in 113 ms; 92 ms sampled under the profiler)
   - `onerun`: "more than twice the median" (first run 2.82 ms, median 1.24 ms, 2.3x) and "about a fifth" (runs 5 to 12 stay
     between 1.04 and 1.30 ms)
   - `profile`: "two thirds" (line 36, 67.5 %), "about a tenth" (line 30, 10.2 %), the JSON clone "doesn't even make the list"
   - `vscode`: "a hundred and thirteen milliseconds", "ninety seven milliseconds of self time" (97.28 ms), "line thirty six
     first, then line thirty" (43.5 % and 17.5 % in that profile)
   - gotcha slide and narration: 86 % and 5 % (85.6 % and 5.2 % in the `profile` take)
   - `after`: "forty eight milliseconds to under one" (medians 48.1 and 0.8 ms), "ninety one" and "twenty five" (loop delay
     max in ms, slow and fast)
   - `memory`: "about fifty megabytes" (+52.8 MB) and "under a megabyte" (+0.4 MB)
3. If the order of the top two lines is swapped on the laptop, say so in the take and swap the two sentences in the `profile`
   narration.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Node.js 22+ | `node --version` (built and tested on v22.23.5 in the container; the takes were recorded on v24.16.0, Windows) | free |
| VS Code | dark theme, font size 18 pt or larger, built-in `.cpuprofile` viewer (see screen 3: VS Code is not available in the container; the recorded take shows the viewer) | free |
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
   - Recording kit (`record.json`, `Open-VsCodeScene.ps1`): the take is clicks only, so the two commands are VS Code
     tasks (Terminal > Run Task...; the task terminal echoes each command) and the file `node --cpu-prof` wrote is
     opened from the Explorer (no `dir`). Order on screen: `--cpu-prof` task, open the new file, `cli.js top` task.
   - Recorded take (laptop, Windows, Node v24.16.0): the built-in viewer appears ("CPU Profile Table Visualizer": Self Time,
     Total Time, File; `buildReportSlow` on top with 97.28 ms self time). The task panel is six rows high, so of the
     `cli.js top` output only the four line rows stay visible (`report.js:36` at 43.5 %, `report.js:30` at 17.5 %) and the
     function table scrolls off; the narration claims only the line view. The round account picture at the bottom of the
     activity bar is painted over in the render (`mask` on the `vscode` scene in script.yaml).
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
