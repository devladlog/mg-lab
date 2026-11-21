using Azure.Identity;
using Azure.Messaging.ServiceBus;
using Contoso.PurchaseEvents;

// dotnet run --project src/PurchaseEvents.Worker -- --namespace <ns>.servicebus.windows.net --topic purchase-events --subscription all-events
// Signs in with DefaultAzureCredential (az login on the lab laptop). Needs Azure Service Bus Data Receiver on the topic.
var options = ParseArgs(args);
if (options is null)
{
    Console.Error.WriteLine("Usage: --namespace <fqdn> --topic <name> --subscription <name> [--max-messages <n>]");
    return 2;
}

await using var client = new ServiceBusClient(options.Namespace, new DefaultAzureCredential());
await using var processor = client.CreateProcessor(options.Topic, options.Subscription, new ServiceBusProcessorOptions
{
    AutoCompleteMessages = false,      // we decide: complete, dead-letter or abandon
    MaxConcurrentCalls = 2,
    PrefetchCount = 0,
});

var handler = new PurchaseEventHandler(new InMemoryProcessedStore(), new ConsoleSink(options.Subscription));
var handled = 0;
using var done = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; done.Cancel(); };

processor.ProcessMessageAsync += async args =>
{
    var result = await handler.HandleAsync(args.Message, args.CancellationToken);
    switch (result.Disposition)
    {
        case Disposition.Complete:
            await args.CompleteMessageAsync(args.Message, args.CancellationToken);
            break;
        case Disposition.DeadLetter:
            Console.WriteLine($"[{options.Subscription}] DEAD-LETTER {args.Message.MessageId}: {result.Reason} - {result.Description}");
            await args.DeadLetterMessageAsync(args.Message, result.Reason, result.Description, args.CancellationToken);
            break;
        default:
            Console.WriteLine($"[{options.Subscription}] RETRY {args.Message.MessageId}: {result.Description}");
            await args.AbandonMessageAsync(args.Message, cancellationToken: args.CancellationToken);
            break;
    }
    if (options.MaxMessages is { } max && Interlocked.Increment(ref handled) >= max) done.Cancel();
};
processor.ProcessErrorAsync += args =>
{
    Console.Error.WriteLine($"[{options.Subscription}] {args.ErrorSource}: {args.Exception.Message}");
    return Task.CompletedTask;
};

Console.WriteLine($"Listening on {options.Topic}/{options.Subscription} (Ctrl+C to stop)");
await processor.StartProcessingAsync();
try { await Task.Delay(Timeout.Infinite, done.Token); } catch (OperationCanceledException) { }
await processor.StopProcessingAsync();
return 0;

static Options? ParseArgs(string[] a)
{
    string? Get(string name) { var i = Array.IndexOf(a, name); return i >= 0 && i + 1 < a.Length ? a[i + 1] : null; }
    var ns = Get("--namespace"); var topic = Get("--topic"); var sub = Get("--subscription");
    if (ns is null || topic is null || sub is null) return null;
    return new Options(ns, topic, sub, int.TryParse(Get("--max-messages"), out var m) ? m : null);
}

internal sealed record Options(string Namespace, string Topic, string Subscription, int? MaxMessages);

internal sealed class ConsoleSink(string subscription) : IPurchaseEventSink
{
    public Task WriteAsync(PurchaseEvent e, string messageId, string? correlationId, CancellationToken ct)
    {
        Console.WriteLine($"[{subscription}] {e.EventType,-9} {e.PurchaseRequestId} {e.Total,10:N2} {e.Currency} by {e.RequestedBy} id={messageId[..8]} corr={correlationId?[..8]}");
        return Task.CompletedTask;
    }
}
