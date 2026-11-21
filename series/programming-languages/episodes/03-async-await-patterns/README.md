# DEVLADLOG Code #3 — Async and await, done properly (C# 14 on .NET 10)

The Contoso project requests from episodes 1 and 2 now need two lookups before anybody can approve them: the
**remaining budget** of the cost center and **who the approver is**. Both come from a small Finance API (ASP.NET
Core, 300 ms per lookup). We call it from a C# client and measure every pattern against the real API:

- **Pass the `CancellationToken` all the way down** to `HttpClient`, so Ctrl+C and timeouts abort the HTTP request
- **Start independent calls, then `await Task.WhenAll`**: budget and approver overlap (300 ms, not 600)
- **Sequential vs all-at-once vs bounded**: `Task.WhenEach` (.NET 9+) and `Parallel.ForEachAsync` with an explicit
  `MaxDegreeOfParallelism`, fed by a streamed `IAsyncEnumerable` (`GetFromJsonAsAsyncEnumerable`)
- **A timeout that cancels the work** (linked `CancellationTokenSource(timeout, TimeProvider)`), versus
  `Task.WaitAsync`, which only stops waiting
- **Retry with exponential backoff** on 503/429/502/504 and timeouts, tested with `FakeTimeProvider`
- **Ctrl+C** handled with `Console.CancelKeyPress` + a token, so in-flight calls are aborted cleanly
- **The sync-over-async deadlock**, reproduced deterministically on a single-threaded `SynchronizationContext`
- **Analyzer guardrails**: CS4014, CA2016 and CA1849 as build errors

| Path | What it is |
|---|---|
| [`Directory.Build.props`](Directory.Build.props) | `net10.0`, nullable, warnings as errors, `latest-recommended` analyzers |
| [`.editorconfig`](.editorconfig) | Pins CA2016 and turns on CA1849 (not reported at `latest-recommended` otherwise) |
| [`src/Contoso.Approvals.Api/`](src/Contoso.Approvals.Api) | Fictional Finance API: `/requests` (streamed), `/budget/{cc}`, `/approver/{dept}`, `/stats`. Logs every call, counts calls in flight and calls aborted by the client (`RequestAborted`). Options: `--Api:LatencyMs`, `--Api:Flaky=CC-400` (503 on every odd call) |
| [`src/Contoso.Approvals.Async/FinanceClient.cs`](src/Contoso.Approvals.Async/FinanceClient.cs) | Typed `HttpClient`, token on every call, `ConfigureAwait(false)`, `GetFromJsonAsAsyncEnumerable` + .NET 10 `AsyncEnumerable.OfType` |
| [`src/Contoso.Approvals.Async/Enricher.cs`](src/Contoso.Approvals.Async/Enricher.cs) | Budget + approver in parallel (`Task.WhenAll`), each call with timeout + retry |
| [`src/Contoso.Approvals.Async/Resilience.cs`](src/Contoso.Approvals.Async/Resilience.cs) | `WithTimeoutAsync` (linked tokens, `TimeProvider`), `RetryAsync` (backoff), `IsTransient` |
| [`src/Contoso.Approvals.Async/BatchRunner.cs`](src/Contoso.Approvals.Async/BatchRunner.cs) | `SequentialAsync`, `AllAtOnceAsync` (`Task.WhenEach`), `BoundedAsync` (`Parallel.ForEachAsync`) |
| [`src/Contoso.Approvals.Async/SingleThreadContext.cs`](src/Contoso.Approvals.Async/SingleThreadContext.cs) / [`SyncOverAsync.cs`](src/Contoso.Approvals.Async/SyncOverAsync.cs) | A UI-thread-like `SynchronizationContext` and the deadlock, three ways |
| [`src/Contoso.Approvals.Cli/Program.cs`](src/Contoso.Approvals.Cli/Program.cs) | Console app used in the video: `sequential`, `unbounded`, `bounded`, `timeout`, `waitasync`, `deadlock`; Ctrl+C support |
| [`tests/Contoso.Approvals.Tests/`](tests/Contoso.Approvals.Tests) | 27 xUnit tests: resilience with `FakeTimeProvider`, concurrency limits, `WhenEach` order, gotchas, and integration tests against the real API in memory (`WebApplicationFactory`) |
| [`demo/Analyzers/`](demo/Analyzers) | Wrong on purpose: CS4014, CA2016, CA1849 |
| [`demo/expect-errors.sh`](demo/expect-errors.sh) | Builds `demo/Analyzers`, checks the three diagnostics, runs the deadlock demo |
| [`demo/expected-output.txt`](demo/expected-output.txt) | Real output of the tests, every CLI mode against the running API, and the script |

