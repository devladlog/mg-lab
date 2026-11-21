# DEVLADLOG Dev Tools #10 — Performance profiling: measure first, then fix the right line

The orders API from [episode 9](../09-debugging-techniques/) has its monthly revenue report (`GET /reports/monthly?month=2026-03`), and this
time the report is **correct and slow**: every test is green, and with 100 000 orders one request takes about two seconds. The episode is the
loop that finds out why without guessing: a **repeatable load** (p50 and p95), **`dotnet-counters`** (allocations, GC), **`dotnet-trace`** into a
**Speedscope** file (where the threads are busy), **one fix**, the same load again, and **a guard that counts queries and bytes instead of seconds**.

```
 "the report takes 2 s, all tests are green"
   1  load:      tools/load.py   (cache emptied before every request)          p50 1846 ms   p95 2908 ms     ── the number to beat
   2  counters:  dotnet-counters collect ... System.Runtime               ──►  813 MB allocated in 14 s, GC pause 5.5 s, 10 gen2 collections
   3  trace:     dotnet-trace collect --profile dotnet-sampled-thread-time --format Speedscope
                                                                           ──►  84% inside ToListAsync (SQLite reads, change tracking), 0.1% in the date formatting I suspected
   4  fix:       filter and group in SQL, AsNoTracking                         ──►  p50 20 ms   p95 50 ms   (filter in SQL only: 128 / 271 ms)
   5  guard:     ReportPerformanceTests: one SQL command with WHERE and GROUP BY, an allocation budget (slow 6.4 MB, fixed 0.35 MB, budget 1 MB)
```

The shipped code is the **fast** version. **The slow version is a patch in [`bugs/`](bugs/)**, applied for the recording (and by the tests), so the folder
in the repository always builds green.

