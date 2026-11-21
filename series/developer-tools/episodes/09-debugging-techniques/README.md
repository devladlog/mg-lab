# DEVLADLOG Dev Tools #9 — Debugging techniques: find the bug, not the person who wrote it

The orders API from [episode 8](../08-api-testing-with-postman/) (the one episodes 4 and 5 ship and whose tests we ran) gets a
**monthly revenue report** (`GET /reports/monthly?month=2026-01`), and then two things go wrong with it. The episode is how you find
each one: a **failing test** as the reproduction, **`git bisect run`** to find the commit, the **VS Code debugger** (launch
configuration, breakpoints, a logpoint, a conditional breakpoint), **one request out of the logs** by trace id, and a **hang**
read from `dotnet-stack` and `dotnet-dump`.

```
 "January is missing orders"   (no exception, no crash)
   1  test:     MonthEnd_orders_are_part_of_the_month   Expected: 30  Actual: 29         ── the reproduction
   2  bisect:   git bisect run scripts/bisect-repro.sh  ── 6 commits, 2 test runs ──►  "refactor(reports): compute the last day ..."
   3  debugger: F5 "Orders API (debug)" ── breakpoint after the query, Watch, logpoint, condition ──► the 31st is not in `orders`
   4  logs:     problem details "traceId" ──► tools/trace_lines.py ──► the log lines of that one request
 "two requests never answer, /healthz is green"
   5  hang:     scripts/triage-hang.sh <pid>  ── dotnet-stack (all threads) ── dotnet-dump (syncblk, clrstack -all) ──► two locks, opposite order
```

The healthy code is what `src/orders-app` contains. **The two bugs are patches in [`bugs/`](bugs/)**, applied for the recording (and by the
tests), so the folder in the repository always builds green and the bugs can be switched on and off in one command.

| Path | What it is |
|---|---|
| [`src/orders-app/src/Contoso.Orders.Api/Reports.cs`](src/orders-app/src/Contoso.Orders.Api/Reports.cs) | `Reports.MonthlyRevenueAsync` (a month is a half-open range), `ReportCache` (two locks, one rule: `_entries` first, then `_stats`), source-generated log messages (`[LoggerMessage]`) |
| [`src/orders-app/src/Contoso.Orders.Api/Program.cs`](src/orders-app/src/Contoso.Orders.Api/Program.cs) | Episode 8's API plus `GET /reports/monthly`, `GET /reports/cache`, `POST /reports/cache/invalidate`; `Orders:Cache:HoldMs` (0 = off) stands in for a database call made while a lock is held |
| [`src/orders-app/src/Contoso.Orders.Api/Orders.cs`](src/orders-app/src/Contoso.Orders.Api/Orders.cs) | Episode 8's model, with `[DebuggerDisplay("Order {Id}: {Customer}, {Total} on {Created}")]` on `Order` |
| [`bugs/01-month-end-off-by-one.patch`](bugs/01-month-end-off-by-one.patch) | "refactor: compute the last day of the month once": the range ends *before* the last day. 5 changed lines |
| [`bugs/02-lock-order-deadlock.patch`](bugs/02-lock-order-deadlock.patch) | `Snapshot()` takes the two locks in the opposite order from `Invalidate()`. 2 changed lines |
| [`bugs/make-history.sh`](bugs/make-history.sh) | Builds the throwaway repository for the bisect demo: 7 commits, tag `demo-good`, the bug in the 4th |
| [`src/orders-app/scripts/bisect-repro.sh`](src/orders-app/scripts/bisect-repro.sh) | What `git bisect run` calls: build (exit 125 = skip), run exactly the reproduction test, exit 0 / 1 / 125 |
| [`src/orders-app/scripts/triage-hang.sh`](src/orders-app/scripts/triage-hang.sh) | `dotnet-stack report`, a dump with heap, `syncblk` and `clrstack -all`; keeps `stacks.txt`, `analysis.txt`, `hang.dmp` in `triage/` (git-ignored) |
| [`src/orders-app/tools/trace_lines.py`](src/orders-app/tools/trace_lines.py) | Reads the API's JSON logs on stdin, prints the lines of one trace id (accepts the 32-character id or the `00-…-…-01` value from the error body) |
| [`src/orders-app/.config/dotnet-tools.json`](src/orders-app/.config/dotnet-tools.json) | Local tool manifest: `dotnet-stack` and `dotnet-dump` 10.0.750501, pinned (`dotnet tool restore`) |
| [`src/orders-app/.vscode/`](src/orders-app/.vscode/) | `launch.json` (launch + attach), `tasks.json` (the `build` task), `orders.http` (REST Client requests), `extensions.json` |
| [`src/orders-app/tests/`](src/orders-app/tests/) | Episode 8's xUnit tests plus `ReportsTests` (the reproduction, "every order lands in exactly one month", cache, problem details), `ReportCacheTests` (the deadlock guard, with a timeout), `DebuggerDisplayTests`: 35 pass, 4 skip |
| [`tests/`](tests/) | 35 pytest tests (below) |