## Build, test, run

```bash
dotnet test AsyncPatterns.slnx -m:1          # Passed: 27, Failed: 0 (~3 s)
./demo/expect-errors.sh                      # 3 errors as expected + "ok" checks + deadlock demo (exit code 0)

# terminal 1: the Finance API on http://localhost:5080
dotnet run --project src/Contoso.Approvals.Api            # add  -- --Api:Flaky=CC-400  to see retries
# terminal 2: the client
dotnet run --project src/Contoso.Approvals.Cli -- sequential   # 12 requests in ~3.7 s, max 2 calls in flight
dotnet run --project src/Contoso.Approvals.Cli -- unbounded    # ~0.33 s, 24 calls in flight at once
dotnet run --project src/Contoso.Approvals.Cli -- bounded      # ~1.0 s, never more than 8 in flight (4 requests x 2)
dotnet run --project src/Contoso.Approvals.Cli -- timeout --timeout-ms 150     # API logs "ABORTED by the client"
dotnet run --project src/Contoso.Approvals.Cli -- waitasync --timeout-ms 150   # API logs "done 300 ms" anyway
dotnet run --project src/Contoso.Approvals.Cli -- deadlock     # no API needed
```

Tested here with .NET SDK 10.0.115 on Linux: 27 tests passed on 10 consecutive runs. Packages: xUnit,
`Microsoft.Extensions.TimeProvider.Testing` 10.11.1, `Microsoft.AspNetCore.Mvc.Testing` 10.0.15. No cloud
resources: the API runs locally.

## What we learned / gotchas

- **`Task.WaitAsync(timeout)` stops waiting, not working.** Both our timeout and `WaitAsync` threw
  `TimeoutException` after ~158 ms, but the API log shows the difference: `ABORTED by the client after 150 ms`
  versus `done 300 ms`. Learn describes `WaitAsync` as a task that completes "when this Task completes, when the
  specified timeout expires, or when the specified CancellationToken has cancellation requested"; it doesn't cancel
  the original task. To stop the work, the token must reach the operation (`GotchaTests`, `ResilienceTests`).
- **Unbounded is the fastest and the worst.** All at once took 0.33 s and put 24 calls in flight on the API at the
  same instant; bounded to 4 requests took ~1 s with at most 8. `Parallel.ForEachAsync` without options runs at most
  `Environment.ProcessorCount` operations in parallel (Learn): a number about your CPU, not about the API.
- **`await Task.WhenAll(...)` rethrows only one exception.** The returned task's `Exception` has all of them
  (`Gotcha_await_WhenAll_throws_only_one_exception_but_the_task_keeps_all`).
- **The deadlock needs a single-threaded context.** Console apps and ASP.NET Core don't have one, so `.Result`
  "works" there, until the same library is called from a UI thread. Reproduced: `.Wait()` gives up after 2 s on work
  that needs 100 ms; with `ConfigureAwait(false)` in the async method it completes; awaiting all the way never blocks.
- **A FakeTimeProvider test can hang if you advance the clock too early.** Our first retry test advanced time right
  after the second attempt, but the retry loop resumes on the thread pool and creates the next `Task.Delay` timer a
  moment later; that timer was due in the "future" of an already-advanced clock and never fired. One of our
  first three test runs hung. Fix: count `CreateTimer` calls (subclass `FakeTimeProvider`) and wait for the timer before `Advance`.
