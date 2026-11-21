namespace OrderIntake.Core;

public interface ICatalog
{
    /// <summary>Unit price in euros, or null when the SKU doesn't exist.</summary>
    decimal? PriceOf(string sku);
}

/// <summary>Fictional demo catalogue. A real app would read a table or an API.</summary>
public sealed class InMemoryCatalog : ICatalog
{
    private static readonly Dictionary<string, decimal> Prices = new()
    {
        ["CBL-001"] = 4.90m,    // USB-C cable
        ["DOC-100"] = 129.00m,  // docking station
        ["MON-270"] = 219.99m,  // 27" monitor
        ["KEY-010"] = 49.50m,   // keyboard
    };

    public decimal? PriceOf(string sku) => Prices.TryGetValue(sku, out var p) ? p : null;
}

/// <summary>
/// Pricing runs in the queue-triggered function. It can fail (unknown SKU), and a failure there
/// is retried by the runtime and ends in the poison queue: that's the behaviour we want to show.
/// </summary>
public static class Pricing
{
    public const decimal DiscountThreshold = 500m;
    public const decimal DiscountRate = 0.05m;

    public static PricedOrder Price(OrderMessage order, ICatalog catalog)
    {
        var lines = order.Lines.Select(l =>
        {
            var unit = catalog.PriceOf(l.Sku) ?? throw new UnknownSkuException(l.Sku);
            return new PricedLine(l.Sku, l.Quantity, unit, Round(unit * l.Quantity));
        }).ToList();

        var subtotal = lines.Sum(l => l.LineTotal);
        var discount = subtotal >= DiscountThreshold ? Round(subtotal * DiscountRate) : 0m;
        return new PricedOrder(order.OrderId, order.CustomerId, lines, subtotal, discount,
            subtotal - discount, order.ReceivedAt);
    }

    private static decimal Round(decimal v) => Math.Round(v, 2, MidpointRounding.AwayFromZero);
}
