using System.Collections.Concurrent;
using System.Runtime.CompilerServices;

namespace Contoso.Approvals;

/// <summary>Three ways to enrich a batch. Same work, very different load on the API.</summary>
public sealed class BatchRunner(Enricher enricher)
{
    /// <summary>One request at a time. Simple, and as slow as the sum of all latencies.</summary>
    public async Task<IReadOnlyList<EnrichedRequest>> SequentialAsync(IEnumerable<ProjectRequest> requests, CancellationToken ct)
    {
        var results = new List<EnrichedRequest>();
        foreach (var request in requests)
            results.Add(await enricher.EnrichAsync(request, ct).ConfigureAwait(false));
        return results;
    }

    /// <summary>
    /// Everything at once, results yielded in completion order with Task.WhenEach (.NET 9+).
    /// Fast with 12 requests; with 12,000 it fires 24,000 HTTP calls at the API in the same instant.
    /// </summary>
    public async IAsyncEnumerable<EnrichedRequest> AllAtOnceAsync(
        IEnumerable<ProjectRequest> requests, [EnumeratorCancellation] CancellationToken ct)
    {
        List<Task<EnrichedRequest>> tasks = [.. requests.Select(r => enricher.EnrichAsync(r, ct))];
        await foreach (var finished in Task.WhenEach(tasks).WithCancellation(ct).ConfigureAwait(false))
            yield return await finished.ConfigureAwait(false);
    }

    /// <summary>At most <paramref name="maxParallel"/> requests in flight, pulled from a stream as slots free up.</summary>
    public async Task<IReadOnlyList<EnrichedRequest>> BoundedAsync(
        IAsyncEnumerable<ProjectRequest> requests, int maxParallel, CancellationToken ct,
        Action<EnrichedRequest>? onCompleted = null)
    {
        var results = new ConcurrentQueue<EnrichedRequest>();
        var options = new ParallelOptions { MaxDegreeOfParallelism = maxParallel, CancellationToken = ct };
        await Parallel.ForEachAsync(requests, options, async (request, token) =>
        {
            var enriched = await enricher.EnrichAsync(request, token).ConfigureAwait(false);
            results.Enqueue(enriched);
            onCompleted?.Invoke(enriched);
        }).ConfigureAwait(false);
        return [.. results.OrderBy(r => r.Request.Code, StringComparer.Ordinal)];
    }
}
