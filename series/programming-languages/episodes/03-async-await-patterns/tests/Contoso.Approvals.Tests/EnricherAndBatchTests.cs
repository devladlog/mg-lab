namespace Contoso.Approvals.Tests;

public class EnricherAndBatchTests
{
    private static Enricher NewEnricher(IFinanceClient client) => new(client, TimeProvider.System);

    [Fact]
    public async Task Budget_and_approver_lookups_overlap()
    {
        var client = new CountingClient(delayMs: 50);
        var result = await NewEnricher(client).EnrichAsync(Data.Request(1), CancellationToken.None);

        Assert.Equal(2, client.MaxTotalInFlight);   // both calls were running at the same time
        Assert.True(result.WithinBudget);
    }

    [Fact]
    public async Task A_request_above_the_remaining_budget_is_flagged()
    {
        var client = new CountingClient { Remaining = 40_000m };
        var result = await NewEnricher(client).EnrichAsync(Data.Request(1, budget: 55_000m), CancellationToken.None);
        Assert.False(result.WithinBudget);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(3)]
    [InlineData(4)]
    public async Task Bounded_never_has_more_than_maxParallel_requests_in_flight(int maxParallel)
    {
        var client = new CountingClient(delayMs: 20);
        var runner = new BatchRunner(NewEnricher(client));

        var results = await runner.BoundedAsync(client.StreamRequestsAsync(CancellationToken.None), maxParallel, CancellationToken.None);

        Assert.Equal(12, results.Count);
        Assert.Equal(maxParallel, client.MaxBudgetInFlight);       // one budget call per request in flight
        Assert.Equal(2 * maxParallel, client.MaxTotalInFlight);    // each request makes two overlapping calls
        Assert.Equal("PR-2026-0001", results[0].Request.Code);     // sorted, whatever the completion order
    }

    [Fact]
    public async Task All_at_once_really_is_all_at_once()
    {
        var client = new CountingClient(delayMs: 50);
        var runner = new BatchRunner(NewEnricher(client));
        var count = 0;
        await foreach (var _ in runner.AllAtOnceAsync(Data.Batch(12), CancellationToken.None)) count++;

        Assert.Equal(12, count);
        Assert.Equal(24, client.MaxTotalInFlight);
    }

    [Fact]
    public async Task All_at_once_yields_in_completion_order_with_WhenEach()
    {
        var client = new GatedClient();
        var runner = new BatchRunner(NewEnricher(client));
        ProjectRequest[] requests = [Data.Request(1, "CC-100"), Data.Request(2, "CC-200"), Data.Request(3, "CC-300")];

        var order = new List<string>();
        var consume = Task.Run(async () =>
        {
            await foreach (var r in runner.AllAtOnceAsync(requests, CancellationToken.None)) order.Add(r.Request.Code);
        });

        await Wait.UntilAsync(() => Volatile.Read(ref client.BudgetCalls) == 3);
        client.Release("CC-300", 1m);
        await Wait.UntilAsync(() => order.Count == 1);
        client.Release("CC-100", 1m);
        await Wait.UntilAsync(() => order.Count == 2);
        client.Release("CC-200", 1m);
        await consume;

        Assert.Equal(["PR-2026-0003", "PR-2026-0001", "PR-2026-0002"], order);
    }

    [Fact]
    public async Task Sequential_keeps_input_order_and_never_overlaps_requests()
    {
        var client = new CountingClient(delayMs: 5);
        var results = await new BatchRunner(NewEnricher(client)).SequentialAsync(Data.Batch(5), CancellationToken.None);

        Assert.Equal(["PR-2026-0001", "PR-2026-0002", "PR-2026-0003", "PR-2026-0004", "PR-2026-0005"],
            results.Select(r => r.Request.Code));
        Assert.Equal(1, client.MaxBudgetInFlight);
    }

    [Fact]
    public async Task Cancelling_a_bounded_batch_stops_it_early()
    {
        var client = new CountingClient(delayMs: 50);
        var runner = new BatchRunner(NewEnricher(client));
        using var cts = new CancellationTokenSource();
        var done = 0;

        var task = runner.BoundedAsync(client.StreamRequestsAsync(cts.Token), 2, cts.Token,
            _ => { if (Interlocked.Increment(ref done) == 2) cts.Cancel(); });

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => task);
        Assert.InRange(Volatile.Read(ref client.Completed), 2, 6);   // nowhere near 12
    }
}
