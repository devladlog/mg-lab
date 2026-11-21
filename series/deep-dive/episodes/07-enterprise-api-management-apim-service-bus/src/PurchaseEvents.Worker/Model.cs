namespace Contoso.PurchaseEvents;

public sealed record PurchaseEvent(
    string EventType,
    string PurchaseRequestId,
    string RequestedBy,
    decimal Total,
    string Currency,
    string? Note);

public enum Disposition { Complete, DeadLetter, Abandon }

public sealed record HandlerResult(Disposition Disposition, string? Reason = null, string? Description = null)
{
    public static readonly HandlerResult Done = new(Disposition.Complete);
    public static HandlerResult Poison(string reason, string description) => new(Disposition.DeadLetter, reason, description);
    public static HandlerResult Retry(string description) => new(Disposition.Abandon, "TransientFailure", description);
}

/// <summary>Where the business work happens. In the demo it writes to the console.</summary>
public interface IPurchaseEventSink
{
    Task WriteAsync(PurchaseEvent purchaseEvent, string messageId, string? correlationId, CancellationToken ct);
}

/// <summary>
/// Duplicate detection on the topic only covers a time window, and delivery is at-least-once anyway:
/// the consumer still has to be idempotent. Production: a table keyed by MessageId (SQL, Table storage).
/// </summary>
public interface IProcessedStore
{
    Task<bool> HasProcessedAsync(string messageId, CancellationToken ct);
    Task MarkProcessedAsync(string messageId, CancellationToken ct);
}

public sealed class InMemoryProcessedStore : IProcessedStore
{
    private readonly HashSet<string> _seen = new(StringComparer.Ordinal);
    private readonly object _gate = new();

    public Task<bool> HasProcessedAsync(string messageId, CancellationToken ct)
    {
        lock (_gate) return Task.FromResult(_seen.Contains(messageId));
    }

    public Task MarkProcessedAsync(string messageId, CancellationToken ct)
    {
        lock (_gate) _seen.Add(messageId);
        return Task.CompletedTask;
    }
}
