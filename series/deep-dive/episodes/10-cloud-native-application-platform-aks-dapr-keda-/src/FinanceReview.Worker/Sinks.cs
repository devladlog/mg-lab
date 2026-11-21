namespace Contoso.FinanceReview;

/// <summary>
/// Demo sink: logs one structured line and spends <c>Work:DelayMs</c> on the "review", so a queue visibly drains.
/// With rawPayload the broker's MessageId may not reach the app (not verified), so episode 7's MessageId store does not apply here:
/// a real sink must be idempotent by business key (upsert by PurchaseRequestId) or use Dapr's state API.
/// </summary>
public sealed class LoggingSink(ILogger<LoggingSink> log, IConfiguration config) : IFinanceReviewSink
{
    private readonly int _delayMs = config.GetValue("Work:DelayMs", 0);

    public async Task OpenReviewAsync(PurchaseEvent e, CancellationToken ct)
    {
        if (_delayMs > 0) await Task.Delay(_delayMs, ct);
        log.LogInformation("Finance review opened for {PurchaseRequestId}: {Total} {Currency} requested by {RequestedBy} ({EventType})",
            e.PurchaseRequestId, e.Total, e.Currency, e.RequestedBy, e.EventType);
    }
}
