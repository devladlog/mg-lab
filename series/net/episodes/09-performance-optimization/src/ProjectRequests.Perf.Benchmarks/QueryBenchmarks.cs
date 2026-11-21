using BenchmarkDotNet.Attributes;
using BenchmarkDotNet.Configs;
using Microsoft.EntityFrameworkCore;
using ProjectRequests.Perf.Api.Data;
using ProjectRequests.Perf.Api.Requests;

namespace ProjectRequests.Perf.Benchmarks;

/// <summary>
/// The listing endpoint written four ways, then the totals written two ways, on a real SQLite file with
/// 20,000 requests. Same shape as the benchmark in Learn's "Performance Diagnosis" page.
/// Each benchmark creates and disposes its own DbContext (that cost is part of every variant, so ratios stay fair).
/// </summary>
[MemoryDiagnoser, GroupBenchmarksBy(BenchmarkLogicalGroupRule.ByCategory), CategoriesColumn]
public class QueryBenchmarks
{
    private string _path = "";
    private DbContextOptions<PerfDbContext> _options = null!;

    [Params(200)]
    public int Rows { get; set; }

    [GlobalSetup]
    public async Task Setup()
    {
        _path = Path.Combine(Path.GetTempPath(), $"perf-bench-{Guid.NewGuid():N}.db");
        _options = new DbContextOptionsBuilder<PerfDbContext>().UseSqlite($"Data Source={_path}").Options;
        await using var db = new PerfDbContext(_options);
        await Seeder.SeedAsync(db, requestCount: 20_000);
    }

    [GlobalCleanup]
    public void Cleanup()
    {
        Microsoft.Data.Sqlite.SqliteConnection.ClearAllPools();
        File.Delete(_path);
    }

    // ---- listing ----
    [Benchmark(Baseline = true), BenchmarkCategory("list")]
    public async Task<int> List_NPlusOne_Tracked()
    {
        await using var db = new PerfDbContext(_options);
        return (await RequestQueries.NPlusOneAsync(db, "FIN", Rows)).Count;
    }

    [Benchmark, BenchmarkCategory("list")]
    public async Task<int> List_Include_Tracked()
    {
        await using var db = new PerfDbContext(_options);
        return (await RequestQueries.IncludeTrackedAsync(db, "FIN", Rows)).Count;
    }

    [Benchmark, BenchmarkCategory("list")]
    public async Task<int> List_Include_NoTracking()
    {
        await using var db = new PerfDbContext(_options);
        return (await RequestQueries.IncludeNoTrackingAsync(db, "FIN", Rows)).Count;
    }

    [Benchmark, BenchmarkCategory("list")]
    public async Task<int> List_Projection()
    {
        await using var db = new PerfDbContext(_options);
        return (await RequestQueries.ProjectedAsync(db, "FIN", 0, Rows)).Count;
    }

    // ---- totals ----
    [Benchmark(Baseline = true), BenchmarkCategory("sum")]
    public async Task<decimal> Sum_LoadEverything()
    {
        await using var db = new PerfDbContext(_options);
        return await RequestQueries.SumLoadAllAsync(db);
    }

    [Benchmark, BenchmarkCategory("sum")]
    public async Task<decimal> Sum_InDatabase()
    {
        await using var db = new PerfDbContext(_options);
        return await RequestQueries.SumInDatabaseAsync(db);
    }
}
