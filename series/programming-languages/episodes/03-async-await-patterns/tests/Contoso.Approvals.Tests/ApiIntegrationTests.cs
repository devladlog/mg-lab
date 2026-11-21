using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;

namespace Contoso.Approvals.Tests;

/// <summary>The real Finance API in memory (TestServer), with 50 ms latency instead of 300.</summary>
public sealed class ApiFixture : IDisposable
{
    private readonly WebApplicationFactory<Program> _factory = new WebApplicationFactory<Program>()
        .WithWebHostBuilder(b => b
            .UseSetting("Api:LatencyMs", "50")
            .UseSetting("Api:Flaky", "CC-400")
            .UseSetting("Api:Quiet", "true"));

    public HttpClient CreateClient() => _factory.CreateClient();
    public void Dispose() => _factory.Dispose();
}

[CollectionDefinition("api")]
public sealed class ApiTestGroup : ICollectionFixture<ApiFixture>;

internal sealed record Stats(int Calls, int InFlight, int MaxInFlight, int Aborted, int Failed);

[Collection("api")]
public sealed class ApiIntegrationTests(ApiFixture api)
{
    private async Task<(HttpClient Http, FinanceClient Client)> FreshAsync()
    {
        var http = api.CreateClient();
        (await http.PostAsync(new Uri("stats/reset", UriKind.Relative), null)).EnsureSuccessStatusCode();
        return (http, new FinanceClient(http));
    }

    [Fact]
    public async Task The_request_list_streams_12_items()
    {
        var (http, client) = await FreshAsync();
        using (http)
        {
            var count = 0;
            await foreach (var _ in client.StreamRequestsAsync(CancellationToken.None)) count++;
            Assert.Equal(12, count);
        }
    }

    [Fact]
    public async Task Bounded_batch_against_the_real_api_peaks_at_two_calls_per_slot()
    {
        var (http, client) = await FreshAsync();
        using (http)
        {
            var runner = new BatchRunner(new Enricher(client, TimeProvider.System));
            var results = await runner.BoundedAsync(client.StreamRequestsAsync(CancellationToken.None), 3, CancellationToken.None);
            var stats = await http.GetFromJsonAsync<Stats>(new Uri("stats", UriKind.Relative));

            Assert.Equal(12, results.Count);
            Assert.Equal(9, results.Count(r => r.WithinBudget));
            Assert.InRange(stats!.MaxInFlight, 2, 6);    // never more than 3 requests x 2 calls
            Assert.True(stats.Failed >= 1);             // CC-400 is flaky on purpose...
            Assert.Equal(12, results.Count(r => r.Budget.CostCenter.Length > 0)); // ...and the retries covered it
        }
    }

    [Fact]
    public async Task Cancelling_the_client_aborts_the_request_on_the_server()
    {
        var (http, client) = await FreshAsync();
        using (http)
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromMilliseconds(15));
            var error = await Record.ExceptionAsync(() => client.GetBudgetAsync("CC-100", cts.Token));

            // Over real Kestrel the client gets OperationCanceledException (see the CLI). The in-memory TestServer
            // can hand back the server's 499 "client closed request" response instead. Either way the call failed...
            Assert.True(error is OperationCanceledException
                || error is HttpRequestException { StatusCode: (System.Net.HttpStatusCode)499 }, $"Got {error}");
            // ...and what matters: the server noticed and stopped working.

            Stats? stats = null;
            for (var i = 0; i < 200 && stats?.Aborted != 1; i++)
            {
                await Task.Delay(10);
                stats = await http.GetFromJsonAsync<Stats>(new Uri("stats", UriKind.Relative));
            }
            Assert.Equal(1, stats!.Aborted);
        }
    }

    [Fact]
    public async Task Unknown_cost_center_is_a_404_and_is_not_retried()
    {
        var (http, client) = await FreshAsync();
        using (http)
        {
            var enricher = new Enricher(client, TimeProvider.System);
            var error = await Assert.ThrowsAsync<HttpRequestException>(
                () => enricher.EnrichAsync(Data.Request(1, costCenter: "CC-999"), CancellationToken.None));
            Assert.Equal(System.Net.HttpStatusCode.NotFound, error.StatusCode);
        }
    }
}
