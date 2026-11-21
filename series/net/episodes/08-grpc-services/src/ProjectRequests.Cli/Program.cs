using Grpc.Core;
using ProjectRequests.Cli;
using ProjectRequests.Grpc;

// dotnet run -- [--address http://localhost:5208] [--deadline 10] get <id> | list [--department FIN] | import <file.csv>
if (!Uri.TryCreate(Option("--address") ?? "http://localhost:5208", UriKind.Absolute, out var address)
    || !double.TryParse(Option("--deadline") ?? "10", System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var seconds))
{
    Console.Error.WriteLine("--address must be an absolute URL and --deadline a number of seconds");
    return 64;
}
var timeout = TimeSpan.FromSeconds(seconds);
var positional = Positionals().ToList();

if (positional.Count == 0 || positional[0] is not ("get" or "list" or "import")
    || (positional[0] is "get" or "import" && positional.Count < 2)
    || (positional[0] is "get" && !int.TryParse(positional[1], out _)))
{
    Console.Error.WriteLine("usage: requests-cli [--address http://localhost:5208] [--deadline 10] get <id> | list [--department FIN] | import <file.csv>");
    return 64;
}

using var cts = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };   // Ctrl+C cancels the call, server side too

using var channel = ChannelFactory.Create(address);
var client = new Requests.RequestsClient(channel);

try
{
    switch (positional[0])
    {
        case "get":
            await Commands.GetAsync(client, int.Parse(positional[1]), timeout, Console.Out, cts.Token);
            break;
        case "list":
            await Commands.ListAsync(client, Option("--department"), timeout, Console.Out, cts.Token);
            break;
        case "import":
            var outcome = await Commands.ImportAsync(client, CsvRows.Read(File.ReadLines(positional[1])), timeout, Console.Out, cts.Token);
            return outcome.Errors == 0 ? 0 : 3;
    }
    return 0;
}
catch (RpcException ex)
{
    // Status code + detail is all the server can send: gRPC has no HTTP status codes, no problem+json.
    Console.Error.WriteLine($"gRPC error: {ex.StatusCode} - {ex.Status.Detail}");
    return 2;
}
catch (OperationCanceledException)
{
    Console.Error.WriteLine("cancelled");
    return 130;
}

string? Option(string name)
{
    var i = Array.IndexOf(args, name);
    return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
}

IEnumerable<string> Positionals()
{
    for (var i = 0; i < args.Length; i++)
    {
        if (args[i].StartsWith("--")) { i++; continue; }              // every option here takes a value
        yield return args[i];
    }
}
