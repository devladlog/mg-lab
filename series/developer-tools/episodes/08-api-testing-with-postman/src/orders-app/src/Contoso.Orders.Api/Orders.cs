using System.ComponentModel.DataAnnotations;
using Microsoft.EntityFrameworkCore;

namespace Contoso.Orders.Api;

public sealed class Order
{
    public int Id { get; set; }
    [MaxLength(100)] public required string Customer { get; set; }
    public decimal Total { get; set; }
    public DateOnly Created { get; set; }
}

public sealed record NewOrder(string? Customer, decimal Total);

/// <summary>Body of GET /healthz. Named type (not an anonymous object) so the OpenAPI document can describe it.</summary>
public sealed record Health(string Status, string Version, string? Database, string Dotnet, string Os, string User,
    bool InContainer);

public sealed record Page<T>(int PageNumber, int PageSize, int Total, IReadOnlyList<T> Items)
{
    public int TotalPages => Total == 0 ? 0 : (Total + PageSize - 1) / PageSize;
}

/// <summary>Paging rules shared by every list endpoint (episode 1's "feat(orders): add paging").</summary>
public static class Paging
{
    public const int DefaultPageSize = 50;
    public const int MaxPageSize = 100;

    public static (int Page, int Size)? Normalize(int? page, int? pageSize)
    {
        var p = page ?? 1;
        if (p < 1) return null;
        return (p, Math.Clamp(pageSize ?? DefaultPageSize, 1, MaxPageSize));
    }
}

public sealed class OrdersDb(DbContextOptions<OrdersDb> options) : DbContext(options)
{
    public DbSet<Order> Orders => Set<Order>();

    protected override void OnModelCreating(ModelBuilder model)
    {
        model.Entity<Order>().Property(o => o.Total).HasPrecision(10, 2);
        model.Entity<Order>().HasIndex(o => o.Created);
    }

    private static readonly string[] Customers =
        ["Contoso Retail", "Fabrikam", "Northwind Traders", "Adventure Works", "Tailspin Toys"];

    /// <summary>Same deterministic data as episode 3's in-memory catalog.</summary>
    public static IEnumerable<Order> SeedData(int count)
    {
        var start = new DateOnly(2026, 1, 1);
        return Enumerable.Range(1, count).Select(i => new Order
        {
            Customer = Customers[i % Customers.Length],
            Total = Math.Round(25m + (i * 37 % 1000) + (i % 100) / 100m, 2),
            Created = start.AddDays(i % 300),
        });
    }
}

public static class Database
{
    /// <summary>Database:Provider picks the engine: Sqlite for a single container or local runs,
    /// SqlServer when Compose starts a SQL Server container next to the API.</summary>
    public static IServiceCollection AddOrdersDb(this IServiceCollection services, IConfiguration config)
    {
        var provider = config["Database:Provider"] ?? "Sqlite";
        var cs = config.GetConnectionString("Orders")
                 ?? throw new InvalidOperationException("ConnectionStrings:Orders is not set");
        return provider switch
        {
            "Sqlite" => services.AddDbContext<OrdersDb>(o => o.UseSqlite(cs)),
            "SqlServer" => services.AddDbContext<OrdersDb>(o => o.UseSqlServer(cs,
                sql => sql.EnableRetryOnFailure(maxRetryCount: 5))),
            _ => throw new InvalidOperationException(
                $"Database:Provider '{provider}' is not supported (use Sqlite or SqlServer)"),
        };
    }

    public static async Task InitializeAsync(IServiceProvider services, int seedCount)
    {
        using var scope = services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<OrdersDb>();
        await db.Database.EnsureCreatedAsync();     // demo app: no migrations
        if (!await db.Orders.AnyAsync())
        {
            db.Orders.AddRange(OrdersDb.SeedData(seedCount));
            await db.SaveChangesAsync();
        }
    }
}
