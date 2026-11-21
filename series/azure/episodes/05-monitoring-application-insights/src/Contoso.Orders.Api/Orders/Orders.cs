namespace Contoso.Orders.Api.Orders;

/// <summary>What the client POSTs to /orders. Channel is "web" or "partner" (a metric dimension).</summary>
public sealed record OrderLine(string Sku, int Quantity);

public sealed record OrderRequest(string? CustomerId, string? Channel, IReadOnlyList<OrderLine>? Lines);

public sealed record PricedLine(string Sku, int Quantity, decimal UnitPrice, decimal LineTotal);

/// <summary>What is stored as orders/{OrderId}.json.</summary>
public sealed record StoredOrder(
    string OrderId,
    string CustomerId,
    string Channel,
    IReadOnlyList<PricedLine> Lines,
    decimal Total,
    DateTimeOffset CreatedAt);

public sealed class UnknownSkuException(string sku) : Exception($"Unknown SKU '{sku}'.")
{
    public string Sku { get; } = sku;
}

/// <summary>Same fictional catalogue as episode 1.</summary>
public static class Catalog
{
    private static readonly Dictionary<string, decimal> Prices = new()
    {
        ["CBL-001"] = 4.90m,    // USB-C cable
        ["DOC-100"] = 129.00m,  // docking station
        ["MON-270"] = 219.99m,  // 27" monitor
        ["KEY-010"] = 49.50m,   // keyboard
    };

    public static IReadOnlyList<PricedLine> Price(IReadOnlyList<OrderLine> lines) =>
        lines.Select(l =>
        {
            var unit = Prices.TryGetValue(l.Sku, out var p) ? p : throw new UnknownSkuException(l.Sku);
            return new PricedLine(l.Sku, l.Quantity, unit, Math.Round(unit * l.Quantity, 2));
        }).ToList();
}

public static class OrderRules
{
    public static readonly string[] Channels = ["web", "partner"];

    /// <summary>Shape checks only; an unknown SKU is a business error (422), found while pricing.</summary>
    public static Dictionary<string, string[]> Validate(OrderRequest? order)
    {
        var errors = new Dictionary<string, string[]>();
        if (order is null)
        {
            errors["body"] = ["A JSON order is required."];
            return errors;
        }
        if (string.IsNullOrWhiteSpace(order.CustomerId))
            errors["customerId"] = ["customerId is required."];
        if (order.Channel is null || !Channels.Contains(order.Channel))
            errors["channel"] = ["channel must be 'web' or 'partner'."];
        if (order.Lines is null || order.Lines.Count is < 1 or > 20)
            errors["lines"] = ["An order has 1 to 20 lines."];
        else if (order.Lines.Any(l => l.Quantity is < 1 or > 100))
            errors["lines"] = ["Quantity must be 1 to 100."];
        return errors;
    }
}
