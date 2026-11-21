using Microsoft.EntityFrameworkCore;
using PurchaseRequests.Api.Domain;

namespace PurchaseRequests.Api.Data;

public sealed class AppDbContext(DbContextOptions<AppDbContext> options) : DbContext(options)
{
    public DbSet<PurchaseRequest> PurchaseRequests => Set<PurchaseRequest>();
    public DbSet<AuditEntry> AuditEntries => Set<AuditEntry>();

    protected override void OnModelCreating(ModelBuilder b)
    {
        b.Entity<PurchaseRequest>(e =>
        {
            e.ToTable("PurchaseRequests");
            e.HasKey(x => x.Id);
            e.Property(x => x.Title).HasMaxLength(120).IsRequired();
            e.Property(x => x.Justification).HasMaxLength(2000).IsRequired();
            e.Property(x => x.Amount).HasPrecision(18, 2);
            e.Property(x => x.Currency).HasMaxLength(3).IsFixedLength().IsUnicode(false);
            e.Property(x => x.RequestedByOid).HasMaxLength(36).IsUnicode(false).IsRequired();
            e.Property(x => x.RequestedByName).HasMaxLength(200);
            e.Property(x => x.Status).HasConversion<string>().HasMaxLength(16).IsUnicode(false);
            e.Property(x => x.DecidedByOid).HasMaxLength(36).IsUnicode(false);
            e.Property(x => x.DecidedByName).HasMaxLength(200);
            e.Property(x => x.DecisionComment).HasMaxLength(500);
            e.Property(x => x.Version).IsConcurrencyToken();
            e.HasIndex(x => x.RequestedByOid);
            e.HasIndex(x => x.Status);
        });

        b.Entity<AuditEntry>(e =>
        {
            e.ToTable("AuditEntries");
            e.HasKey(x => x.Id);
            e.Property(x => x.Action).HasMaxLength(32).IsUnicode(false).IsRequired();
            e.Property(x => x.ActorOid).HasMaxLength(36).IsUnicode(false).IsRequired();
            e.Property(x => x.Detail).HasMaxLength(400);
            e.Property(x => x.CorrelationId).HasMaxLength(64).IsUnicode(false);
            e.HasIndex(x => x.RequestId);
        });
    }
}

public static class SqlConnectionGuard
{
    /// <summary>
    /// Refuse SQL authentication outside Development: in Azure the connection string must use
    /// Microsoft Entra authentication (the web app's managed identity), never a password.
    /// </summary>
    public static void Validate(string? connectionString, bool isDevelopment)
    {
        if (string.IsNullOrWhiteSpace(connectionString))
            throw new InvalidOperationException("ConnectionStrings:Sql is not set.");
        if (isDevelopment) return;

        var builder = new System.Data.Common.DbConnectionStringBuilder { ConnectionString = connectionString };
        if (builder.ContainsKey("Password") || builder.ContainsKey("Pwd"))
            throw new InvalidOperationException("Passwords are not allowed in ConnectionStrings:Sql. Use Authentication=Active Directory Default.");
        if (!builder.TryGetValue("Authentication", out var auth) || !(auth?.ToString() ?? "").StartsWith("Active Directory", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("ConnectionStrings:Sql must use Microsoft Entra authentication (Authentication=Active Directory Default).");
    }
}
