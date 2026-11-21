using Contoso.Orders.Api.Orders;
using Microsoft.EntityFrameworkCore;

namespace Contoso.Orders.Api.Data;

public sealed class OrdersDbContext(DbContextOptions<OrdersDbContext> options) : DbContext(options)
{
    public DbSet<Order> Orders => Set<Order>();
    public DbSet<OrderLine> OrderLines => Set<OrderLine>();

    protected override void OnModelCreating(ModelBuilder b)
    {
        b.Entity<Order>(o =>
        {
            o.ToTable("Orders");
            o.HasKey(x => x.Id);
            o.Property(x => x.CustomerId).HasMaxLength(64).IsRequired();
            o.Property(x => x.IdempotencyKey).HasMaxLength(64).IsRequired();
            o.Property(x => x.RequestHash).HasMaxLength(64).IsFixedLength().IsUnicode(false).IsRequired();
            o.Property(x => x.Status).HasMaxLength(16).IsUnicode(false).IsRequired();
            o.Property(x => x.Total).HasPrecision(10, 2);
            o.Property(x => x.Version).IsConcurrencyToken();

            // The database enforces idempotency: a retried INSERT can't create a second order
            o.HasIndex(x => x.IdempotencyKey).IsUnique();

            // Keyset paging: "this customer's orders, newest first, after (CreatedUtc, Id)"
            o.HasIndex(x => new { x.CustomerId, x.CreatedUtc, x.Id }).IsDescending(false, true, true);

            o.HasMany(x => x.Lines).WithOne().HasForeignKey(l => l.OrderId).OnDelete(DeleteBehavior.Cascade);
        });

        b.Entity<OrderLine>(l =>
        {
            l.ToTable("OrderLines");
            l.Property(x => x.Sku).HasMaxLength(7).IsUnicode(false).IsRequired();
            l.Property(x => x.UnitPrice).HasPrecision(10, 2);
        });
    }
}