- **A late continuation on a dead `SynchronizationContext` crashed the test host.** Our demo context threw
  `ObjectDisposedException` from `Post` when a continuation arrived after its thread had finished; that exception runs
  on a thread-pool thread, so it killed the whole test process (2 runs out of 6) instead of failing one test. The
  context now drops late posts.
- **CA1849 is opinionated.** Once enabled it also flagged `Console.Error.WriteLine` inside our async `Main`
  (`TextWriter.WriteLine` "synchronously blocks"); we switched to `WriteLineAsync`. Plain `Console.WriteLine` isn't
  flagged. At `AnalysisLevel=latest-recommended`, CS4014 and CA2016 are already warnings; CA1849 only appears because
  of our `.editorconfig` line.
- **In-memory TestServer reports a cancelled call differently.** Over real Kestrel the client gets
  `OperationCanceledException` (see the Ctrl+C run). With `WebApplicationFactory`, cancelling the client sometimes
  returned the server's HTTP 499 response instead. Our integration test accepts both and asserts what matters: the
  API counted the call as aborted.
- **Ctrl+C**: `Console.CancelKeyPress` with `e.Cancel = true` turns Ctrl+C into a cancelled token; the API logged both
  in-flight calls as aborted. (Tested here by sending SIGINT; check it once on the Windows laptop, see demo.md.)

## References
- [Asynchronous programming with async and await](https://learn.microsoft.com/dotnet/csharp/asynchronous-programming/)
- [Common async/await bugs (deadlocks, async void, missing await)](https://learn.microsoft.com/dotnet/standard/asynchronous-programming-patterns/common-async-bugs)
- [Consuming the Task-based Asynchronous Pattern (WhenAll exceptions, ConfigureAwait)](https://learn.microsoft.com/dotnet/standard/asynchronous-programming-patterns/consuming-the-task-based-asynchronous-pattern)
- [Task exception handling](https://learn.microsoft.com/dotnet/standard/asynchronous-programming-patterns/task-exception-handling)
- [Process asynchronous tasks as they complete (`Task.WhenEach`)](https://learn.microsoft.com/dotnet/csharp/asynchronous-programming/start-multiple-async-tasks-and-process-them-as-they-complete) and [What's new in .NET 9 libraries](https://learn.microsoft.com/dotnet/core/whats-new/dotnet-9/libraries#threading)
- [`Parallel.ForEachAsync`](https://learn.microsoft.com/dotnet/api/system.threading.tasks.parallel.foreachasync) and [`ParallelOptions.MaxDegreeOfParallelism`](https://learn.microsoft.com/dotnet/api/system.threading.tasks.paralleloptions.maxdegreeofparallelism)
- [`Task.WaitAsync`](https://learn.microsoft.com/dotnet/api/system.threading.tasks.task.waitasync)
- [What is TimeProvider?](https://learn.microsoft.com/dotnet/standard/datetime/timeprovider-overview) and [Testing with FakeTimeProvider](https://learn.microsoft.com/dotnet/core/extensions/timeprovider-testing)
- [System.Linq.AsyncEnumerable in .NET 10](https://learn.microsoft.com/dotnet/core/compatibility/core-libraries/10.0/asyncenumerable)
- [`HttpClientJsonExtensions.GetFromJsonAsAsyncEnumerable`](https://learn.microsoft.com/dotnet/api/system.net.http.json.httpclientjsonextensions.getfromjsonasasyncenumerable)
- [Async return types (`async void`)](https://learn.microsoft.com/dotnet/csharp/asynchronous-programming/async-return-types#void-return-type)
- [CA2016](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/quality-rules/ca2016), [CA1849](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/quality-rules/ca1849)
- Blog: [Async/Await Patterns — Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-06-25-asyncawait-patterns-complete-guide-2025/)
