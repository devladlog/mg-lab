using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.Extensions.Logging;

namespace Contoso.Portfolio;

/// <summary>EF Core 10 + SQLite. Every executed SQL command can be sent to <c>sqlLog</c>.</summary>
public sealed class PortfolioDb(string connectionString, Action<string>? sqlLog = null) : DbContext
{
    public DbSet<Department> Departments => Set<Department>();
    public DbSet<ProjectRequest> Requests => Set<ProjectRequest>();

    protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
    {
        optionsBuilder.UseSqlite(connectionString);
        if (sqlLog is not null)
            optionsBuilder.LogTo(sqlLog, [RelationalEventId.CommandExecuted], LogLevel.Information, DbContextLoggerOptions.None);
    }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Department>().HasKey(d => d.Code);
        modelBuilder.Entity<ProjectRequest>().HasKey(r => r.Id);
        modelBuilder.Entity<ProjectRequest>().Property(r => r.Status).HasConversion<string>();
    }

    /// <summary>Recreates the database file and loads the sample portfolio.</summary>
    public static async Task<PortfolioDb> CreateFreshAsync(string path, Action<string>? sqlLog = null, CancellationToken ct = default)
    {
        await using (var setup = new PortfolioDb($"Data Source={path}"))
        {
            await setup.Database.EnsureDeletedAsync(ct);
            await setup.Database.EnsureCreatedAsync(ct);
            setup.Departments.AddRange(SampleData.Departments);
            setup.Requests.AddRange(SampleData.Requests);
            await setup.SaveChangesAsync(ct);
        }
        return new PortfolioDb($"Data Source={path}", sqlLog);
    }
}
