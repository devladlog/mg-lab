# Demo shot list — DEVLADLOG Dev Tools #10, Performance profiling tools

Already real (build machine, 21 Nov 2026, Linux): the slow version as a patch and what it does to the tests (33 of 35 stay green, the two guards fail), the load, `dotnet-counters collect` (JSON),
`dotnet-trace collect --profile dotnet-sampled-thread-time --format Speedscope`, and the three summaries, all through `scripts/profile.sh` against a really running Release API (`test_e2e.py`).
Numbers in script.yaml come from a 100 000-order run on that machine. `dotnet test`: 35 passed, 4 skipped; `pytest`: 27 passed.
**Recorded here for the first time:** the same commands in Windows Terminal on the recording laptop, the live `dotnet-counters monitor` table, and **speedscope.app in a browser** with the Sandwich view.
Status: **needs the recording laptop**. No Azure, no tenant, no GitHub, no Docker.

## Lab environment

| What | Details | Cost |
|---|---|---|
| Recording laptop (Windows, the lab host) | .NET SDK 10 (`global.json`: 10.0.100, `rollForward: latestFeature`); Git for Windows (Git Bash gives `bash`, `patch`); Python 3 on the PATH (for `tools/*.py`); Windows Terminal; a browser (Edge or Chrome) for speedscope.app. All screens are recorded here. | none |
| Local tools | `dotnet tool restore` in `src/orders-app` installs `dotnet-counters` and `dotnet-trace` 10.0.750501 from NuGet (pinned in `.config/dotnet-tools.json`). | none |
| Data | `Orders__SeedCount=100000` seeds 100 000 fictional orders (customers such as contoso) into a throwaway SQLite file, about 6 MB. | none |
| Port | `5080` in every command below. | none |
| speedscope.app | Not a Microsoft product (Learn's dotnet-trace page names it as the viewer for the Speedscope format). It reads the file in the browser. If the laptop has no internet access during the recording, use Visual Studio's profiler to open the `.nettrace` instead (Learn says it opens `.nettrace` files); **not verified here**. | none |

Close other heavy programs first: the numbers are only comparable when the machine is quiet. Record the **same run twice** if the first one is noisy; the ratios matter, not the exact milliseconds.

## Prepare (before recording, off camera)

```bash
# Git Bash, from a clone of mg-lab on the laptop. Everything is copied to C:\work so the clone stays clean.
cd series/developer-tools/episodes/10-performance-profiling-tools
mkdir -p /c/work && cp -r src/orders-app /c/work/orders-perf && cp bugs/01-load-everything.patch /c/work/
cd /c/work/orders-perf && dotnet tool restore && dotnet test -m:1        # 35 passed, 4 skipped
patch -p1 < ../01-load-everything.patch                                   # the slow version (33 of 35 still pass, the guards fail)
dotnet build src/Contoso.Orders.Api -c Release                            # Release: a Debug build measures the Debug build
```

Not verified on the build machine: everything on Windows (the scripts ran on Linux; `profile.sh` needs `bash`, so use Git Bash), `dotnet-counters monitor`'s live table (only `collect` was run),
and speedscope.app itself (the converter's output was analysed with `tools/speedscope_top.py`, not opened in a browser). If `dotnet-trace` or `dotnet-counters` cannot attach on Windows without elevation, run the terminal as the same user as the API.

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/counters.jpg` — Windows Terminal · dotnet-counters**
   ```bash
   cd /c/work/orders-perf
   ASPNETCORE_URLS=http://localhost:5080 ASPNETCORE_ENVIRONMENT=Production Orders__SeedCount=100000 \
     ConnectionStrings__Orders="Data Source=perf.db" dotnet src/Contoso.Orders.Api/bin/Release/net10.0/Contoso.Orders.Api.dll &
   dotnet tool run dotnet-trace ps                          # find the pid of Contoso.Orders.Api (dotnet-counters ps works too)
   python tools/load.py http://localhost:5080 --seconds 60 &   # tab 1: the load, cache emptied before every request
   dotnet tool run dotnet-counters monitor -p <pid> --counters System.Runtime     # tab 2: the live table
   bash scripts/profile.sh http://localhost:5080 <pid> 15      # the file version, ends with the counters summary line
   ```
   - Capture: the live table (allocation rate, GC collections per generation, GC pause time) moving while the load runs, then the line `window 14 s: ... allocated 813 MB ... GC pause 5.5 s ... gen0/gen1/gen2 ...`. The numbers will differ from the script: say your own.
   - Mask: nothing (no accounts).

2. **`screens/trace.jpg` — Windows Terminal + speedscope.app**
   - The `dotnet-trace collect` line from `scripts/profile.sh` (profile `dotnet-sampled-thread-time`, `--format Speedscope`) and the resulting `profile/trace.speedscope.json`.
   - Browser: https://www.speedscope.app, drag `trace.speedscope.json` in (it is read locally). Pick the busiest thread, switch to **Sandwich**, sort by **Self**: the SQLite and change-tracking frames are at the top.
   - Terminal next to it: `python tools/speedscope_top.py profile/trace.speedscope.json --top 6 --match Reports.MonthlyRevenueAsync` (`Busy thread time in the trace`, the top self frames, and the inclusive share of `Reports.MonthlyRevenueAsync`).
   - Say on camera that the expected culprit, formatting the date text, is not in the list.

3. **`screens/after.jpg` — Windows Terminal · the same load, new build**
   ```bash
   cd /c/work/orders-perf && kill <pid>                       # stop only the API started above
   python tools/load.py http://localhost:5080 --requests 30   # first, on the slow build (cache emptied each time): note p50 / p95
   patch -R -p1 < ../01-load-everything.patch && dotnet build src/Contoso.Orders.Api -c Release
   ASPNETCORE_URLS=http://localhost:5080 ASPNETCORE_ENVIRONMENT=Production Orders__SeedCount=100000 \
     ConnectionStrings__Orders="Data Source=perf.db" dotnet src/Contoso.Orders.Api/bin/Release/net10.0/Contoso.Orders.Api.dll &
   python tools/load.py http://localhost:5080 --requests 30   # the fixed build, same database file
   dotnet test -m:1 --filter "FullyQualifiedName~ReportPerformanceTests"    # 3 passed (and with the patch applied: 2 failed, with the byte counts)
   ```
   - Capture: both `load.py` lines side by side (the script says 1846 / 2908 ms before and 20 / 50 ms after: expect the same order of magnitude, say your own), then the guard tests green. Optionally show the red message `one report allocated ... bytes ... the budget is 1,000,000` from the patched build.

## Optional b-roll (not scripted, not verified)

Visual Studio's **Performance Profiler** (Alt+F2, CPU Usage) on the same Release API: Learn says it gives per-function Total and Self CPU, and can open `.nettrace` files from `dotnet-trace`. Only if Visual Studio is installed and licensed; nothing in the script depends on it.

## Tear-down

- `kill <pid>` for the API you started (Git Bash) or end that one `Contoso.Orders.Api` process in Task Manager; do not stop other `dotnet` processes.
- `rm -rf /c/work/orders-perf /c/work/01-load-everything.patch` (the `profile/` folder with the `.nettrace` and `.speedscope.json` files is inside; `perf.db` too).
- Close the speedscope.app tab (nothing was uploaded).
- Repo working copy: nothing was edited; `git status` must be clean (`bin/`, `obj/`, `profile/`, `*.db`, `*.nettrace` and `*.speedscope.json` are git-ignored).
