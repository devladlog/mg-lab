namespace Contoso.Orders.Api;

public sealed record Order(int Id, string Customer, decimal Total, DateOnly Created);

public sealed record Page<T>(int PageNumber, int PageSize, int Total, IReadOnlyList<T> Items)
{
    public int TotalPages => Total == 0 ? 0 : (Total + PageSize - 1) / PageSize;
}

/// <summary>Paging rules shared by every list endpoint (the "feat(orders): add paging" change from episode 1).</summary>
public static class Paging
{
    public const int DefaultPageSize = 50;
    public const int MaxPageSize = 100;

    /// <summary>Returns null when the page number is invalid; clamps the page size into 1..MaxPageSize.</summary>
    public static (int Page, int Size)? Normalize(int? page, int? pageSize)
    {
        var p = page ?? 1;
        if (p < 1) return null;
        var s = Math.Clamp(pageSize ?? DefaultPageSize, 1, MaxPageSize);
        return (p, s);
    }
}

/// <summary>In-memory orders, seeded deterministically. Episode 4 replaces this with a real database.</summary>
public sealed class OrderCatalog
{
    private static readonly string[] Customers =
        ["Contoso Retail", "Fabrikam", "Northwind Traders", "Adventure Works", "Tailspin Toys"];

    private readonly List<Order> _orders;

    public OrderCatalog(IEnumerable<Order> orders) => _orders = orders.OrderBy(o => o.Id).ToList();

    public static OrderCatalog Seed(int count)
    {
        var start = new DateOnly(2026, 1, 1);
        var orders = Enumerable.Range(1, count).Select(i => new Order(
            Id: i,
            Customer: Customers[i % Customers.Length],
            Total: Math.Round(25m + (i * 37 % 1000) + (i % 100) / 100m, 2),
            Created: start.AddDays(i % 300)));
        return new OrderCatalog(orders);
    }

    public int Count => _orders.Count;

    public Order? Find(int id) => _orders.FirstOrDefault(o => o.Id == id);

    public Page<Order> GetPage(int page, int pageSize)
    {
        var items = _orders.Skip((page - 1) * pageSize).Take(pageSize).ToList();
        return new Page<Order>(page, pageSize, _orders.Count, items);
    }
}