## Run the tests

```bash
cd series/developer-tools/episodes/09-debugging-techniques
(cd src/orders-app && dotnet test)                 # Passed! 35 passed, 4 skipped (the SQL Server tests: no SQL Server here)
python3 -m pytest -q tests                          # 35 passed (~5.5 min: real builds, real git bisect, a real hang and a real dump)
```

Needs .NET SDK 10, `git`, `bash`, GNU `patch`, Python 3 with `pytest` and `pyyaml`, and NuGet access for `dotnet tool restore`
(the hang test skips, loudly, if the restore fails or the environment forbids reading process memory). Everything runs in temporary
copies, so `src/orders-app` never gets `bin/`, `obj/`, databases or dumps.

| Test file | What it proves |
|---|---|
| `test_bugs.py` (7) | Both patches apply to the shipped source and touch only `Reports.cs`. **Patch 01 turns exactly two tests red** (`MonthEnd_orders_are_part_of_the_month`: Expected 30, Actual 29; `Every_order_lands_in_exactly_one_month`: Expected 237, Actual 230) and nothing else (2 failed, 33 passed, 4 skipped). **Patch 02, for real:** the healthy API answers `POST /reports/cache/invalidate` (204) and `GET /reports/cache` (200) at the same time in under 5 s; the patched API (with `HoldMs=50`) times out on both while `/healthz` and `/orders` still answer 200 and the next `GET /reports/cache` hangs too. The xUnit deadlock guard fails on the patched source with its message instead of hanging |
| `test_bisect.py` (3) | **A real `git bisect run`**: `bugs/make-history.sh` builds the 7-commit repository, bisect names the refactor commit in 2 test runs (6 commits after the good one), prints the 5-line stat, leaves the repository in the bisect state until `git bisect reset`. The script exits **125** for a commit that does not build and for a commit where the test does not exist, and `dotnet test --filter` on its own exits 0 for the missing test (the trap). `make-history.sh` refuses a folder that is not empty |
| `test_logging.py` (9) | A real run of the API with JSON logs and scopes: a caller's `traceparent` comes back inside the problem details `traceId`; the rejected-month Warning is found with that value through `tools/trace_lines.py`; the successful request is found by its bare 32-character id; the scopes carry `TraceId`, `SpanId`, `ParentId`, `RequestId`, `RequestPath`, `ConnectionId`; a request without a header gets its own trace id; the tool's parsing, plain-text lines, null scopes and exit codes 0/1/2 |
| `test_vscode.py` (6) | `launch.json` has the launch and the attach configuration; `preLaunchTask` exists and is `dotnet build` of the API project; `program` is where the build puts the dll; every non-`ASPNETCORE_` variable in `env` is a setting `Program.cs` reads; `orders.http` matches the routes. **Runs the `build` task command and starts the built program with the launch configuration's environment**, then sends the `.http` requests (200, 400, 200, 204) |
| `test_hang_triage.py` (2) | The tool manifest pins exact versions. **`scripts/triage-hang.sh` against the real deadlocked API**: `dotnet-stack` shows two threads in `Monitor.Enter`, one in `Invalidate`, one in `Snapshot`; a heap dump is written (>10 MB); `syncblk` lists two monitors with two different owning threads; `clrstack -all` gives `Reports.cs @ <line>` for both |
| `test_script.py` (8) | `script.yaml`: header, 12–16 scenes, 750–900 words, three shorts, code excerpts are real lines of the real files, and every number or output on screen is one the tests above assert |

## Use it

```bash
cd src/orders-app
dotnet run --project src/Contoso.Orders.Api        # http://localhost:5000 by default; the launch configuration uses :8080
curl "http://localhost:8080/reports/monthly?month=2026-01"

# switch a bug on / off
patch -p1 < ../../bugs/01-month-end-off-by-one.patch        # or: git apply ../../bugs/01-month-end-off-by-one.patch
patch -R -p1 < ../../bugs/01-month-end-off-by-one.patch

# bisect, on a throwaway repository
bash ../../bugs/make-history.sh /tmp/orders-history && cd /tmp/orders-history
git bisect start HEAD demo-good && git bisect run scripts/bisect-repro.sh ; git bisect reset

# a hang: patch 02, 50 ms "database call" under the lock, two requests at once, then
Orders__Cache__HoldMs=50 dotnet src/Contoso.Orders.Api/bin/Debug/net10.0/Contoso.Orders.Api.dll &
curl -X POST http://localhost:5000/reports/cache/invalidate & curl http://localhost:5000/reports/cache &
scripts/triage-hang.sh <pid>

# one request out of the logs (container logs work the same)
Logging__Console__FormatterName=json Logging__Console__FormatterOptions__IncludeScopes=true dotnet run ... 2>&1 | python3 tools/trace_lines.py <traceId>
```

