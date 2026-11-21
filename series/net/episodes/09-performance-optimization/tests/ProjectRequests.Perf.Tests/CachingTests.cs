using System.IO.Compression;
using System.Net;
using System.Net.Http.Json;
using Microsoft.Extensions.Caching.Hybrid;
using Microsoft.Extensions.Caching.Memory;
using ProjectRequests.Perf.Api.Json;
using ProjectRequests.Perf.Api.Requests;

namespace ProjectRequests.Perf.Tests;

public class CachingTests
{
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    private static Task<HttpResponseMessage> Post(HttpClient c, string title, decimal budget = 100_000) =>
        c.PostAsJsonAsync("/api/requests", new CreateRequest(title, budget, "FIN", 1), AppJsonContext.Default.CreateRequest, Ct);

    // ---- output cache (HTTP level) ----

    [Fact]
    public async Task Second_identical_GET_is_served_from_the_output_cache_with_zero_SQL()
    {
        await using var app = new PerfFactory();
        var client = app.CreateClient();

        var first = await client.GetStringAsync("/api/requests?pageSize=10", Ct);
        app.Commands.Reset();
        var second = await client.GetStringAsync("/api/requests?pageSize=10", Ct);

        Assert.Equal(first, second);
        Assert.Equal(0, app.Commands.Count);
    }

    [Fact]
    public async Task Cache_varies_by_the_query_string_values_we_named()
    {
        await using var app = new PerfFactory();
        var client = app.CreateClient();

        await client.GetStringAsync("/api/requests?page=1&pageSize=10", Ct);
        app.Commands.Reset();
        await client.GetStringAsync("/api/requests?page=2&pageSize=10", Ct);

        Assert.Equal(2, app.Commands.Count);              // page 2 is a different entry: it hit the database
    }

    [Fact]
    public async Task Creating_a_request_evicts_the_cached_list_by_tag()
    {
        await using var app = new PerfFactory();
        var client = app.CreateClient();

        var before = await client.GetFromJsonAsync("/api/requests?pageSize=5", AppJsonContext.Default.PagedResultRequestDto, Ct);
        var created = await Post(client, "Cache me if you can");
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);

        app.Commands.Reset();
        var after = await client.GetFromJsonAsync("/api/requests?pageSize=5", AppJsonContext.Default.PagedResultRequestDto, Ct);

