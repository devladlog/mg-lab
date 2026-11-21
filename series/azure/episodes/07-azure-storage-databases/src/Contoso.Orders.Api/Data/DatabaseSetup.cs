using Microsoft.Data.SqlClient;
using Microsoft.EntityFrameworkCore;

namespace Contoso.Orders.Api.Data;

public sealed class DatabaseOptions
{
    /// <summary>"SqlServer" (Azure SQL Database) or "Sqlite" (local runs and tests).</summary>
    public string Provider { get; set; } = "Sqlite";

    /// <summary>Server FQDN from the Bicep output, e.g. sql-contoso-xxxx.database.windows.net.</summary>
    public string? Server { get; set; }
    public string? Database { get; set; }

    public string SqliteConnectionString { get; set; } = "Data Source=orders-local.db";
}

public static class DatabaseSetup
{
    /// <summary>
    /// Azure SQL connection string with no secret in it: Microsoft Entra ID through DefaultAzureCredential
    /// (managed identity in Azure, your az login on a laptop). Connect Timeout 60 s because a paused
    /// serverless database resumes on the first connection, which fails with 40613 meanwhile.
    /// </summary>
    public static string AzureSqlConnectionString(string server, string database) => new SqlConnectionStringBuilder
    {
        DataSource = $"tcp:{server},1433",
        InitialCatalog = database,
        Authentication = SqlAuthenticationMethod.ActiveDirectoryDefault,
        Encrypt = SqlConnectionEncryptOption.Mandatory,
        TrustServerCertificate = false,
        ConnectTimeout = 60,
        ApplicationName = "contoso-orders-api",
    }.ConnectionString;

    public static void Configure(DbContextOptionsBuilder b, DatabaseOptions o)
    {
        if (string.Equals(o.Provider, "SqlServer", StringComparison.OrdinalIgnoreCase))
        {
            if (string.IsNullOrWhiteSpace(o.Server) || string.IsNullOrWhiteSpace(o.Database))
                throw new InvalidOperationException("Database:Server and Database:Database are required for SqlServer.");

            b.UseSqlServer(AzureSqlConnectionString(o.Server, o.Database), sql =>
                // Retries transient errors, 40613 (database not currently available) included.
                // A retried SaveChanges can re-run an INSERT whose commit actually succeeded:
                // the unique IdempotencyKey index turns that into a replay instead of a duplicate.
                sql.EnableRetryOnFailure(maxRetryCount: 6, maxRetryDelay: TimeSpan.FromSeconds(30), errorNumbersToAdd: null));
        }
        else
        {
            b.UseSqlite(o.SqliteConnectionString);
        }
    }

    /// <summary>T-SQL for the current model (what db/schema.sql must contain). Doesn't open a connection.</summary>
    public static string SqlServerCreateScript()
    {
        var options = new DbContextOptionsBuilder<OrdersDbContext>()
            .UseSqlServer("Server=tcp:schema-only.invalid,1433;Database=orders").Options;
        using var db = new OrdersDbContext(options);
        return db.Database.GenerateCreateScript();
    }
}
