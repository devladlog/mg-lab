using System.Text;
using System.Text.Json;
using Contoso.FinanceReview;

namespace FinanceReview.Tests;

public sealed class FakeSink : IFinanceReviewSink
{
    public List<PurchaseEvent> Opened { get; } = [];
    public Exception? Throw { get; set; }

    public Task OpenReviewAsync(PurchaseEvent purchaseEvent, CancellationToken ct)
    {
        if (Throw is not null) throw Throw;
        Opened.Add(purchaseEvent);
        return Task.CompletedTask;
    }
}

public class DeliveryTests
{
    private const string Good = """{"eventType":"submitted","purchaseRequestId":"PR-1002","requestedBy":"alex.demo@contoso.example","total":7380,"currency":"EUR","note":"two monitors"}""";

    private static JsonElement Envelope(string json) => JsonDocument.Parse(json).RootElement.Clone();

    /// <summary>What a Dapr sidecar sends for a rawPayload subscription: the raw body, base64-encoded, in a CloudEvent.</summary>
    private static JsonElement RawEnvelope(string body) => Envelope(JsonSerializer.Serialize(new
    {
        specversion = "1.0",
        id = Guid.NewGuid().ToString(),
        source = "purchase-pubsub",
        type = "com.dapr.event.sent",
        datacontenttype = "application/octet-stream",
        data_base64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(body)),
        topic = "purchase-events",
        pubsubname = "purchase-pubsub",
    }));

    [Fact]
    public async Task A_raw_payload_is_decoded_and_a_review_opened()
    {
        var sink = new FakeSink();
        var r = await new Delivery(sink).HandleAsync(RawEnvelope(Good), CancellationToken.None);
        Assert.Equal(DeliveryStatus.SUCCESS, r.Status);
        var e = Assert.Single(sink.Opened);
        Assert.Equal("PR-1002", e.PurchaseRequestId);
        Assert.Equal(7380m, e.Total);
    }

    [Fact]
    public async Task A_cloudevent_with_the_body_in_data_works_too()
    {
        var sink = new FakeSink();
        var r = await new Delivery(sink).HandleAsync(Envelope($$"""{"specversion":"1.0","data":{{Good}}}"""), CancellationToken.None);
        Assert.Equal(DeliveryStatus.SUCCESS, r.Status);
        Assert.Single(sink.Opened);
    }

    [Fact]
    public async Task A_json_string_in_data_works_too()
    {
        var sink = new FakeSink();
        var escaped = JsonSerializer.Serialize(Good);
        var r = await new Delivery(sink).HandleAsync(Envelope($$"""{"data":{{escaped}}}"""), CancellationToken.None);
        Assert.Equal(DeliveryStatus.SUCCESS, r.Status);
    }

    [Theory]
    [InlineData("""{"specversion":"1.0"}""")]                       // no payload at all
    [InlineData("""{"data_base64":"***not base64***"}""")]          // not base64
    [InlineData("""{"data":42}""")]                                 // wrong shape
    [InlineData("""[1,2,3]""")]                                     // not an object
    public async Task A_broken_envelope_is_dropped_not_retried(string envelope)
    {
        var sink = new FakeSink();
        var r = await new Delivery(sink).HandleAsync(Envelope(envelope), CancellationToken.None);
        Assert.Equal(DeliveryStatus.DROP, r.Status);
        Assert.Empty(sink.Opened);
    }

    [Theory]
    [InlineData("not json at all")]
    [InlineData("""{"eventType":"deleted","purchaseRequestId":"PR-1002","requestedBy":"a@b.c","total":7380,"currency":"EUR"}""")]
    [InlineData("""{"eventType":"submitted","purchaseRequestId":"1002","requestedBy":"a@b.c","total":7380,"currency":"EUR"}""")]
    [InlineData("""{"eventType":"submitted","purchaseRequestId":"PR-1002","requestedBy":"a@b.c","total":7380,"currency":"JPY"}""")]
    [InlineData("""{"eventType":"submitted","purchaseRequestId":"PR-1002","requestedBy":"a@b.c","total":20000000,"currency":"EUR"}""")]
    public async Task A_poison_body_is_dropped_not_retried(string body)
    {
        var sink = new FakeSink();
        var r = await new Delivery(sink).HandleAsync(RawEnvelope(body), CancellationToken.None);
        Assert.Equal(DeliveryStatus.DROP, r.Status);
        Assert.Empty(sink.Opened);
    }

    [Theory]
    [InlineData(4999.99, false)]   // purchase.standard never belongs on the finance-review subscription
    [InlineData(5000, true)]
    public async Task The_threshold_is_the_one_from_episode_7(double total, bool accepted)
    {
        var body = $$"""{"eventType":"submitted","purchaseRequestId":"PR-2000","requestedBy":"a@b.c","total":{{total.ToString(System.Globalization.CultureInfo.InvariantCulture)}},"currency":"EUR"}""";
        var r = await new Delivery(new FakeSink()).HandleAsync(RawEnvelope(body), CancellationToken.None);
        Assert.Equal(accepted ? DeliveryStatus.SUCCESS : DeliveryStatus.DROP, r.Status);
        Assert.Equal(5000m, PurchaseRules.HighValueThreshold);
    }

    [Fact]
    public async Task A_failing_sink_means_retry_so_the_broker_redelivers()
    {
        var sink = new FakeSink { Throw = new InvalidOperationException("finance system is down") };
        var r = await new Delivery(sink).HandleAsync(RawEnvelope(Good), CancellationToken.None);
        Assert.Equal(DeliveryStatus.RETRY, r.Status);
        Assert.Contains("finance system is down", r.Reason);
    }

    [Fact]
    public async Task Cancellation_is_not_swallowed()
    {
        var sink = new FakeSink { Throw = new OperationCanceledException() };
        await Assert.ThrowsAsync<OperationCanceledException>(() => new Delivery(sink).HandleAsync(RawEnvelope(Good), CancellationToken.None));
    }
}
