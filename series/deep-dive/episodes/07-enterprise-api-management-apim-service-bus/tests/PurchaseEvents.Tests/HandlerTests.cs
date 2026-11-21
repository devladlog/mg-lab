using System.Text.Json;
using Azure.Messaging.ServiceBus;
using Contoso.PurchaseEvents;

namespace PurchaseEvents.Tests;

internal sealed class RecordingSink : IPurchaseEventSink
{
    public List<(PurchaseEvent Event, string MessageId, string? Correlation)> Written { get; } = [];
    public Exception? Fail { get; set; }

    public Task WriteAsync(PurchaseEvent e, string messageId, string? correlationId, CancellationToken ct)
    {
        if (Fail is not null) throw Fail;
        Written.Add((e, messageId, correlationId));
        return Task.CompletedTask;
    }
}

public class HandlerTests
{
    internal static ServiceBusReceivedMessage Msg(
        object? body = null, string? messageId = null, string? contentType = "application/json",
        string? subject = null, string? correlationId = "11111111-2222-3333-4444-555555555555", string? rawBody = null)
    {
        body ??= new { eventType = "submitted", purchaseRequestId = "PR-1001", requestedBy = "alex.demo@contoso.com", total = 1476m, currency = "EUR" };
        var json = rawBody ?? JsonSerializer.Serialize(body);
        var total = rawBody is null ? JsonSerializer.SerializeToElement(body).GetProperty("total").GetDecimal() : 0m;
        return ServiceBusModelFactory.ServiceBusReceivedMessage(
            body: BinaryData.FromString(json),
            messageId: messageId ?? Guid.NewGuid().ToString(),
            contentType: contentType,
            subject: subject ?? PurchaseRouting.LabelFor(total),
            correlationId: correlationId);
    }

    private static (PurchaseEventHandler Handler, RecordingSink Sink, InMemoryProcessedStore Store) Create()
    {
        var sink = new RecordingSink();
        var store = new InMemoryProcessedStore();
        return (new PurchaseEventHandler(store, sink), sink, store);
    }

    [Fact]
    public async Task A_valid_standard_event_is_written_and_completed()
    {
        var (h, sink, _) = Create();
        var result = await h.HandleAsync(Msg(), CancellationToken.None);
        Assert.Equal(Disposition.Complete, result.Disposition);
        var written = Assert.Single(sink.Written);
        Assert.Equal("PR-1001", written.Event.PurchaseRequestId);
        Assert.Equal(1476m, written.Event.Total);
        Assert.Equal("11111111-2222-3333-4444-555555555555", written.Correlation);
    }

    [Fact]
    public async Task The_same_message_id_twice_is_handled_once()
    {
        var (h, sink, _) = Create();
        var id = Guid.NewGuid().ToString();
        Assert.Equal(Disposition.Complete, (await h.HandleAsync(Msg(messageId: id), CancellationToken.None)).Disposition);
        Assert.Equal(Disposition.Complete, (await h.HandleAsync(Msg(messageId: id), CancellationToken.None)).Disposition);
        Assert.Single(sink.Written);
    }

    [Fact]
    public async Task A_failing_sink_means_retry_and_the_message_is_not_marked_processed()
    {
        var (h, sink, store) = Create();
        var id = Guid.NewGuid().ToString();
        sink.Fail = new InvalidOperationException("database is down");

        var first = await h.HandleAsync(Msg(messageId: id), CancellationToken.None);
        Assert.Equal(Disposition.Abandon, first.Disposition);
        Assert.False(await store.HasProcessedAsync(id, CancellationToken.None));

        sink.Fail = null;
        var second = await h.HandleAsync(Msg(messageId: id), CancellationToken.None);
        Assert.Equal(Disposition.Complete, second.Disposition);
        Assert.Single(sink.Written);
    }

    [Fact]
    public async Task Cancellation_is_not_swallowed_into_a_retry()
    {
        var (h, sink, _) = Create();
        sink.Fail = new OperationCanceledException();
        await Assert.ThrowsAsync<OperationCanceledException>(() => h.HandleAsync(Msg(), CancellationToken.None));
    }

    [Theory]
    [InlineData("not-a-guid", "application/json", "InvalidMessageId")]
    [InlineData(null, "text/plain", "UnsupportedContentType")]
    [InlineData(null, null, "UnsupportedContentType")]
    public async Task Messages_that_did_not_come_through_the_gateway_are_dead_lettered(string? messageId, string? contentType, string reason)
    {
        var (h, sink, _) = Create();
        var result = await h.HandleAsync(Msg(messageId: messageId, contentType: contentType), CancellationToken.None);
        Assert.Equal(Disposition.DeadLetter, result.Disposition);
        Assert.Equal(reason, result.Reason);
        Assert.Empty(sink.Written);
    }

    [Fact]
    public async Task Broken_json_is_dead_lettered_not_retried()
    {
        var (h, _, _) = Create();
        var result = await h.HandleAsync(Msg(rawBody: "{ this is not json", subject: PurchaseRouting.StandardLabel), CancellationToken.None);
        Assert.Equal(Disposition.DeadLetter, result.Disposition);
        Assert.Equal("InvalidJson", result.Reason);
    }

    [Theory]
    [InlineData("eventType", "deleted")]
    [InlineData("purchaseRequestId", "PR-12")]
    [InlineData("purchaseRequestId", "pr-1001")]
    [InlineData("currency", "JPY")]
    [InlineData("requestedBy", "")]
    public async Task A_body_that_breaks_the_schema_is_dead_lettered(string field, string value)
    {
        var body = new Dictionary<string, object?>
        {
            ["eventType"] = "submitted", ["purchaseRequestId"] = "PR-1001", ["requestedBy"] = "alex.demo@contoso.com",
            ["total"] = 1476m, ["currency"] = "EUR",
        };
        body[field] = value;
        var (h, sink, _) = Create();
        var result = await h.HandleAsync(Msg(body), CancellationToken.None);
        Assert.Equal("SchemaViolation", result.Reason);
        Assert.Empty(sink.Written);
    }

    [Theory]
    [InlineData(0.0, "purchase.standard")]
    [InlineData(10_000_000.01, "purchase.high")]
    public async Task Totals_outside_the_range_are_dead_lettered(double total, string label)
    {
        var body = new { eventType = "submitted", purchaseRequestId = "PR-1001", requestedBy = "alex.demo@contoso.com", total = (decimal)total, currency = "EUR" };
        var (h, _, _) = Create();
        var result = await h.HandleAsync(Msg(body, subject: label), CancellationToken.None);
        Assert.Equal("SchemaViolation", result.Reason);
    }

    [Theory]
    [InlineData(4999.99, "purchase.standard", Disposition.Complete)]
    [InlineData(5000.00, "purchase.high", Disposition.Complete)]
    [InlineData(7380.00, "purchase.high", Disposition.Complete)]
    [InlineData(7380.00, "purchase.standard", Disposition.DeadLetter)]
    [InlineData(1476.00, "purchase.high", Disposition.DeadLetter)]
    public async Task The_label_must_match_the_total(double total, string label, Disposition expected)
    {
        var body = new { eventType = "submitted", purchaseRequestId = "PR-1002", requestedBy = "alex.demo@contoso.com", total = (decimal)total, currency = "EUR" };
        var (h, _, _) = Create();
        var result = await h.HandleAsync(Msg(body, subject: label), CancellationToken.None);
        Assert.Equal(expected, result.Disposition);
        if (expected == Disposition.DeadLetter) Assert.Equal("LabelMismatch", result.Reason);
    }
}
