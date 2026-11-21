namespace OrderIntake.Core;

/// <summary>What the client POSTs to /api/orders.</summary>
public sealed record OrderLine(string Sku, int Quantity);

public sealed record OrderRequest(string CustomerId, IReadOnlyList<OrderLine> Lines);

/// <summary>What goes on the queue: the request plus an id and a timestamp.</summary>
public sealed record OrderMessage(string OrderId, string CustomerId, IReadOnlyList<OrderLine> Lines, DateTimeOffset ReceivedAt);

public sealed record PricedLine(string Sku, int Quantity, decimal UnitPrice, decimal LineTotal);

/// <summary>What the queue-triggered function writes to blob storage.</summary>
public sealed record PricedOrder(
    string OrderId,
    string CustomerId,
    IReadOnlyList<PricedLine> Lines,
    decimal Subtotal,
    decimal Discount,
    decimal Total,
    DateTimeOffset ReceivedAt);

public sealed class UnknownSkuException(string sku) : Exception($"Unknown SKU '{sku}'.")
{
    public string Sku { get; } = sku;
}
