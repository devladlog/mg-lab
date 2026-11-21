using Microsoft.EntityFrameworkCore;
using TenantApi.Tenancy;

namespace TenantApi.Data;

public sealed class CrossTenantWriteException(string message) : InvalidOperationException(message);

public sealed class AppDbContext(DbContextOptions<AppDbContext> options, TenantContext tenant) : DbContext(options)
{
    public DbSet<Tenant> Tenants => Set<Tenant>();
    public DbSet<PurchaseRequest> PurchaseRequests => Set<PurchaseRequest>();

    // Read by the query filter on every query this context instance runs (EF evaluates it per instance).
    public Guid CurrentTenantId => tenant.TenantId;

    protected override void OnModelCreating(ModelBuilder b)
    {
        b.Entity<Tenant>(e =>
        {
            e.ToTable("Tenants");
            e.HasKey(t => t.TenantId);
            e.Property(t => t.Name).HasMaxLength(200);
            e.Property(t => t.Plan).HasMaxLength(20);
            e.Property(t => t.Status).HasMaxLength(20);
        });

        b.Entity<PurchaseRequest>(e =>
        {
            e.ToTable("PurchaseRequests");
            // The tenant is part of the key: the same Id in two tenants is two different rows.
            e.HasKey(p => new { p.TenantId, p.Id });
            e.Property(p => p.Title).HasMaxLength(200);
            e.Property(p => p.Status).HasMaxLength(20);
            e.Property(p => p.CreatedBy).HasMaxLength(64);
            e.Property(p => p.Amount).HasPrecision(18, 2);
            e.HasQueryFilter(p => p.TenantId == CurrentTenantId);
        });
    }

    public override int SaveChanges(bool acceptAllChangesOnSuccess)
    {
        EnforceTenantOnWrites();
        return base.SaveChanges(acceptAllChangesOnSuccess);
    }

    public override Task<int> SaveChangesAsync(bool acceptAllChangesOnSuccess, CancellationToken cancellationToken = default)
    {
        EnforceTenantOnWrites();
        return base.SaveChangesAsync(acceptAllChangesOnSuccess, cancellationToken);
    }

    /// <summary>
    /// The query filter protects reads. This protects writes: new rows get the current tenant, a row for another
    /// tenant is refused, and TenantId can never be changed. The database policy (sql/002-rls.sql) repeats the rule.
    /// </summary>
    void EnforceTenantOnWrites()
    {
        foreach (var entry in ChangeTracker.Entries<ITenantScoped>())
        {
            if (entry.State == EntityState.Added)
            {
                if (CurrentTenantId == Guid.Empty)
                    throw new CrossTenantWriteException("No tenant in context: refusing to write tenant data.");
                if (entry.Entity.TenantId == Guid.Empty) entry.Entity.TenantId = CurrentTenantId;
                else if (entry.Entity.TenantId != CurrentTenantId)
                    throw new CrossTenantWriteException("Refusing to write a row that belongs to another tenant.");
            }
            else if (entry.State == EntityState.Modified && entry.Property(nameof(ITenantScoped.TenantId)).IsModified)
            {
                throw new CrossTenantWriteException("TenantId is immutable.");
            }
        }
    }
}
