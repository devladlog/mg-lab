using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace ProjectRequests.Api.Data;

public static class DatabaseSetup
{
    /// <summary>
    /// Registers the DbContext for the provider in "Database:Provider":
    /// "Sqlite" (local development, tests) or "SqlServer" (Azure SQL Database).
    /// Endpoints always ask for <see cref="RequestsDbContext"/>.
    /// </summary>
    public static IServiceCollection AddRequestsDatabase(this IServiceCollection services, IConfiguration config)
    {
        var provider = config["Database:Provider"] ?? "Sqlite";
        var connectionString = config.GetConnectionString("Requests");
        if (string.IsNullOrWhiteSpace(connectionString))
            throw new InvalidOperationException("Connection string 'Requests' is missing (ConnectionStrings:Requests).");

        switch (provider)
        {
            case "SqlServer":
                services.AddDbContext<RequestsDbContext>(o => o.UseSqlServer(connectionString,
                    sql => sql.EnableRetryOnFailure()));          // transient Azure SQL errors are retried
                break;

            case "Sqlite":
                services.AddDbContext<SqliteRequestsDbContext>(o => o.UseSqlite(connectionString));
                services.AddScoped<RequestsDbContext>(sp => sp.GetRequiredService<SqliteRequestsDbContext>());
                break;

            default:
                throw new InvalidOperationException($"Unsupported Database:Provider '{provider}'.");
        }

        return services;
    }

    /// <summary>
    /// Applies pending migrations at startup when "Database:MigrateOnStartup" is true.
    /// Used by the integration tests. In Azure we apply a reviewed, idempotent SQL script instead.
    /// </summary>
    public static async Task MigrateIfConfiguredAsync(this WebApplication app)
    {
        if (!app.Configuration.GetValue<bool>("Database:MigrateOnStartup"))
            return;

        await using var scope = app.Services.CreateAsyncScope();
        var db = scope.ServiceProvider.GetRequiredService<RequestsDbContext>();
        await db.Database.MigrateAsync();
    }
}

/// <summary>
/// Design-time only: lets "dotnet ef migrations add --context RequestsDbContext" build the SQL Server model
/// without a SQL Server. Adding migrations and generating scripts never opens this connection.
/// </summary>
public sealed class SqlServerDesignTimeFactory : IDesignTimeDbContextFactory<RequestsDbContext>
{
    public RequestsDbContext CreateDbContext(string[] args) =>
        new(new DbContextOptionsBuilder<RequestsDbContext>()
            .UseSqlServer("Server=design-time-only;Database=ProjectRequests")
            .Options);
}
