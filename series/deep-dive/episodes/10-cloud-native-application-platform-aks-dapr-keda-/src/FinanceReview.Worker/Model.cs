using System.Text.Json.Serialization;

namespace Contoso.FinanceReview;

/// <summary>The purchase event from episode 7 (same contract as its OpenAPI schema).</summary>
public sealed record PurchaseEvent(
    string EventType,
    string PurchaseRequestId,
    string RequestedBy,
    decimal Total,
    string Currency,
    string? Note);

/// <summary>What the Dapr sidecar expects back from a subscriber (Dapr pub/sub API, "Expected HTTP response").</summary>
public enum DeliveryStatus { SUCCESS, RETRY, DROP }

public sealed record DeliveryResult(
    [property: JsonConverter(typeof(JsonStringEnumConverter))] DeliveryStatus Status,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] string? Reason = null)
{
    public static readonly DeliveryResult Done = new(DeliveryStatus.SUCCESS);
    public static DeliveryResult Drop(string reason) => new(DeliveryStatus.DROP, reason);
    public static DeliveryResult Retry(string reason) => new(DeliveryStatus.RETRY, reason);
}

/// <summary>Where the work happens. In the demo it logs; production writes to the finance system.</summary>
public interface IFinanceReviewSink
{
    Task OpenReviewAsync(PurchaseEvent purchaseEvent, CancellationToken ct);
}
