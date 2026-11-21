using System.Diagnostics;
using System.Globalization;
using System.Net.Http.Json;
using Contoso.Approvals;

// usage: dotnet run --project src/Contoso.Approvals.Cli -- <mode> [--api URL] [--parallel N] [--timeout-ms N]
// modes: sequential | unbounded | bounded | timeout | waitasync | deadlock
var mode = args.FirstOrDefault() ?? "bounded";
var api = Option("--api", "http://localhost:5080/");
var parallel = int.Parse(Option("--parallel", "4"), CultureInfo.InvariantCulture);
var timeoutMs = int.Parse(Option("--timeout-ms", "2000"), CultureInfo.InvariantCulture);

// Ctrl+C cancels the token instead of killing the process: every await downstream sees it.
using var cts = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) =>
{
    e.Cancel = true;
    Console.WriteLine("Ctrl+C: cancelling...");
    cts.Cancel();
};

if (mode == "deadlock")
{
    RunDeadlockDemo();
    return 0;
}

using var http = new HttpClient { BaseAddress = new Uri(api) };
var client = new FinanceClient(http);
var enricher = new Enricher(client, TimeProvider.System,
    EnricherOptions.Default with { AttemptTimeout = TimeSpan.FromMilliseconds(timeoutMs) });
enricher.Retrying += (what, attempt, delay, error) =>
    Console.WriteLine($"  retry  {what,-20} attempt {attempt} failed ({Reason(error)}), waiting {delay.TotalMilliseconds:N0} ms");
var runner = new BatchRunner(enricher);

await http.PostAsync("stats/reset", null, cts.Token);
var watch = Stopwatch.StartNew();
try
{
    switch (mode)
    {
        case "sequential":
            Summary("sequential", await runner.SequentialAsync(await LoadAsync(), cts.Token));
            break;
        case "unbounded":
            var all = new List<EnrichedRequest>();
            await foreach (var done in runner.AllAtOnceAsync(await LoadAsync(), cts.Token))
            {
                all.Add(done);
                Line(done);
            }
            Summary("all at once (Task.WhenEach)", all);
            break;
        case "bounded":
            Summary($"bounded, {parallel} at a time",
                await runner.BoundedAsync(client.StreamRequestsAsync(cts.Token), parallel, cts.Token, Line));
            break;
        case "timeout":
            // Real timeout: the linked token reaches HttpClient, the API logs "ABORTED by the client".
            var budget = await Resilience.WithTimeoutAsync(
                c => client.GetBudgetAsync("CC-100", c), TimeSpan.FromMilliseconds(timeoutMs), TimeProvider.System, cts.Token);
            Console.WriteLine($"budget {budget.CostCenter}: {budget.Remaining:N0} EUR left");
            break;
        case "waitasync":
            // Gotcha: WaitAsync stops WAITING after the timeout. The HTTP call keeps running on the API.
            var call = client.GetBudgetAsync("CC-100", cts.Token);
            await call.WaitAsync(TimeSpan.FromMilliseconds(timeoutMs), cts.Token);
            break;
        default:
            await Console.Error.WriteLineAsync($"Unknown mode '{mode}'.");
            return 2;
    }
}
catch (OperationCanceledException) when (cts.IsCancellationRequested)
{
    Console.WriteLine($"Cancelled after {watch.Elapsed.TotalSeconds:F2} s.");
}
catch (TimeoutException ex)
{
    Console.WriteLine($"TimeoutException after {watch.ElapsedMilliseconds} ms: {ex.Message}");
}

// Give the API a moment to finish its own bookkeeping, then show what it saw.
await Task.Delay(400, CancellationToken.None);
var stats = await http.GetFromJsonAsync<StatsSnapshot>("stats", CancellationToken.None);
Console.WriteLine($"api saw: {stats}");
return 0;

async Task<IReadOnlyList<ProjectRequest>> LoadAsync()
{
    List<ProjectRequest> list = [];
    await foreach (var request in client.StreamRequestsAsync(cts.Token)) list.Add(request);
    watch.Restart(); // time only the enrichment, not the download of the list
    return list;
}

void Line(EnrichedRequest r) => Console.WriteLine(
    $"  {r.Request.Code}  {r.Request.CostCenter}  {r.Request.Budget,10:N0} EUR  {(r.WithinBudget ? "within budget" : "OVER budget"),-13}  -> {r.Approver.Email}");

void Summary(string label, IReadOnlyCollection<EnrichedRequest> results) => Console.WriteLine(
    $"{label}: {results.Count} requests in {watch.Elapsed.TotalSeconds:F2} s, " +
    $"{results.Count(r => r.WithinBudget)} within budget, {results.Count(r => !r.WithinBudget)} over budget");

string Option(string name, string fallback)
{
    var i = Array.IndexOf(args, name);
    return i >= 0 && i + 1 < args.Length ? args[i + 1] : fallback;
}

static string Reason(Exception error) => error switch
{
    HttpRequestException { StatusCode: { } code } => $"{(int)code} {code}",
    _ => error.GetType().Name,
};

static void RunDeadlockDemo()
{
    var latency = TimeSpan.FromMilliseconds(100);
    var giveUp = TimeSpan.FromSeconds(2);
    Console.WriteLine("On a single-threaded SynchronizationContext (like a UI thread):");

    var watch = Stopwatch.StartNew();
    var completed = SyncOverAsync.BlockOnUiThread(latency, giveUp);
    Console.WriteLine($"  1. .Wait() on async code         -> {(completed ? "completed" : "DEADLOCK")} ({watch.ElapsedMilliseconds} ms, the work needed 100)");

    watch.Restart();
    completed = SyncOverAsync.BlockOnUiThreadLibraryStyle(latency, giveUp);
    Console.WriteLine($"  2. .Wait(), ConfigureAwait(false) -> {(completed ? "completed" : "DEADLOCK")} ({watch.ElapsedMilliseconds} ms, but a thread sat blocked)");

    watch.Restart();
    completed = SyncOverAsync.AwaitOnUiThread(latency);
    Console.WriteLine($"  3. await all the way             -> {(completed ? "completed" : "DEADLOCK")} ({watch.ElapsedMilliseconds} ms, nothing blocked)");
}

internal sealed record StatsSnapshot(int Calls, int InFlight, int MaxInFlight, int Aborted, int Failed);
