using Microsoft.EntityFrameworkCore;

namespace ProjectRequests.Perf.Api.Data;

public class PerfDbContext(DbContextOptions<PerfDbContext> options) : DbContext(options)
{
    public DbSet<Department> Departments => Set<Department>();
    public DbSet<Requester> Requesters => Set<Requester>();
    public DbSet<ProjectRequest> Requests => Set<ProjectRequest>();

    protected override void OnModelCreating(ModelBuilder b)
    {
        b.Entity<Department>(e =>
        {
            e.Property(d => d.Code).HasMaxLength(8);
            e.HasIndex(d => d.Code).IsUnique();
        });

        b.Entity<Requester>().Property(r => r.Email).HasMaxLength(200);

        b.Entity<ProjectRequest>(e =>
        {
            e.Property(r => r.Title).HasMaxLength(100);
            e.Property(r => r.Budget).HasPrecision(18, 2);
            e.Property(r => r.Priority).HasConversion<string>().HasMaxLength(16);
            e.Property(r => r.Status).HasConversion<string>().HasMaxLength(16);
            // The list filters by department and pages by Id.
            e.HasIndex(r => new { r.DepartmentId, r.Id });
            e.HasOne(r => r.Department).WithMany().HasForeignKey(r => r.DepartmentId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(r => r.Requester).WithMany().HasForeignKey(r => r.RequesterId).OnDelete(DeleteBehavior.Restrict);
        });
    }
}