| Path | What it is |
|---|---|
| [`src/orders-app/src/Contoso.Orders.Api/Reports.cs`](src/orders-app/src/Contoso.Orders.Api/Reports.cs) | `Reports.MonthlyRevenueAsync`: a half-open date range and the grouping in SQL, `AsNoTracking`. Episode 9's `ReportCache` and log messages are unchanged |
| [`bugs/01-load-everything.patch`](bugs/01-load-everything.patch) | The slow version: `db.Orders.ToListAsync()` (every order, tracked), filter by formatting each date as text, group in memory. 1 file, answers are identical |
| [`src/orders-app/tools/load.py`](src/orders-app/tools/load.py) | The load: `POST /reports/cache/invalidate`, then a timed `GET /reports/monthly?month=2026-MM`, N workers; prints p50 / p95 / max, exit 1 on any failed request |
| [`src/orders-app/tools/counters_summary.py`](src/orders-app/tools/counters_summary.py) | Reads a `dotnet-counters collect --format json` file: allocated MB, GC pause, collections per generation, working set, request duration |
| [`src/orders-app/tools/speedscope_top.py`](src/orders-app/tools/speedscope_top.py) | Reads the `.speedscope.json` that `dotnet-trace` writes: busy time per method, self and inclusive (the terminal version of Speedscope's Sandwich view) |
| [`src/orders-app/scripts/profile.sh`](src/orders-app/scripts/profile.sh) | The whole measurement on a running API: load + `dotnet-counters collect` + `dotnet-trace collect`, then the three summaries |
| [`src/orders-app/.config/dotnet-tools.json`](src/orders-app/.config/dotnet-tools.json) | Local tool manifest: `dotnet-counters` and `dotnet-trace` 10.0.750501, pinned (`dotnet tool restore`) |
| [`src/orders-app/tests/`](src/orders-app/tests/) | Episode 8/9's xUnit tests plus `ReportPerformanceTests` (the guard): 35 pass, 4 skip |
| [`tests/`](tests/) | 27 pytest tests, `fixtures/counters-slow.json` is a real capture (124 KB) |

## Run the tests

```bash
cd series/developer-tools/episodes/10-performance-profiling-tools
(cd src/orders-app && dotnet test -m:1)            # Passed! 35 passed, 4 skipped (the SQL Server tests: no SQL Server here)
python3 -m pytest -q tests                          # 27 passed (about 2 min: real Release builds, a real load, a real trace)
```

Needs .NET SDK 10, `bash`, GNU `patch`, Python 3 with `pytest` and `pyyaml`, and NuGet access for `dotnet tool restore`. Everything that builds runs in temporary copies.

| Test file | What it proves |
|---|---|
| `src/orders-app/tests/.../ReportPerformanceTests.cs` (3) | On a 20 000-row SQLite file: the report is **one** SQL command containing `WHERE` and `GROUP BY` (captured with an EF `DbCommandInterceptor`); one report allocates less than 1 000 000 bytes (`GC.GetTotalAllocatedBytes(precise: true)` around a second call, after a warm-up); the numbers equal plain LINQ over the seed. Runs in a no-parallel collection |
| `test_patch.py` (3) | The patch applies and touches only `Reports.cs`; the shipped code is the fast version. **With the patch, the 33 other xUnit tests stay green and exactly the two guards fail**, with the message `one report allocated 6,355,072 bytes for 20,000 orders in the table, the budget is 1,000,000` (fixed code: 346,128 bytes) |
| `test_tools.py` (13) | `load.py` percentiles, `summarize`, empties the cache before every request (a local HTTP server records the order), exit 1 on failures; `speedscope_top.py` counts only `CPU_TIME` intervals and never reports the pseudo frames (synthetic evented and sampled files), exit 1 on an idle trace; `counters_summary.py` on the real capture (813.2 MB, 5.54 s GC pause, 12/2/10 collections, 353 MB) |
| `test_e2e.py` (3) | **The episode for real**, 50 000 orders: builds slow and fixed in Release, runs `scripts/profile.sh` against each (load, `dotnet-counters`, `dotnet-trace`). The slow p50 is more than 3 times the fixed one; the trace puts more than 50% of busy time inside `Reports.MonthlyRevenueAsync` with SQLite frames in the top self list; the slow build's GC pause is longer than the fixed build's (2.1 s vs 0.13 s in one run, 2.3 s vs 0.45 s in another) |
| `test_script.py` (8) | `script.yaml`: header, 12–16 scenes, 750–900 words, three shorts, code excerpts are real lines of the patch, `Reports.cs` and the test, and the counters, p50/p95 and trace numbers on screen are the ones the fixture and tools produce |

## Use it

```bash
cd src/orders-app
dotnet build src/Contoso.Orders.Api -c Release                    # measure Release: a Debug build measures the Debug build
patch -p1 < ../../bugs/01-load-everything.patch                    # the slow version (patch -R -p1 to undo; git apply works too)
dotnet build src/Contoso.Orders.Api -c Release
ASPNETCORE_URLS=http://localhost:5080 Orders__SeedCount=100000 ConnectionStrings__Orders="Data Source=perf.db" \
  dotnet src/Contoso.Orders.Api/bin/Release/net10.0/Contoso.Orders.Api.dll &
python3 tools/load.py http://localhost:5080 --requests 30            # p50 / p95
scripts/profile.sh http://localhost:5080 <pid> 15                    # counters + trace + the three summaries, files in profile/
# open profile/trace.speedscope.json in https://www.speedscope.app (the page reads the file in the browser)
```

## Measured (build machine, 21 Nov 2026, SDK 10.0.115, Release, 100 000 orders, 2 shared CPUs)

| | p50 | p95 |
|---|---|---|
| slow (`bugs/01`) | 1846 ms | 2908 ms |
| filter in SQL, still loads every order of the month, tracked | 128 ms | 271 ms |
| shipped: filter and group in SQL, `AsNoTracking` | 20 ms | 50 ms |

The machine was shared with other builds, so these are an **order of magnitude, not a benchmark**; run it again and the milliseconds move.
The ratios are what held every time. Slow-build counters over 14 s (real capture, `tests/fixtures/counters-slow.json`): 813.2 MB allocated, GC pause 5.54 s, 12 / 2 / 10 gen0 / gen1 / gen2
collections, working set 353 MB. The 100 000 rows are `Orders__SeedCount=100000` on a SQLite file (about 6 MB).

## What we learned / gotchas

- **The hunch was wrong, the trace was right.** I expected the cost to be formatting a date into text for every order (the slow code does that). In the trace `DateOnly.ToString` is 0.1% of busy time;
  84% is inside `ToListAsync`: SQLite reading rows (`sqlite3_data_count`, `SqliteDataReader.GetInt32`, `SqliteDataRecord.Read`) and the change tracker (`StateManager.StartTracking`). Learn's EF page says the same in general
  terms: tracking queries keep a dictionary of instances and a snapshot of each, and in read-only scenarios no-tracking queries avoid that.
- **A cached answer measures nothing.** The report is cached per month (episode 9). `load.py` posts `/reports/cache/invalidate` before every request; without it only the first request per month is slow.
- **Release, not Debug.** Learn (Debug ASP.NET Core apps, and the Visual Studio profiler overview): measure a Release build. `profile.sh` and every command here use `-c Release`.
- **Tracing is not free.** The server-side request p50 in the counters (3726 ms) is higher than the load script's p50 for the same run (2683 ms in the profiled run): the trace was running. Compare runs that were measured the same way.
- **`dotnet-trace` profile name.** The profile that gives thread time is `dotnet-sampled-thread-time`; `dotnet-sampled-cpu` and `cpu-sampling` are not valid on 10.0.750501 (the tool says so). `--format Speedscope` writes `<name>.speedscope.json` next to the `.nettrace`.
  Learn's dotnet-trace page: the Speedscope file opens at speedscope.app; speedscope is not a Microsoft product.
- **What the Speedscope file contains.** With this profile each thread is an "evented" profile whose stacks end in a pseudo frame, `CPU_TIME` or `UNMANAGED_CODE_TIME`. In the files from this episode, threads that wait end in
  `UNMANAGED_CODE_TIME` and threads running managed code (calls into SQLite included) end in `CPU_TIME`. **Those two labels are the converter's; I did not find them on Learn**, so `speedscope_top.py` calls the result "busy thread time", not CPU seconds. It adds all threads up, so it can exceed the wall-clock window (31.5 s of busy time in a 15 s trace).
- **`dotnet-counters collect --duration`.** Learn's dotnet-counters page does not list `--duration` under `collect`; the installed tool's `--help` (10.0.750501) does, with the `dd:hh:mm:ss` format `profile.sh` uses. Rates are exported per refresh interval (1 s), so the sum of a rate over the file is the total for the window.
- **MB per second is not the comparison.** A fast server answers more requests per second, so under the same load both builds allocated at about the same rate in one of two runs (44.0 vs 44.1 MB/s; 327 vs 86 MB/s in the other). Compare GC pause, or bytes per request (what the guard test does).
- **Wall-clock budgets flake, counts do not.** The guard asserts what the query is (one command, `WHERE`, `GROUP BY`) and how many bytes one report allocates. The budget (1 MB) sits between the fixed code (0.35 MB) and the slow code (6.4 MB) on a 20 000-row table; it measures allocations of the calling thread and the test collection runs without parallelism, so other tests do not add to it. I did not try other runtimes or operating systems.
- **The functional tests cannot see it.** With the patch applied, 33 of 35 tests pass and the answers are identical. A report that is slow is not wrong; only a test that measures something other than the answer can fail.
- **EF Core translated the grouping on SQLite.** `GroupBy(o => o.Customer).Select(g => new RevenueRow(g.Key, g.Count(), g.Sum(o => o.Total)))` runs as one SQL statement (the guard asserts one command with `GROUP BY`) and its totals equal plain LINQ over the seed.
- **Not done:** a BenchmarkDotNet micro-benchmark (heavy on a shared 2-CPU machine) and a Visual Studio profiler session (no Visual Studio here). Learn lists both; nothing in this episode depends on them. The `dotnet-counters` capture of the **fixed** build was not stored as a fixture; the end-to-end test measures it each run.

## References
- Blog: [Performance Profiling Tools — Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-20-performance-profiling-tools-complete-guide-2025/)
- Microsoft Learn: [dotnet-trace](https://learn.microsoft.com/dotnet/core/diagnostics/dotnet-trace) (`collect`, profiles, `--format Speedscope`) ·
  [dotnet-counters](https://learn.microsoft.com/dotnet/core/diagnostics/dotnet-counters) (`collect`, `--format json`, `--counters`) ·
  [Runtime metrics](https://learn.microsoft.com/dotnet/core/diagnostics/built-in-metrics-runtime) (`dotnet.gc.*`, `dotnet.process.*`) ·
  [.NET profiling tools](https://learn.microsoft.com/dotnet/core/diagnostics/profilers) (Visual Studio profiler and dotnet-trace) ·
  [Overview of the profiling tools](https://learn.microsoft.com/visualstudio/profiling/profiling-feature-tour?view=visualstudio) (Release builds; dotnet-trace gives sampling results) ·
  [Efficient querying (EF Core)](https://learn.microsoft.com/ef/core/performance/efficient-querying) (tracking overhead, project only what you need) ·
  [Tracking vs. no-tracking queries](https://learn.microsoft.com/ef/core/querying/tracking) ·
  [Client vs. server evaluation](https://learn.microsoft.com/ef/core/querying/client-eval) (what happens when a filter cannot run in the database) ·
  [Local tools](https://learn.microsoft.com/dotnet/core/tools/local-tools-how-to-use) (`dotnet tool restore`, `dotnet tool run`)
- Not Microsoft: [speedscope](https://www.speedscope.app) (the viewer for `.speedscope.json`)
- Packages: `dotnet-counters` and `dotnet-trace` 10.0.750501 (local tools, pinned); EF Core 10.0.15 and `Microsoft.Data.Sqlite` as in episode 8
