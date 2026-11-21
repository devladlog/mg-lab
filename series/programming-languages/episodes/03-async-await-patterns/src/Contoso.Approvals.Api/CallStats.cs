using System.Diagnostics;

namespace Contoso.Approvals.Api;

public sealed record StatsSnapshot(int Calls, int InFlight, int MaxInFlight, int Aborted, int Failed);

/// <summary>Thread-safe counters: how many lookups are running right now, the peak, and how many the client aborted.</summary>
public sealed class CallStats(ApiOptions options)
{
    private int _calls, _inFlight, _maxInFlight, _aborted, _failed, _flakyCounter;

    public StatsSnapshot Snapshot() =>
        new(Volatile.Read(ref _calls), Volatile.Read(ref _inFlight), Volatile.Read(ref _maxInFlight),
            Volatile.Read(ref _aborted), Volatile.Read(ref _failed));

    public void Reset()
    {
        Interlocked.Exchange(ref _calls, 0);
        Interlocked.Exchange(ref _maxInFlight, Volatile.Read(ref _inFlight));
        Interlocked.Exchange(ref _aborted, 0);
        Interlocked.Exchange(ref _failed, 0);
        Interlocked.Exchange(ref _flakyCounter, 0);
    }

    /// <summary>True on every odd call for the flaky cost center.</summary>
    public bool ShouldFail(string costCenter) =>
        options.Flaky.Length > 0
        && string.Equals(costCenter, options.Flaky, StringComparison.OrdinalIgnoreCase)
        && Interlocked.Increment(ref _flakyCounter) % 2 == 1;

    public void Failed(string what)
    {
        Interlocked.Increment(ref _failed);
        Log($"{what,-22} 503 Service Unavailable (flaky on purpose)");
    }

    /// <summary>Runs one simulated lookup: counts it, waits the configured latency, and notices a client abort.</summary>
    public async Task<T> TrackAsync<T>(string what, Func<T> result, CancellationToken requestAborted)
    {
        Interlocked.Increment(ref _calls);
        var now = Interlocked.Increment(ref _inFlight);
        UpdateMax(now);
        Log($"{what,-22} start  (in flight {now})");
        var watch = Stopwatch.StartNew();
        try
        {
            // The token is HttpContext.RequestAborted: it fires when the client cancels or disconnects.
            await Task.Delay(options.LatencyMs, requestAborted);
            Log($"{what,-22} done   {watch.ElapsedMilliseconds,4} ms");
            return result();
        }
        catch (OperationCanceledException)
        {
            Interlocked.Increment(ref _aborted);
            Log($"{what,-22} ABORTED by the client after {watch.ElapsedMilliseconds} ms");
            throw;
        }
        finally
        {
            Interlocked.Decrement(ref _inFlight);
        }
    }

    private void UpdateMax(int candidate)
    {
        int seen;
        while (candidate > (seen = Volatile.Read(ref _maxInFlight)))
            if (Interlocked.CompareExchange(ref _maxInFlight, candidate, seen) == seen) return;
    }

    private void Log(string line)
    {
        if (!options.Quiet) Console.WriteLine($"[api {DateTime.Now:HH:mm:ss.fff}] {line}");
    }
}
