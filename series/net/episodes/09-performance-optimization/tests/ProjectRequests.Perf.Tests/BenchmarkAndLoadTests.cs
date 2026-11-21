using ProjectRequests.Perf.Api.Data;
using ProjectRequests.Perf.Api.Requests;
using ProjectRequests.Perf.Benchmarks;
using ProjectRequests.Perf.LoadTest;

namespace ProjectRequests.Perf.Tests;

/// <summary>A benchmark that compares things which return different results measures nothing. These run each variant once.</summary>
public class BenchmarkSanityTests
{
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Fact]
    public async Task All_listing_variants_return_exactly_the_same_rows()
    {
        await using var app = new PerfFactory();
        using var scope = app.Services.CreateScope();      // the app already seeded its own SQLite file
        var db = scope.ServiceProvider.GetRequiredService<PerfDbContext>();

        var nPlusOne = await RequestQueries.NPlusOneAsync(db, "FIN", 60, Ct);
        var tracked = await RequestQueries.IncludeTrackedAsync(db, "FIN", 60, Ct);
        var noTracking = await RequestQueries.IncludeNoTrackingAsync(db, "FIN", 60, Ct);
        var projected = await RequestQueries.ProjectedAsync(db, "FIN", 0, 60, Ct);

        Assert.Equal(60, nPlusOne.Count);
        Assert.Equal(nPlusOne, tracked);
        Assert.Equal(nPlusOne, noTracking);
        Assert.Equal(nPlusOne, projected);
    }

    [Fact]
    public async Task Both_ways_of_summing_budgets_agree()
    {
        await using var app = new PerfFactory();
        using var scope = app.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<PerfDbContext>();

        var inMemory = await RequestQueries.SumLoadAllAsync(db, Ct);
        var inDatabase = await RequestQueries.SumInDatabaseAsync(db, Ct);

        Assert.True(inMemory > 0);
        Assert.Equal(inMemory, inDatabase);
    }

    [Fact]
    public void JSON_benchmark_variants_produce_identical_output()
    {
        var bench = new JsonBenchmarks();
        var reflection = bench.Reflection_based();

        Assert.Equal(reflection, bench.Source_generated());
        Assert.Equal(reflection, System.Text.Encoding.UTF8.GetString(bench.Source_generated_utf8()));
    }

    [Fact]
    public async Task The_benchmark_class_itself_runs_end_to_end_on_a_seeded_database()
    {
        var bench = new QueryBenchmarks { Rows = 50 };
        await bench.Setup();
        try
        {
            Assert.Equal(50, await bench.List_NPlusOne_Tracked());
            Assert.Equal(50, await bench.List_Include_Tracked());
            Assert.Equal(50, await bench.List_Include_NoTracking());
            Assert.Equal(50, await bench.List_Projection());
            Assert.Equal(await bench.Sum_LoadEverything(), await bench.Sum_InDatabase());
        }
        finally { bench.Cleanup(); }
    }
}

public class LoadRunnerTests
{
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Theory]
    [InlineData(50, 5)]
    [InlineData(95, 10)]
    [InlineData(99, 10)]
    [InlineData(100, 10)]
    public void Percentile_uses_the_nearest_rank_method(double p, double expected)
    {
        double[] sorted = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
        Assert.Equal(expected, LoadRunner.Percentile(sorted, p));
    }

    [Fact]
    public void Percentile_of_nothing_is_zero() => Assert.Equal(0, LoadRunner.Percentile([], 95));

    [Fact]
    public async Task Runner_drives_the_API_and_reports_requests_and_percentiles()
    {
        await using var app = new PerfFactory();
        var result = await LoadRunner.RunAsync(app.CreateClient(), "/api/requests?pageSize=10", 4, TimeSpan.FromMilliseconds(400), ct: Ct);

        Assert.True(result.Requests > 4);
        Assert.Equal(0, result.Errors);
        Assert.True(result.P50 <= result.P95 && result.P95 <= result.P99 && result.P99 <= result.Max);
    }

    [Fact]
    public async Task Runner_counts_non_success_responses_as_errors()
    {
        await using var app = new PerfFactory();
        var result = await LoadRunner.RunAsync(app.CreateClient(), "/api/requests?pageSize=500", 2, TimeSpan.FromMilliseconds(200), ct: Ct);
        Assert.Equal(result.Requests, result.Errors);     // every request was a 400
    }
}