## What we learned / gotchas

- **`dotnet test --filter` that matches nothing exits 0.** It prints `No test matches the given testcase filter` and succeeds. A bisect script that only
  looks at the exit code reports every commit from before the test existed as *good* and the search ends in the wrong place. `bisect-repro.sh` requires
  `Passed: 1` or `Failed: n` in the output, and exits **125** (skip) otherwise. git's manual: exit 0 = good, 1–127 except 125 = bad, **125 = "cannot be tested", the
  revision is skipped**, any other code aborts the bisect. A commit that does not build gets 125 for the same reason.
- **The `traceId` in a problem details body is not the trace id.** It is `Activity.Id`, the W3C traceparent form `00-<32 hex trace id>-<16 hex span id>-<flags>`
  (checked by running it: the value is `00-<the caller's trace id>-<the server's own span>-01`). The JSON log lines carry the bare 32 characters in the `TraceId` scope, and a
  *different* span id. Searching the logs for the whole value finds nothing. Learn's error-handling page shows the same shape in its sample (`"traceId":"00-b644<snip>-00"`)
  without saying what it holds. `trace_lines.py` takes both forms.
- **Scopes are on by default, printing them is not.** Learn: `SpanId`, `TraceId`, `ParentId` are enabled by default (`ActivityTrackingOptions`). They only appear in the console output with the
  JSON formatter (`Logging:Console:FormatterName=json`) **and** scopes switched on. I ran it with `Logging:Console:FormatterOptions:IncludeScopes=true`; Learn's scopes page shows
  `Logging:Console:IncludeScopes` for the console provider, and I did not test whether that key alone also works with the JSON formatter. Each line then carries `TraceId`, `SpanId`, `ParentId`, `ConnectionId`, `RequestId`, `RequestPath` in `Scopes`.
- **A mini dump is not enough for `syncblk`.** `dotnet-dump collect --type Mini` (24 MB for this tiny API) analyzes fine for `clrstack -all` (with file and line numbers, because the pdb is next
  to the dll) but `syncblk` answers `Error requesting SyncBlk data`. `--type Heap` (232 MB) answers. Learn's table: `Full` (default) is the largest, `Heap` has everything except mapped images, `Mini`
  has modules, threads, exceptions and stacks, **`Triage` is a small dump with PII removed** (not tried here). A dump is a copy of the process memory: customer names, connection strings. `.gitignore` has `*.dmp`; the script says "delete hang.dmp when done".
- **A deadlock is local, and the health check stays green.** With patch 02 only requests that need both locks hang; `/healthz`, `/orders` answer 200 (asserted). Everything that tests "is the process up" is happy.
  After the first two stuck requests, every later `GET /reports/cache` waits too (asserted). I did **not** measure how often it hangs with `HoldMs=0`: the window is then microseconds.
  `HoldMs` exists so the demo is certain, not random.
- **A test that can hang needs a timeout.** `Invalidate_and_Snapshot_at_the_same_time_do_not_deadlock` waits 20 s for both threads (`Task.WhenAny`) and fails with a message that names the cause; the
  threads are background threads, so the test host still exits. Without the timeout the test run itself hangs.
- **Reading a process needs ptrace.** Here (root, no container) `dotnet-stack` and `dotnet-dump` just worked. Learn's container page: `dotnet-dump` runs a helper process that needs ptrace permissions
  (`--cap-add=SYS_PTRACE`, sometimes a seccomp change); the tools can run in the container, from the host or from a sidecar, and a sidecar needs a **shared process namespace** and the **shared `/tmp`**
  (the diagnostic socket). Episode 4's image is the chiseled one: no shell, no package manager, so there is nothing to `docker exec` into: use the sidecar/host route. **Not verified here (no Docker).**
- **`dotnet new tool-manifest` put the file in the project root.** Learn says `.config/dotnet-tools.json`; SDK 10.0.115 here wrote `dotnet-tools.json` next to the solution. I moved it to `.config/` and
  `dotnet tool restore` / `dotnet tool list` find it (tested).
- **EF Core 10 on SQLite sums `decimal` in SQL.** A `GroupBy(...).Select(g => g.Sum(o => o.Total))` ran without error here (I had expected the old "SQLite cannot translate Sum over decimal" limitation).
  The report still groups in memory: one month is small. (Episode 10 uses this.)
