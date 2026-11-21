using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Microsoft.EntityFrameworkCore.Storage.ValueConversion;

namespace ProjectRequests.Api.Data;

/// <summary>
/// The application's DbContext. Used as-is with SQL Server / Azure SQL; SQLite uses the derived
/// <see cref="SqliteRequestsDbContext"/> so each provider keeps its own set of migrations.
/// </summary>
public class RequestsDbContext : DbContext
{
    public RequestsDbContext(DbContextOptions<RequestsDbContext> options) : base(options) { }

    /// <summary>For derived contexts (one per provider): they pass their own typed options.</summary>
    protected RequestsDbContext(DbContextOptions options) : base(options) { }

    public DbSet<ProjectRequest> Requests => Set<ProjectRequest>();
    public DbSet<Department> Departments => Set<Department>();

    protected override void OnModelCreating(ModelBuilder modelBuilder) =>
        modelBuilder.ApplyConfigurationsFromAssembly(typeof(RequestsDbContext).Assembly);

    /// <summary>
    /// Databases drop DateTime.Kind: values come back as Unspecified, and JSON loses the "Z".
    /// We only ever store UTC, so every DateTime read from the database is marked UTC again.
    /// </summary>
    protected override void ConfigureConventions(ModelConfigurationBuilder configurationBuilder) =>
        configurationBuilder.Properties<DateTime>().HaveConversion<UtcDateTimeConverter>();
}

internal sealed class UtcDateTimeConverter() : ValueConverter<DateTime, DateTime>(
    toDatabase => toDatabase.ToUniversalTime(),
    fromDatabase => DateTime.SpecifyKind(fromDatabase, DateTimeKind.Utc));

/// <summary>Same model, SQLite migrations (Migrations/Sqlite). Local development and tests.</summary>
public sealed class SqliteRequestsDbContext(DbContextOptions<SqliteRequestsDbContext> options)
    : RequestsDbContext(options);

internal sealed class ProjectRequestConfiguration : IEntityTypeConfiguration<ProjectRequest>
{
    public void Configure(EntityTypeBuilder<ProjectRequest> e)
    {
        e.ToTable("ProjectRequests");
        e.Property(r => r.Title).HasMaxLength(100).IsRequired();
        e.Property(r => r.Budget).HasPrecision(18, 2);            // decimal(18,2) on SQL Server
        e.Property(r => r.RequestedBy).HasMaxLength(254).IsRequired();
        e.Property(r => r.DecidedBy).HasMaxLength(254);
        e.Property(r => r.Justification).HasMaxLength(2000);
        e.Property(r => r.Priority).HasConversion<string>().HasMaxLength(16);   // readable in the table
        e.Property(r => r.Status).HasConversion<string>().HasMaxLength(16);
        e.Property(r => r.Version).IsConcurrencyToken();          // UPDATE ... WHERE Id = @id AND Version = @v

        e.HasOne(r => r.Department).WithMany(d => d.Requests)
            .HasForeignKey(r => r.DepartmentId)
            .OnDelete(DeleteBehavior.Restrict);                   // no cascade: requests are records

        e.HasIndex(r => new { r.Status, r.Priority });            // 2nd migration: the list filters on these
    }
}

internal sealed class DepartmentConfiguration : IEntityTypeConfiguration<Department>
{
    public void Configure(EntityTypeBuilder<Department> e)
    {
        e.Property(d => d.Code).HasMaxLength(8).IsRequired();
        e.Property(d => d.Name).HasMaxLength(100).IsRequired();
        e.HasIndex(d => d.Code).IsUnique();

        e.HasData(                                                // part of the migration, same on every database
            new Department { Id = 1, Code = "FIN", Name = "Finance" },
            new Department { Id = 2, Code = "IT", Name = "Information Technology" },
            new Department { Id = 3, Code = "OPS", Name = "Operations" });
    }
}
