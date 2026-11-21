# DEVLADLOG Code #10 - Performance profiling in Node.js: measure, don't guess

Series: `programming-languages` (DEVLADLOG Code). Blog: <https://www.devladlog.com/articles/programming-languages/2025-07-06-performance-profiling-complete-guide-2025/>

The Contoso approval report (project requests in; duplicate codes, formatted budgets and department totals out) exists in
two versions with identical output: `buildReportSlow`, written the usual way, and `buildReportFast`. Around them are the
tools you need to find out *why* the first one is slow, in plain ES modules on **Node 22, zero npm dependencies**:

- **A benchmark that is not lying** (`src/bench.js`): warm-up runs, many timed runs, median / min / p95, results kept alive.
- **A CPU profiler you can call from code** (`src/profiler.js`): `node:inspector/promises` `Profiler.start/stop` writes a
  `.cpuprofile`, the same format `node --cpu-prof` writes.
- **A `.cpuprofile` reader** (`src/cpuprofile.js`): self and total time per function (recursion counted once), and the
  **hot-lines view** from V8's `positionTicks`, with the source text next to the number.
- **Event loop delay** (`src/eventloop.js`): `perf_hooks.monitorEventLoopDelay` around a piece of work.
- **A leaking cache and its fix** (`src/cache.js`): unbounded `Map` vs a small LRU, measured with `--expose-gc`.
- **Tests that pin all of it**, including a test that the profile of the slow report really puts the `toLocaleString`
  line and the `seen.some(` line on top.

| Path | What it is |
|---|---|
| [`package.json`](package.json) | `"type": "module"`, Node >= 22, `imports` map, scripts (`test`, `check`, `bench`, `profile:slow`, `profile:fast`, `lag`, `memory`) |
| [`src/data.js`](src/data.js) | Seeded generator of fictional requests (same data on every machine, about 2 % repeated codes) |
| [`src/report.js`](src/report.js) | `buildReportSlow` (linear duplicate search, JSON deep copy, formatter per row) and `buildReportFast` |
| [`src/bench.js`](src/bench.js) | `bench`, `stats` |
| [`src/profiler.js`](src/profiler.js) | `profileToFile(fn, file)` |
| [`src/cpuprofile.js`](src/cpuprofile.js) | `summarize`, `hotLines`, `formatTop`, `formatHotLines`, `loadProfile` |
| [`src/eventloop.js`](src/eventloop.js) | `measureLoopLag(work)` |
| [`src/cache.js`](src/cache.js) | `createUnboundedCache`, `createLruCache`, `measureCache` |
| [`src/run-report.js`](src/run-report.js) | Plain script to profile with `node --cpu-prof` |
| [`src/cli.js`](src/cli.js) | `bench`, `profile <slow\|fast>`, `top <file>`, `lag <slow\|fast>`, `memory` |
| [`demo/one-run-benchmark.js`](demo/one-run-benchmark.js) | The same code timed twelve times in a row |
| [`demo/expected-output.txt`](demo/expected-output.txt) | Real captured output of everything above |
| [`tests/`](tests) | 14 tests in 3 files |

## Build, test, run

```bash
node --version                                   # 22 or later (built and tested on v22.23.5, Linux)
npm test                                         # node --test "tests/**/*.test.js"  ->  tests 14, pass 14, fail 0 (about 8 s)
node demo/one-run-benchmark.js                   # twelve timings of the same code
node src/cli.js bench --rows 2000 --runs 7       # slow vs fast, median / min / p95
node src/cli.js profile slow --rows 3000         # writes profiles/slow.cpuprofile, prints function and line tables
node src/cli.js profile fast --rows 30000        # ten times the rows
node src/cli.js lag slow --rows 3000             # event loop delay while the slow report runs
node --expose-gc src/cli.js memory               # 150,000 keys through an unbounded cache and an LRU
# no code of ours needed to get a profile:
node --cpu-prof --cpu-prof-dir=cpuprof src/run-report.js slow 3000
node src/cli.js top cpuprof/CPU.*.cpuprofile     # (PowerShell: node src/cli.js top (Get-ChildItem cpuprof\*.cpuprofile).FullName)
```
Nothing to install. Passed 14/14 in 6 consecutive runs of the final version. Not run on Windows (the recording laptop): the
code uses no platform-specific calls, but check once before recording. The container is a **shared, loaded machine**, so every
timing in `demo/expected-output.txt` is noisy (run 3 of the one-run demo took 71 ms for code that usually takes 1.4 ms).
The tests assert structure (which lines are hot, that the fast profile samples much less, that the loop lag is at least the
length of a blocking loop), never absolute speed.

