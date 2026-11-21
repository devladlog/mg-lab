using System.Globalization;
using ProjectRequests.Perf.LoadTest;

// loadtest <url> [--concurrency 16] [--seconds 10] [--warmup 2] [--header "Name: value"]...
if (args.Length == 0 || args[0] is "-h" or "--help")
{
    Console.WriteLine("usage: loadtest <url> [--concurrency 16] [--seconds 10] [--warmup 2] [--header \"Name: value\"]...");
    return args.Length == 0 ? 2 : 0;
}

var url = args[0];
int concurrency = 16, seconds = 10, warmup = 2;
var headers = new Dictionary<string, string>();
for (var i = 1; i < args.Length; i++)
{
    switch (args[i])
    {
        case "--concurrency": concurrency = int.Parse(args[++i], CultureInfo.InvariantCulture); break;
        case "--seconds": seconds = int.Parse(args[++i], CultureInfo.InvariantCulture); break;
        case "--warmup": warmup = int.Parse(args[++i], CultureInfo.InvariantCulture); break;
        case "--header":
            var parts = args[++i].Split(':', 2, StringSplitOptions.TrimEntries);
            headers[parts[0]] = parts.Length > 1 ? parts[1] : "";
            break;
        default: Console.Error.WriteLine($"unknown option {args[i]}"); return 2;
    }
}

// One shared handler = one connection pool, like a real client. Compression is explicit via --header, not automatic.
using var client = new HttpClient(new SocketsHttpHandler { MaxConnectionsPerServer = concurrency }) { Timeout = TimeSpan.FromSeconds(60) };

if (warmup > 0)
{
    Console.WriteLine($"warm-up {warmup}s ...");
    await LoadRunner.RunAsync(client, url, concurrency, TimeSpan.FromSeconds(warmup), headers);
}
Console.WriteLine($"measuring {seconds}s, {concurrency} workers: GET {url}");
var r = await LoadRunner.RunAsync(client, url, concurrency, TimeSpan.FromSeconds(seconds), headers);

Console.WriteLine($"requests   {r.Requests}   errors {r.Errors}");
Console.WriteLine($"throughput {r.RequestsPerSecond:F1} req/s");
Console.WriteLine($"latency ms p50 {r.P50:F1}   p95 {r.P95:F1}   p99 {r.P99:F1}   max {r.Max:F1}");
return r.Errors == 0 ? 0 : 1;