- **Launch and attach in VS Code (needs the recording laptop).** VS Code's docs: conditional breakpoints stop when an expression is true (also hit count and "wait for breakpoint"); a **logpoint "writes a message to the
  Debug Console without pausing execution"**, expressions in curly braces. The C# Dev Kit page says attaching is the Command Palette command *Debug: Attach to a .NET 5+ or .NET Core process*; it does not show a
  `request: "attach"` entry, so the `attach` configuration (`"processId": "${command:pickProcess}"`) is **not verified** until the recording. The C# debugger settings page lists `program`, `cwd`, `env`, `justMyCode`,
  `serverReadyAction`, `pipeTransport` (with `ssh` as its example, not Docker) and `symbolOptions`; `justMyCode` is on in both entries.
- **`[DebuggerDisplay]`** takes names in braces (field, property or method); Learn recommends against general expressions (slow, can change state) and shows the private `DebuggerDisplay` property with `,nq` as the safe pattern. The test checks
  that every `{name}` is a real member of `Order`.
- **C# Dev Kit licence.** Learn: it uses Visual Studio's licence model: free for individuals, academia and open source; for organizations it is included with Visual Studio Professional and Enterprise subscriptions. Check this before recording in a company
  setting; see [demo.md](demo.md) for the fallback.

## References
- Blog: [Debugging Techniques — Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-13-debugging-techniques-complete-guide-2025/)
- Microsoft Learn: [dotnet-dump](https://learn.microsoft.com/dotnet/core/diagnostics/dotnet-dump) (collect `--type`, analyze, `syncblk`, `clrstack -all`, containers, ptrace) ·
  [Debug a deadlock in .NET](https://learn.microsoft.com/dotnet/core/diagnostics/debug-deadlock) ·
  [dotnet-stack](https://learn.microsoft.com/dotnet/core/diagnostics/dotnet-stack) (`report -p|-n`, `ps`) ·
  [Collect diagnostics in Linux containers](https://learn.microsoft.com/dotnet/core/diagnostics/diagnostics-in-containers) (host, sidecar, shared `/tmp`, ptrace) ·
  [Debug Linux dumps](https://learn.microsoft.com/dotnet/core/diagnostics/debug-linux-dumps) ·
  [Local tools](https://learn.microsoft.com/dotnet/core/tools/local-tools-how-to-use) (`dotnet new tool-manifest`, `dotnet tool restore`, `dotnet tool run`) ·
  [Logging in ASP.NET Core](https://learn.microsoft.com/aspnet/core/fundamentals/logging/?view=aspnetcore-10.0) (scopes, `ActivityTrackingOptions`) ·
  [Console log formatting](https://learn.microsoft.com/dotnet/core/extensions/logging/console-log-formatter) (JSON formatter, `FormatterName`) ·
  [Compile-time logging source generation](https://learn.microsoft.com/dotnet/core/extensions/logging/source-generation) (`[LoggerMessage]`) ·
  [Handle errors in ASP.NET Core](https://learn.microsoft.com/aspnet/core/fundamentals/error-handling?view=aspnetcore-10.0) (problem details sample with `traceId`) ·
  [DebuggerDisplay](https://learn.microsoft.com/visualstudio/debugger/using-the-debuggerdisplay-attribute?view=visualstudio) ·
  [Debug ASP.NET Core apps in Visual Studio](https://learn.microsoft.com/visualstudio/debugger/how-to-enable-debugging-for-aspnet-applications?view=visualstudio) (Release for measurements, attach to process) ·
  [C# Dev Kit](https://learn.microsoft.com/visualstudio/subscriptions/vs-c-sharp-dev-kit) (eligibility) ·
  [Use .http files](https://learn.microsoft.com/aspnet/core/test/http-files?view=aspnetcore-10.0) (the REST Client extension and Visual Studio's editor)
- VS Code docs (not Microsoft Learn): [Debugging](https://code.visualstudio.com/docs/debugtest/debugging) (conditional breakpoints, logpoints, Debug Console) ·
  [C# debugging](https://code.visualstudio.com/docs/csharp/debugging) (attach command, Hot Reload) · [C# debugger settings](https://code.visualstudio.com/docs/csharp/debugger-settings) (`launch.json` options)
- git: [`git bisect`](https://git-scm.com/docs/git-bisect) (`run`, exit codes 0 / 1–127 except 125 / 125, `reset`)
- Packages: `dotnet-stack` and `dotnet-dump` 10.0.750501 (local tools, pinned); `Microsoft.AspNetCore.OpenApi`, EF Core 10.0.15 as in episode 8
