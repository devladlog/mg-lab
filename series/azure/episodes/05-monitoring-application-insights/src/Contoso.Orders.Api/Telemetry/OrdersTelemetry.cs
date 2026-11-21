using System.Diagnostics;
using System.Diagnostics.Metrics;

namespace Contoso.Orders.Api.Telemetry;

/// <summary>
/// The app's own signals. Spans explain one request (they can be sampled); metrics count every
/// order (metrics are never sampled), so alerts and dashboards should prefer metrics.
/// </summary>
public sealed class OrdersTelemetry
{
    public const string SourceName = "Contoso.Orders";
    public const string MeterName = "Contoso.Orders";

    // ActivitySource = OpenTelemetry tracer. It must be registered with AddSource(SourceName).
    public static readonly ActivitySource Source = new(SourceName);

    private readonly Counter<long> created;
    private readonly Counter<long> rejected;
    private readonly Histogram<double> value;

    public OrdersTelemetry(IMeterFactory meterFactory)
    {
        var meter = meterFactory.Create(MeterName);
        created = meter.CreateCounter<long>("contoso.orders.created", unit: "{order}",
            description: "Orders accepted and stored.");
        rejected = meter.CreateCounter<long>("contoso.orders.rejected", unit: "{order}",
            description: "Orders refused: invalid shape or unknown SKU.");
        value = meter.CreateHistogram<double>("contoso.orders.value", unit: "EUR",
            description: "Order total in euros.");
    }

    /// <summary>Low-cardinality dimensions only: channel, never the customer or the order id.</summary>
    public void OrderCreated(string channel, decimal total)
    {
        var tag = new KeyValuePair<string, object?>("order.channel", channel);
        created.Add(1, tag);
        value.Record((double)total, tag);
    }

    public void OrderRejected(string reason) =>
        rejected.Add(1, new KeyValuePair<string, object?>("order.reject_reason", reason));
}