## What we learned / gotchas
- **The function view hides the guilty code.** The slow report's profile says ~80 % of the time is in `buildReportSlow` itself,
  and the `seen.some(...)` callback shows as a separate `(anonymous)` entry with only ~13 %. V8 inlines small callbacks into the
  caller, and built-ins such as `toLocaleString` and `JSON.stringify` have no frame of their own, so their time lands on the
  caller. Every profile node has `positionTicks` (`[{ line, ticks }]`), and splitting the node's time by those ticks gives the
  real answer: in our capture line 36 (`toLocaleString`) about 51 %, line 30 (`seen.some`) about 37 %, the JSON copy line
  about 4 %. The team's first guess (the JSON clone) was the smallest of the three.
- **Creating a formatter is the expensive part.** In the `node --cpu-prof` capture of the slow run, loading `report.js` shows the one-time
  `new Intl.NumberFormat(...)` line with tens of milliseconds of self time: that is what `toLocaleString` pays on
  every row (it builds a formatter each call) and what the shared `euro.format()` avoids. (That claim comes from this one
  capture; I did not read V8's source.)
- **The duplicate check is quadratic.** Measured on this machine, the slow version took about 0.8 s for 4,000 rows and about 4.6 s
  for 12,000 (3x the rows, 5.5x the time), while the fast one stayed around 40 ms. A time that grows faster than the data is the
  signature to look for.
- **One timing proves nothing.** The same code timed twelve times ranged from 1.3 ms to 114 ms in one run on this shared box.
  `bench()` warms up, repeats and reports the median and p95.
- **`monitorEventLoopDelay` only records late timers after the blocking code returns.** `measureLoopLag` therefore waits
  a few timer ticks after the work before it reads the histogram. An idle loop still reads about 10 to 30 ms with a 10 ms timer
  here (the resolution plus scheduling noise): compare against that baseline, not against zero.
- **A fast profile of a fast function says nothing.** At 3,000 rows the fast version finishes in under 10 ms, so the 1 ms sampler
  mostly sees the inspector itself; profile it with ten times the rows (as the demo does).
- **`--expose-gc` is needed to measure heap honestly**: `process.memoryUsage().heapUsed` includes garbage that has not been
  collected yet. `heapUsedMb()` calls `gc()` first and throws a clear error if the flag is missing.
- **`.cpuprofile` file names are unique** (`CPU.<date>.<time>.<pid>.0.001.cpuprofile`), so scripts that open the file need a glob.
- Not verified here: VS Code's viewer for `.cpuprofile` (Learn documents opening a `.cpuprofile` in VS Code, but VS Code is
  not available in the build container), and anything on Windows.

## References
- [Diagnose high latency with CPU Insights (Visual Studio): Top Functions, Total CPU vs Self CPU, Hot Path](https://learn.microsoft.com/visualstudio/profiling/cpu-insights?view=visualstudio)
- [Analyze performance by using CPU profiling in the Performance Profiler (Visual Studio, .NET): the same method for managed code](https://learn.microsoft.com/visualstudio/profiling/cpu-usage?view=visualstudio)
- [Best practices and troubleshooting guide for Node.js applications on Azure App Service for Windows (collect a `.cpuprofile`, open it in Chrome DevTools)](https://learn.microsoft.com/troubleshoot/azure/app-service/app-service-web-nodejs-best-practices-troubleshoot-guide#nodejs-troubleshooting-scenarios-and-recommendations)
- [Performance in Scripting (Minecraft scripting docs): a `.cpuprofile` opens in Visual Studio Code and lists functions with cumulative time](https://learn.microsoft.com/minecraft/creator/documents/scripting/script-performance?view=minecraft-bedrock-stable#script-profiling)
- [Choose the right Node.js version for Azure (use LTS)](https://learn.microsoft.com/azure/developer/javascript/choose-nodejs-version)
- Node.js API docs (behaviour here was verified by running it): `--cpu-prof`, `node:inspector/promises`, `perf_hooks.monitorEventLoopDelay`
- Blog: [Performance Profiling - Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-07-06-performance-profiling-complete-guide-2025/)