        Assert.Equal(before!.Total + 1, after!.Total);
        Assert.True(app.Commands.Count > 0);              // it was recomputed, not served stale
    }

    // ---- HybridCache (data level) ----

    [Fact]
    public async Task Summary_is_computed_once_for_many_concurrent_callers()
    {
        await using var app = new PerfFactory();
        var client = app.CreateClient();
        using var computed = app.Record("mglab.perf.summary.computed");
        app.Commands.Delay = TimeSpan.FromMilliseconds(100);     // make the cold computation slow so callers really overlap

        var results = await Task.WhenAll(Enumerable.Range(0, 30).Select(_ =>
            client.GetFromJsonAsync("/api/summary", AppJsonContext.Default.SummaryDto, Ct)));

        Assert.Equal(1, computed.Total);                  // one factory run, 29 callers waited for it
        Assert.All(results, r => Assert.Equal(300, r!.Total));
        Assert.Single(results.Select(r => r!.ComputedAtUtc).Distinct());
    }

    [Fact]
    public async Task Writes_invalidate_the_summary_by_tag()
    {
        await using var app = new PerfFactory();
        var client = app.CreateClient();
        using var computed = app.Record("mglab.perf.summary.computed");

        var first = await client.GetFromJsonAsync("/api/summary", AppJsonContext.Default.SummaryDto, Ct);
        await client.GetFromJsonAsync("/api/summary", AppJsonContext.Default.SummaryDto, Ct);
        Assert.Equal(1, computed.Total);                  // second call was a cache hit

        await Post(client, "Invalidate the summary", 250_000);
        var after = await client.GetFromJsonAsync("/api/summary", AppJsonContext.Default.SummaryDto, Ct);

        Assert.Equal(2, computed.Total);
        Assert.Equal(first!.Total + 1, after!.Total);
        Assert.Equal(first.TotalBudget + 250_000, after.TotalBudget);
    }

    [Fact]
    public async Task Creating_requests_is_counted_by_the_custom_metric()
    {
        await using var app = new PerfFactory();
        var client = app.CreateClient();
        using var created = app.Record("mglab.perf.requests.created");

        await Post(client, "One");
        await Post(client, "Two");
        var rejected = await client.PostAsJsonAsync("/api/requests",
            new CreateRequest("Bad department", 10, "NOPE", 1), AppJsonContext.Default.CreateRequest, Ct);

        Assert.Equal(HttpStatusCode.BadRequest, rejected.StatusCode);
        Assert.Equal(2, created.Total);                   // the rejected one is not counted
    }

    // ---- the library behaviour the summary relies on, shown on its own ----

    [Fact]
    public async Task IMemoryCache_GetOrCreate_can_run_the_factory_many_times_HybridCache_runs_it_once()
    {
        var naiveCalls = 0;
        using (var memory = new MemoryCache(new MemoryCacheOptions()))
        {
            await Task.WhenAll(Enumerable.Range(0, 20).Select(_ => memory.GetOrCreateAsync("k", async _ =>
            {
                Interlocked.Increment(ref naiveCalls);
                await Task.Delay(100, Ct);
                return "value";
            })));
        }

        var hybridCalls = 0;
        var services = new ServiceCollection().AddHybridCache().Services.BuildServiceProvider();
        var hybrid = services.GetRequiredService<HybridCache>();
        await Task.WhenAll(Enumerable.Range(0, 20).Select(_ => hybrid.GetOrCreateAsync("k", async token =>
        {
            Interlocked.Increment(ref hybridCalls);
            await Task.Delay(100, token);
            return "value";               // strings are handled by HybridCache itself, no JSON serializer involved
        }, cancellationToken: Ct).AsTask()));

        Assert.True(naiveCalls > 1, $"expected a stampede, factory ran {naiveCalls} time(s)");
        Assert.Equal(1, hybridCalls);
    }

    // ---- compression ----

    private static async Task<HttpResponseMessage> GetWith(HttpClient c, string url, string acceptEncoding)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, url);
        request.Headers.TryAddWithoutValidation("Accept-Encoding", acceptEncoding);
        return await c.SendAsync(request, Ct);
    }

    [Theory]
    [InlineData("gzip")]
    [InlineData("br")]
    public async Task Responses_are_compressed_when_the_client_asks_and_decompress_to_the_same_body(string encoding)
    {
        await using var app = new PerfFactory();
        var client = app.CreateClient();
        var url = "/api/requests?pageSize=100";

        var plain = await client.GetByteArrayAsync(url, Ct);
        using var response = await GetWith(client, url, encoding);
        var compressed = await response.Content.ReadAsByteArrayAsync(Ct);

        Assert.Equal(encoding, Assert.Single(response.Content.Headers.ContentEncoding));
        Assert.Contains("Accept-Encoding", response.Headers.Vary);
        Assert.True(compressed.Length < plain.Length / 2, $"{compressed.Length} bytes vs {plain.Length} uncompressed");

        await using var input = new MemoryStream(compressed);
        await using Stream decoder = encoding == "gzip" ? new GZipStream(input, CompressionMode.Decompress) : new BrotliStream(input, CompressionMode.Decompress);
        using var output = new MemoryStream();
        await decoder.CopyToAsync(output, Ct);
        Assert.Equal(plain, output.ToArray());
    }

    [Fact]
    public async Task Output_cache_and_compression_work_together()
    {
        await using var app = new PerfFactory();
        var client = app.CreateClient();
        var url = "/api/requests?pageSize=50";

        using var first = await GetWith(client, url, "gzip");
        app.Commands.Reset();
        using var second = await GetWith(client, url, "gzip");

        Assert.Equal(0, app.Commands.Count);              // served from the output cache ...
        Assert.Contains("gzip", second.Content.Headers.ContentEncoding);   // ... and still compressed on the way out
        Assert.Equal(await first.Content.ReadAsByteArrayAsync(Ct), await second.Content.ReadAsByteArrayAsync(Ct));
    }
}
