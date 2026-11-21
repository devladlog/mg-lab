# DEVLADLOG .NET #9 — Performance on .NET 10: measure first, then fix the query, cache the answer, watch the counters

Episode 3's project requests API has grown to 20,000 requests and the list screen is slow. Everyone has a theory.
This episode doesn't guess. It **measures** (BenchmarkDotNet, a small load generator, EF Core's own SQL log),
fixes the one thing the measurement points at, and measures again:

- **The classic N+1**: a listing that loads tracked entities and then runs **two more queries per row**
  (`1 + 2N` round trips). Kept in the code as `RequestQueries.NPlusOneAsync` so it can be measured, next to three
  better versions: `Include` (tracked), `Include` + `AsNoTracking`, and a **projection** straight into the DTO.
- **Paging that can't be abused**: page size is capped at 100 and anything else is a `400` problem response
  (Learn: don't return unbounded collections).
- **Two caches, two jobs**: **output caching** for whole HTTP responses (per department / page, evicted **by tag**
  when a request is created) and **`HybridCache`** for a computed value (the dashboard summary), which adds
  **stampede protection** and tag invalidation that `IMemoryCache` doesn't have.
- **Response compression** in the right place in the pipeline, with `EnableForHttps` left off.
- **Source-generated JSON** (`JsonSerializerContext`) with reflection switched **off**, so a forgotten type fails
  loudly instead of silently falling back to reflection.
- **Your own metrics** on `System.Diagnostics.Metrics`, visible live in `dotnet-counters`.
- **Benchmarks that can't lie**: tests check that every benchmark variant returns *exactly the same data*.

| Path | What it is |
|---|---|
| [`src/ProjectRequests.Perf.Api/Requests/RequestQueries.cs`](src/ProjectRequests.Perf.Api/Requests/RequestQueries.cs) | The same listing four ways (N+1, Include tracked, Include no-tracking, projection) + two ways to sum |
| [`src/ProjectRequests.Perf.Api/Requests/RequestEndpoints.cs`](src/ProjectRequests.Perf.Api/Requests/RequestEndpoints.cs) | `GET /api/requests` (projection, paging, output cache), `GET /api/summary`, `POST /api/requests` (evicts both caches), `GET /api/slow/requests` (the "before", off unless `Perf:EnableSlowEndpoint`) |
| [`src/ProjectRequests.Perf.Api/Caching/SummaryService.cs`](src/ProjectRequests.Perf.Api/Caching/SummaryService.cs) | `HybridCache.GetOrCreateAsync` with tags and expiry, `RemoveByTagAsync` |
| [`src/ProjectRequests.Perf.Api/Caching/SummarySerializer.cs`](src/ProjectRequests.Perf.Api/Caching/SummarySerializer.cs) | `IHybridCacheSerializer<SummaryDto>` on the source-generated context (needed with reflection off) |
| [`src/ProjectRequests.Perf.Api/Json/AppJsonContext.cs`](src/ProjectRequests.Perf.Api/Json/AppJsonContext.cs) | `JsonSerializerContext`: Web defaults + string enums |
| [`src/ProjectRequests.Perf.Api/Telemetry/RequestMetrics.cs`](src/ProjectRequests.Perf.Api/Telemetry/RequestMetrics.cs) | Two counters from `IMeterFactory` |
| [`src/ProjectRequests.Perf.Api/Program.cs`](src/ProjectRequests.Perf.Api/Program.cs) | Registration order: compression, output cache, HybridCache, JSON resolver chain |
| [`src/ProjectRequests.Perf.Api/Data/`](src/ProjectRequests.Perf.Api/Data/) | Entities, `PerfDbContext`, deterministic seeder (20,000 requests, 400 requesters, SQLite) |
| [`src/ProjectRequests.Perf.Benchmarks/`](src/ProjectRequests.Perf.Benchmarks/) | BenchmarkDotNet: `QueryBenchmarks` (list x4, sum x2), `JsonBenchmarks` (reflection vs source-generated) |
| [`src/ProjectRequests.Perf.LoadTest/`](src/ProjectRequests.Perf.LoadTest/) | `loadtest <url>`: N workers, warm-up, req/s and p50/p95/p99 |
| [`tests/ProjectRequests.Perf.Tests/`](tests/ProjectRequests.Perf.Tests/) | 30 tests: SQL command counts, cache hits/eviction/stampede, compression, JSON, metrics, benchmark sanity |
| [`deploy/Measure-Endpoints.ps1`](deploy/Measure-Endpoints.ps1) | Demo driver: starts the API three ways and load-tests each (pwsh, Windows or Linux) |
| [`deploy/loadtest-container.txt`](deploy/loadtest-container.txt) · [`benchmark-results.container.txt`](deploy/benchmark-results.container.txt) · [`sql-log.sample.txt`](deploy/sql-log.sample.txt) · [`dotnet-counters.sample.csv`](deploy/dotnet-counters.sample.csv) | Real output from runs in the build container (not the recording laptop) |

## Build, test, run

```bash
dotnet test                       # MTP mode via global.json -> total: 30, failed: 0, succeeded: 30 (~35 s)
                                  # NB: no -m:1 here, in MTP mode it is handed to the test app ("Unknown option '--m'")

# the API (Development: slow endpoint on, EF Core SQL logged). First start seeds 20,000 rows into perf.db
dotnet run --project src/ProjectRequests.Perf.Api --launch-profile http      # http://localhost:5209
curl "http://localhost:5209/api/requests?department=FIN&pageSize=5"
curl "http://localhost:5209/api/slow/requests?take=5"
curl  http://localhost:5209/api/summary

# the measurements
dotnet run -c Release --project src/ProjectRequests.Perf.Benchmarks -- --filter "*QueryBenchmarks*"    # add --job short for a quick pass
dotnet run -c Release --project src/ProjectRequests.Perf.Benchmarks -- --filter "*JsonBenchmarks*"
pwsh ./deploy/Measure-Endpoints.ps1                      # before / after / cached, 8 s each

# live metrics (global tool, install once: dotnet tool install -g dotnet-counters)
dotnet-counters monitor -n ProjectRequests.Perf.Api --counters ProjectRequests.Perf
```

Tested with .NET SDK 10.0.115 / runtime 10.0.15, EF Core SQLite 10.0.15, `Microsoft.Extensions.Caching.Hybrid` 10.11.1,
BenchmarkDotNet 0.15.8, xUnit.net v3 4.0.3, on Linux. **No SQL Server or Azure is involved**: SQLite is a local file
(no Docker here). That is deliberate: the lessons are about the shape of the queries and the caches, and the
numbers are reproducible on the recording laptop without any cloud resource.

**Mutation-checked**: removing `outputCache.EvictByTagAsync(...)` from `Create` fails the output-cache eviction test;
removing `summary.InvalidateAsync(...)` fails the HybridCache one; removing `AddSerializer<...>` fails the summary tests.

## What the numbers looked like here (build container, 2 shared vCPUs, so noisy)

| | before | after |
|---|---|---|
| SQL commands for 20 rows | **41** (1 + 2 x 20) | **2** (`COUNT` + one `SELECT` with the JOINs); **0** on a cache hit |
| Allocated per 200-row listing (BenchmarkDotNet) | 6,010 KB (N+1, tracked) | 175 KB (projection), 578 KB (Include, tracked), 400 KB (Include, no-tracking) |
| Mean per 200-row listing (ShortRun, error bars are wide) | ~53 ms | ~6 ms (Include tracked ~7.5 ms, no-tracking ~9.5 ms: **no-tracking was not faster than tracking here**, see below) |
| Sum of 20,000 budgets | load everything: ~473 ms, 24 MB | `SUM` in SQLite: ~41 ms, 3 MB |
| Load test, 8 workers, 8 s (`/slow` take=100 vs `/api/requests` pageSize=100) | **49 req/s**, p50 150 ms, p99 424 ms | **849 req/s**, p50 8 ms, p99 30 ms; with the output cache on **32,789 req/s**, p50 0.2 ms |
| Response size, `pageSize=100` | 17,890 bytes | 2,638 gzip, 3,327 Brotli (default levels, measured with `curl`) |
| JSON, 100 DTOs | reflection 35.4 KB allocated | source-generated 35.0 KB as a `string`, **17.6 KB as UTF-8 bytes** |

Full output: [`deploy/loadtest-container.txt`](deploy/loadtest-container.txt),
[`deploy/benchmark-results.container.txt`](deploy/benchmark-results.container.txt). Re-record on the laptop: the
orders of magnitude and the allocation columns are the stable part, the absolute times are not.

## What we learned / gotchas

- **`HybridCache` serialises what it stores, even with no distributed cache.** With reflection-based JSON switched off
  (`JsonSerializerIsReflectionEnabledByDefault=false`) the first `GetOrCreateAsync` of a `SummaryDto` threw
  *"Reflection-based serialization has been disabled for this application"* from `DefaultJsonSerializerFactory`.
  Learn's Native AOT section says the same: cache custom types with source generation or a configured serializer.
  Fix: `AddHybridCache().AddSerializer<SummaryDto, SummarySerializer>()`. Strings and `byte[]` need nothing.
- **`IMemoryCache.GetOrCreateAsync` has no stampede protection; `HybridCache` has.** Test: 20 concurrent callers
  with a 100 ms factory. `MemoryCache` ran the factory more than once; `HybridCache` ran it once (Learn: only one
  concurrent caller per key calls the factory, per `HybridCache` instance). In the API test 30 concurrent
  `GET /api/summary` calls on a cold cache increment `mglab.perf.summary.computed` exactly once.
- **Tag invalidation is logical, not physical.** `RemoveByTagAsync` sets an "ignore anything created before now"
  rule; old values stay in memory until they expire (Learn). It's also per server: other instances' local caches are
  not touched. With more than one instance you need the secondary (distributed) cache, and for the output cache a
  Redis store.
- **Output caching defaults are conservative**: only `200` responses to `GET`/`HEAD`, nothing for authenticated
  requests or responses that set cookies; default expiry 60 s; resource locking is on by default against cache
  stampedes (Learn). We named the query keys that vary the entry (`department`, `page`, `pageSize`); an unrelated
  extra query parameter doesn't create new entries. We also saw that a request header `Cache-Control: no-cache` did
  **not** bypass it (0 SQL commands) — don't count on clients to refresh it, evict by tag.
- **Compression goes before the output cache in the pipeline** (`UseResponseCompression` first): the cache stores the
  uncompressed body and each response is compressed on the way out, with `Vary: Accept-Encoding`. A test pins that a
  cached response is still compressed and issues zero SQL. `EnableForHttps` stays `false`: Learn flags compression of
  dynamic content over TLS as a CRIME/BREACH risk. On a laptop, behind IIS or App Service, check the `Content-Encoding`
  header isn't being applied by the web server instead (Learn).
- **Source-generated JSON is not a speed miracle on .NET 10.** BenchmarkDotNet showed the same allocation as
  reflection when producing a `string` (35 KB) and only about 25% less time with huge error bars on a shared CPU. The
  real wins: no reflection at run time (startup, trimming, Native AOT), and writing **UTF-8 bytes** halves the
  allocation. The switch that makes it safe is `JsonSerializerIsReflectionEnabledByDefault=false`: a type missing from
  `AppJsonContext` then throws `NotSupportedException` (a test proves it) instead of quietly using reflection.
- **No-tracking is not automatically faster.** Learn's benchmark shows no-tracking at 0.71 of the tracking time for
  10 blogs x 20 posts, and its Razor Pages tutorial notes that in some cases a tracking query is more efficient. Here
  `Include` + `AsNoTracking` (9.5 ms) did not beat `Include` tracked (7.5 ms) for 200 rows (ShortRun, wide error bars);
  what it did save is memory (400 KB vs 578 KB). The big steps were removing the N+1 (10x less memory, ~7x less time)
  and projecting only the needed columns (175 KB). Measure, don't assume.
- **"In the database" isn't free on SQLite.** `SUM` of a `decimal` shows up in the SQL log as
  `COALESCE(ef_sum("r"."Budget"), '0.0')` because SQLite stores decimals as text; it was still ~10x faster and 8x
  lighter than loading 20,000 entities.
- **EF Core could not translate `GroupBy(...).Select(new DepartmentSummary(...)).OrderBy(s => s.Code)`**; ordering
  the groups first (`GroupBy(...).OrderBy(g => g.Key).Select(...)`) translates. The error message lists the whole
  expression, which is how we saw what to change.
- **Output cache vs local SQLite**: 849 -> 32,789 req/s is the cache skipping the two queries *and* the JSON
  serialisation, on loopback. Against a remote database each avoided round trip is worth much more than the ~1 ms they
  cost here, but we only measured what we ran.
- **BenchmarkDotNet needs the exe name to match the `.csproj` name** (it rebuilds the project in a temp folder).
  We first set `AssemblyName` to `benchmarks` and got "Unable to find benchmarks ... name of output exe is different
  than the name of the .(c/f)sproj". Also use `GroupBenchmarksBy(ByCategory)`: without it the "sum" benchmarks were
  compared against the "list" baseline.
- **A console project that references the web project sees its `public partial class Program`** (needed by
  `WebApplicationFactory<Program>`), so top-level statements in the benchmark project warn CS0436. We use an explicit
  `Main` there.
- **`dotnet test -m:1` breaks in Microsoft.Testing.Platform mode**: the option is passed to the test app. Plain
  `dotnet test`.
- **`dotnet-counters collect` only wrote its CSV when it ended by itself** (`--duration 00:00:16`); stopping it with
  `SIGINT` left no file. The custom meter showed up under `--counters ProjectRequests.Perf`
  (see [`deploy/dotnet-counters.sample.csv`](deploy/dotnet-counters.sample.csv): 8 summary reads, then 3 writes each
  followed by a read: `requests.created` ticks 3 times and `summary.computed` ticks once after each write, not for
  the cached reads).
- **Metrics in tests**: `IMeterFactory` meters are scoped to the app instance, so a `MeterListener` filtered on
  `instrument.Meter.Scope` sees only its own test's measurements; parallel tests don't interfere.

## References
- [HybridCache library in ASP.NET Core (stampede protection, tags, serialization, Native AOT)](https://learn.microsoft.com/aspnet/core/performance/caching/hybrid)
- [Output caching middleware in ASP.NET Core (defaults, tags, eviction, locking, limits)](https://learn.microsoft.com/aspnet/core/performance/caching/output)
- [Response compression in ASP.NET Core (`EnableForHttps`, CRIME/BREACH, providers, middleware order)](https://learn.microsoft.com/aspnet/core/performance/response-compression)
- [ASP.NET Core best practices (async, pagination, LOH >= 85,000 bytes, `ArrayPool`, no-tracking, projections)](https://learn.microsoft.com/aspnet/core/performance/performance-best-practices)
- [EF Core efficient querying (N+1, tracking, projection)](https://learn.microsoft.com/ef/core/performance/efficient-querying)
- [EF Core tracking vs no-tracking queries](https://learn.microsoft.com/ef/core/querying/tracking)
- [EF Core performance diagnosis (benchmarking with BenchmarkDotNet)](https://learn.microsoft.com/ef/core/performance/performance-diagnosis)
- [System.Text.Json source generation (combine contexts, `TypeInfoResolverChain`, disable reflection defaults, `UseStringEnumConverter`)](https://learn.microsoft.com/dotnet/standard/serialization/system-text-json/source-generation)
- [Reflection vs source generation in System.Text.Json](https://learn.microsoft.com/dotnet/standard/serialization/system-text-json/reflection-vs-source-generation)
- [ASP.NET Core support for Native AOT (JSON contexts registered in DI)](https://learn.microsoft.com/aspnet/core/fundamentals/native-aot)
- [Creating metrics (`Meter`, `Counter`)](https://learn.microsoft.com/dotnet/core/diagnostics/metrics-instrumentation) · [ASP.NET Core metrics (`IMeterFactory`, `dotnet-counters`)](https://learn.microsoft.com/aspnet/core/metrics/overview)
- Blog: [Performance Optimization — Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-19-performance-optimization-complete-guide-2026/)
