using System.Text.Json;

namespace Contoso.FinanceReview;

/// <summary>
/// Turns what the Dapr sidecar POSTs into a decision. The publisher is API Management, not Dapr, so the subscription
/// is declared with rawPayload: the sidecar wraps the raw Service Bus body in a CloudEvent and base64-encodes it.
/// </summary>
public sealed class Delivery(IFinanceReviewSink sink)
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public async Task<DeliveryResult> HandleAsync(JsonElement envelope, CancellationToken ct)
    {
        if (envelope.ValueKind != JsonValueKind.Object) return DeliveryResult.Drop("Envelope is not a JSON object.");

        var body = ExtractBody(envelope, out var problem);
        if (body is null) return DeliveryResult.Drop(problem!);

        PurchaseEvent? evt;
        try { evt = JsonSerializer.Deserialize<PurchaseEvent>(body, Json); }
        catch (JsonException ex) { return DeliveryResult.Drop($"Body is not valid JSON for a purchase event: {ex.Message}"); }

        var invalid = PurchaseRules.Validate(evt);
        if (invalid is not null) return DeliveryResult.Drop(invalid);

        try { await sink.OpenReviewAsync(evt!, ct); }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            return DeliveryResult.Retry(ex.Message); // back to the subscription; it dead-letters after MaxDeliveryCount
        }
        return DeliveryResult.Done;
    }

    /// <summary>CloudEvents allows the payload in data_base64 (what a raw payload arrives as) or in data.</summary>
    internal static byte[]? ExtractBody(JsonElement envelope, out string? problem)
    {
        problem = null;
        if (envelope.TryGetProperty("data_base64", out var b64) && b64.ValueKind == JsonValueKind.String)
        {
            try { return Convert.FromBase64String(b64.GetString()!); }
            catch (FormatException) { problem = "data_base64 is not valid base64."; return null; }
        }
        if (envelope.TryGetProperty("data", out var data))
        {
            return data.ValueKind switch
            {
                JsonValueKind.Object => JsonSerializer.SerializeToUtf8Bytes(data),
                JsonValueKind.String => System.Text.Encoding.UTF8.GetBytes(data.GetString()!),
                _ => Fail("data must be a JSON object or a string.", out problem),
            };
        }
        problem = "The CloudEvent carries neither data_base64 nor data.";
        return null;
    }

    private static byte[]? Fail(string message, out string problem) { problem = message; return null; }
}
