namespace Contoso.Orders.Api.Orders;

/// <summary>One order. <see cref="Id"/> is an identity column: a narrow, ever-increasing clustered key.</summary>
public sealed class Order
{
    public long Id { get; set; }
    public required string CustomerId { get; set; }

    /// <summary>Client-supplied Idempotency-Key header. Unique in the database, not just in code.</summary>
    public required string IdempotencyKey { get; set; }

    /// <summary>SHA-256 of the normalised request: the same key with a different body is a conflict, not a replay.</summary>
    public required string RequestHash { get; set; }

    public DateTime CreatedUtc { get; set; }
    public string Status { get; set; } = OrderStatus.Placed;
    public decimal Total { get; set; }

    /// <summary>Optimistic concurrency token, sent to clients as the ETag.</summary>
    public Guid Version { get; set; } = Guid.NewGuid();

    public List<OrderLine> Lines { get; set; } = [];
}

public sealed class OrderLine
{
    public long Id { get; set; }
    public long OrderId { get; set; }
    public required string Sku { get; set; }
    public int Quantity { get; set; }
    public decimal UnitPrice { get; set; }
}

public static class OrderStatus
{
    public const string Placed = "Placed";
    public const string Cancelled = "Cancelled";
}

public sealed record OrderLineRequest(string? Sku, int Quantity);
public sealed record CreateOrderRequest(string? CustomerId, List<OrderLineRequest>? Lines);

public sealed record OrderLineDto(string Sku, int Quantity, decimal UnitPrice);
public sealed record OrderDto(long Id, string CustomerId, DateTime CreatedUtc, string Status, decimal Total, IReadOnlyList<OrderLineDto> Lines)
{
    public static OrderDto From(Order o) => new(
        o.Id, o.CustomerId, DateTime.SpecifyKind(o.CreatedUtc, DateTimeKind.Utc), o.Status, o.Total,
        o.Lines.OrderBy(l => l.Sku, StringComparer.Ordinal).Select(l => new OrderLineDto(l.Sku, l.Quantity, l.UnitPrice)).ToList());
}

public sealed record OrderPage(IReadOnlyList<OrderDto> Items, string? Next);
