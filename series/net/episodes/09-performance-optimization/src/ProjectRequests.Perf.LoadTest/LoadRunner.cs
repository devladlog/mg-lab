using System.Diagnostics;

namespace ProjectRequests.Perf.LoadTest;

public sealed record LoadResult(int Requests, int Errors, TimeSpan Elapsed, double P50, double P95, double P99, double Max)
{
    public double RequestsPerSecond => Requests / Elapsed.TotalSeconds;
}

public static class LoadRunner
{
    /// <summary>Nearest-rank percentile of already sorted values (milliseconds). p in (0, 100].</summary>
    public static double Percentile(IReadOnlyList<double> sorted, double p)
    {
        if (sorted.Count == 0) return 0;
        var rank = (int)Math.Ceiling(p / 100.0 * sorted.Count);
        return sorted[Math.Clamp(rank, 1, sorted.Count) - 1];
    }

    public static async Task<LoadResult> RunAsync(HttpClient client, string url, int concurrency, TimeSpan duration,
        IReadOnlyDictionary<string, string>? headers = null, CancellationToken ct = default)
    {
        var latencies = new List<double>();
        var errors = 0;
        var sw = Stopwatch.StartNew();

        async Task Worker()
        {
            var local = new List<double>();
            var localErrors = 0;
            while (sw.Elapsed < duration && !ct.IsCancellationRequested)
            {
                using var request = new HttpRequestMessage(HttpMethod.Get, url);
                foreach (var (k, v) in headers ?? new Dictionary<string, string>())
                    request.Headers.TryAddWithoutValidation(k, v);

                var started = Stopwatch.GetTimestamp();
                try
                {
                    using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
                    await response.Content.CopyToAsync(Stream.Null, ct);          // read the body: that's part of the latency
                    if (!response.IsSuccessStatusCode) localErrors++;
                }
                catch (HttpRequestException) { localErrors++; }
                local.Add(Stopwatch.GetElapsedTime(started).TotalMilliseconds);
            }
            lock (latencies) { latencies.AddRange(local); errors += localErrors; }
        }

        await Task.WhenAll(Enumerable.Range(0, concurrency).Select(_ => Worker()));
        sw.Stop();

        latencies.Sort();
        return new LoadResult(latencies.Count, errors, sw.Elapsed,
            Percentile(latencies, 50), Percentile(latencies, 95), Percentile(latencies, 99),
            latencies.Count == 0 ? 0 : latencies[^1]);
    }
}
