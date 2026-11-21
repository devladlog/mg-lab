using System.Diagnostics;
using Contoso.Orders.Api.Telemetry;

namespace Contoso.Orders.Api.Orders;

public static partial class OrderEndpoints
{
    public static void MapOrders(this WebApplication app)
    {
        app.MapPost("/orders", CreateOrder);
        app.MapGet("/orders/{orderId}", async (string orderId, IOrderStore store, CancellationToken ct) =>
            await store.FindAsync(orderId, ct) is { } order ? Results.Ok(order) : Results.NotFound());
    }

    internal static async Task<IResult> CreateOrder(OrderRequest? order, IOrderStore store,
        OrdersTelemetry telemetry, TimeProvider clock, ILogger<OrderRequest> logger, CancellationToken ct)
    {
        var errors = OrderRules.Validate(order);
        if (errors.Count > 0)
        {
            telemetry.OrderRejected("invalid");
            return Results.ValidationProblem(errors);                         // 400, not a failure
        }

        var (customerId, channel, requested) = (order!.CustomerId!, order.Channel!, order.Lines!);
        var orderId = Guid.NewGuid().ToString("N");
        IReadOnlyList<PricedLine> lines;
        using (var span = OrdersTelemetry.Source.StartActivity("orders.price"))  // Internal span -> dependencies table
        {
            span?.SetTag("order.id", orderId);
            span?.SetTag("order.channel", channel);
            span?.SetTag("order.line_count", requested.Count);
            try
            {
                lines = Catalog.Price(requested);
            }
            catch (UnknownSkuException e)
            {
                span?.SetStatus(ActivityStatusCode.Error, "unknown SKU");
                telemetry.OrderRejected("unknown_sku");
                LogUnknownSku(logger, orderId, e.Sku);
                return Results.Problem(e.Message, statusCode: StatusCodes.Status422UnprocessableEntity);
            }
            span?.SetTag("order.total", (double)lines.Sum(l => l.LineTotal));
        }

        var stored = new StoredOrder(orderId, customerId, channel, lines,
            lines.Sum(l => l.LineTotal), clock.GetUtcNow());
        await store.SaveAsync(stored, ct);                                   // -> Azure blob dependency

        telemetry.OrderCreated(stored.Channel, stored.Total);
        LogCreated(logger, orderId, stored.Channel, lines.Count, stored.Total);
        return Results.Created($"/orders/{orderId}", new { orderId, total = stored.Total });
    }

    // Source-generated, structured: OrderId, Channel, ... become customDimensions in the traces table.
    // The customer id is deliberately not logged.
    [LoggerMessage(Level = LogLevel.Information,
        Message = "Order {OrderId} created via {Channel}: {LineCount} lines, total {Total}")]
    private static partial void LogCreated(ILogger logger, string orderId, string channel, int lineCount, decimal total);

    [LoggerMessage(Level = LogLevel.Warning, Message = "Order {OrderId} refused: unknown SKU {Sku}")]
    private static partial void LogUnknownSku(ILogger logger, string orderId, string sku);
}
