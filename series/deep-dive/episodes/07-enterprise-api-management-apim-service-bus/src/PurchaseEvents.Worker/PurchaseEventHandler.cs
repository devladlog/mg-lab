using System.Text.Json;
using System.Text.RegularExpressions;
using Azure.Messaging.ServiceBus;

namespace Contoso.PurchaseEvents;

/// <summary>
/// Decides what happens to one message. Pure decision logic over a real <see cref="ServiceBusReceivedMessage"/>:
/// the processor in Program.cs turns the result into Complete / DeadLetter / Abandon.
/// </summary>
public sealed partial class PurchaseEventHandler(IProcessedStore store, IPurchaseEventSink sink)
{
    private static readonly string[] EventTypes = ["submitted", "approved", "rejected"];
    private static readonly string[] Currencies = ["EUR", "USD", "GBP"];

    [GeneratedRegex("^PR-[0-9]{4,8}$")]
    private static partial Regex RequestIdPattern();

    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public async Task<HandlerResult> HandleAsync(ServiceBusReceivedMessage message, CancellationToken ct)
    {
        // The gateway always sets these. A message without them did not come through the gateway.
        if (!Guid.TryParse(message.MessageId, out _))
            return HandlerResult.Poison("InvalidMessageId", "MessageId must be the caller's idempotency GUID.");

        if (message.ContentType is null || !message.ContentType.StartsWith("application/json", StringComparison.OrdinalIgnoreCase))
            return HandlerResult.Poison("UnsupportedContentType", $"Expected application/json, got '{message.ContentType}'.");

        PurchaseEvent? evt;
        try
        {
            evt = message.Body.ToObjectFromJson<PurchaseEvent>(Json);
        }
        catch (JsonException ex)
        {
            return HandlerResult.Poison("InvalidJson", ex.Message);
        }

        // Defence in depth: the gateway validated the body already, but a topic can be sent to by anyone with the role.
        var problem = Validate(evt);
        if (problem is not null) return HandlerResult.Poison("SchemaViolation", problem);

        if (!string.Equals(message.Subject, PurchaseRouting.LabelFor(evt!.Total), StringComparison.Ordinal))
            return HandlerResult.Poison("LabelMismatch", $"Label '{message.Subject}' does not match total {evt.Total}.");

        if (await store.HasProcessedAsync(message.MessageId, ct))
            return HandlerResult.Done; // delivered again (outside the detection window, or after a lock loss): already handled

        try
        {
            await sink.WriteAsync(evt, message.MessageId, message.CorrelationId, ct);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            return HandlerResult.Retry(ex.Message); // goes back to the subscription; dead-letters after MaxDeliveryCount
        }

        await store.MarkProcessedAsync(message.MessageId, ct);
        return HandlerResult.Done;
    }

    internal static string? Validate(PurchaseEvent? e)
    {
        if (e is null) return "Body is empty.";
        if (!EventTypes.Contains(e.EventType)) return $"eventType '{e.EventType}' is not one of {string.Join('/', EventTypes)}.";
        if (e.PurchaseRequestId is null || !RequestIdPattern().IsMatch(e.PurchaseRequestId)) return "purchaseRequestId must look like PR-1001.";
        if (string.IsNullOrWhiteSpace(e.RequestedBy) || e.RequestedBy.Length > 254) return "requestedBy is missing or too long.";
        if (e.Total < 0.01m || e.Total > 10_000_000m) return "total is out of range.";
        if (!Currencies.Contains(e.Currency)) return $"currency '{e.Currency}' is not one of {string.Join('/', Currencies)}.";
        if (e.Note is { Length: > 500 }) return "note is longer than 500 characters.";
        return null;
    }
}
