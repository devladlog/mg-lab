using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Data.Sqlite;

namespace ProjectRequests.Api.Tests;

/// <summary>
/// The real app, in memory, on its own SQLite file. The app applies the real migrations at startup
/// (Database:MigrateOnStartup), so every integration test also proves the migrations work.
/// </summary>
public sealed class RequestsApiFactory : WebApplicationFactory<Program>
{
    public string DatabasePath { get; }

    public RequestsApiFactory() : this(Path.Combine(Path.GetTempPath(), $"requests-{Guid.NewGuid():N}.db")) { }

    /// <summary>Point a second app instance at an existing database file (restart test).</summary>
    public RequestsApiFactory(string databasePath) => DatabasePath = databasePath;

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Development");
        builder.UseSetting("Database:Provider", "Sqlite");
        builder.UseSetting("ConnectionStrings:Requests", $"Data Source={DatabasePath}");
        builder.UseSetting("Database:MigrateOnStartup", "true");
        builder.UseSetting("Logging:LogLevel:Microsoft.EntityFrameworkCore.Database.Command", "Warning");
    }

    public void DeleteDatabase()
    {
        SqliteConnection.ClearAllPools();                        // pooled connections keep the file open
        File.Delete(DatabasePath);
    }
}
