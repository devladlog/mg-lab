using System.Globalization;
using Microsoft.AspNetCore.SignalR;
using ProjectRequests.Contracts;
using ProjectRequests.Feed;

// dotnet run -- [--api http://localhost:5207/] [--department FIN]
var api = new Uri(Arg("--api") ?? "http://localhost:5207/");
var department = Arg("--department");

using var cts = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };

await using var feed = new RequestsFeed(api);   // no logger: the state lines below say what the connection does

feed.Created += r => Print(ConsoleColor.Cyan, "NEW     ", r);
feed.Updated += r => Print(r.Status switch
{
    RequestStatus.Approved => ConsoleColor.Green,
    RequestStatus.Rejected => ConsoleColor.Red,
    _ => ConsoleColor.Yellow,
}, "UPDATED ", r);
feed.StateChanged += s => Log($"connection: {s}");
feed.Resubscribed += () => Log($"reconnected as {feed.ConnectionId}, watching {feed.Department ?? "all departments"} again");

// WithAutomaticReconnect only covers connections that were up once; a failed first start is ours to retry.
while (!cts.IsCancellationRequested)
{
    try
    {
        await feed.StartAsync(department, cts.Token);
        Log($"connected to {api} as {feed.ConnectionId}, watching {feed.Department ?? "all departments"} (Ctrl+C to stop)");
        break;
    }
    catch (HubException ex)
    {
        Log($"the hub refused: {ex.Message}");                       // e.g. unknown department
        return 1;
    }
    catch (Exception ex) when (ex is HttpRequestException or TimeoutException)
    {
        Log($"API not reachable ({ex.Message}); retrying in 5 s");
        try { await Task.Delay(TimeSpan.FromSeconds(5), cts.Token); } catch (OperationCanceledException) { }
    }
    catch (OperationCanceledException) { }
}

try { await Task.Delay(Timeout.Infinite, cts.Token); } catch (OperationCanceledException) { }
return 0;

string? Arg(string name)
{
    var i = Array.IndexOf(args, name);
    return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
}

static void Log(string text) => Console.WriteLine($"{DateTime.Now:HH:mm:ss} {text}");

static void Print(ConsoleColor color, string what, RequestDto r)
{
    Console.ForegroundColor = color;
    Console.WriteLine(string.Create(CultureInfo.InvariantCulture,
        $"{DateTime.Now:HH:mm:ss} {what}#{r.Id} {r.Department,-3} {r.Title,-28} {r.Budget,12:N0}  {r.Priority,-8} {r.Status}{(r.DecidedBy is null ? "" : " by " + r.DecidedBy)}"));
    Console.ResetColor();
}
