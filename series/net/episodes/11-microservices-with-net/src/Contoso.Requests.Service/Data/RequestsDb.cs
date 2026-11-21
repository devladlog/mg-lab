using Microsoft.EntityFrameworkCore;

namespace Contoso.Requests.Service.Data;

/// <summary>Where the budget stands for a request. Pending = the Budget service could not be asked (yet).</summary>
public enum BudgetState { Pending, Reserved, Declined }

public sealed class ProjectRequest
{
    public int Id { get; set; }
    public string Title { get; set; } = "";
    public string Department { get; set; } = "";
    public decimal Amount { get; set; }
    public string RequestedBy { get; set; } = "";

    /// <summary>Sent to the Budget service with every attempt, including the later re-checks: the same key, always.</summary>
    public Guid IdempotencyKey { get; set; }

    public BudgetState BudgetState { get; set; }
    public Guid? ReservationId { get; set; }
    public string? TraceId { get; set; }
    public DateTime CreatedAtUtc { get; set; }
}

public sealed class RequestsDb(DbContextOptions<RequestsDb> options) : DbContext(options)
{
    public DbSet<ProjectRequest> Requests => Set<ProjectRequest>();

    protected override void OnModelCreating(ModelBuilder model)
    {
        model.Entity<ProjectRequest>(e =>
        {
            e.Property(r => r.Title).HasMaxLength(100);
            e.Property(r => r.Department).HasMaxLength(8);
            e.Property(r => r.RequestedBy).HasMaxLength(254);
            e.Property(r => r.BudgetState).HasConversion<string>().HasMaxLength(16);
            e.HasIndex(r => r.IdempotencyKey).IsUnique();   // the same key can never create a second request
            e.HasIndex(r => r.BudgetState);
        });
    }
}
