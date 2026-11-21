using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.DependencyInjection;

namespace ProjectRequests.Api.Tests;

/// <summary>
/// The real app, in memory, on its own SQLite file. The app applies the real migrations at startup
/// (Database:MigrateOnStartup). Tests can change the environment, settings and services.
/// </summary>
public sealed class RequestsApiFactory : WebApplicationFactory<Program>
{
    private readonly string _environment;
    private readonly Dictionary<string, string> _settings;
    private readonly Action<IServiceCollection>? _services;

    public string DatabasePath { get; }

    public RequestsApiFactory(
        string environment = "Development",
        Dictionary<string, string>? settings = null,
        Action<IServiceCollection>? services = null,
        string? databasePath = null)
    {
        _environment = environment;
        _settings = settings ?? [];
        _services = services;
        DatabasePath = databasePath ?? Path.Combine(Path.GetTempPath(), $"requests-{Guid.NewGuid():N}.db");
    }

    /// <summary>Point a second app instance at an existing database file (restart test).</summary>
    public static RequestsApiFactory ForExistingDatabase(string databasePath) => new(databasePath: databasePath);

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment(_environment);
        builder.UseSetting("Database:Provider", "Sqlite");
        builder.UseSetting("ConnectionStrings:Requests", $"Data Source={DatabasePath}");
        builder.UseSetting("Database:MigrateOnStartup", "true");
        builder.UseSetting("Notifications:DigestInterval", "4.00:00:00");   // real clock: never fires during a test
        builder.UseSetting("Notifications:StaleAfterDays", "3");            // appsettings.Development.json says 0
        builder.UseSetting("Logging:LogLevel:Microsoft.EntityFrameworkCore.Database.Command", "Warning");
        foreach (var (key, value) in _settings)
            builder.UseSetting(key, value);

        if (_services is not null)
            builder.ConfigureTestServices(_services);               // runs after Program's registrations: last one wins
    }

    public void DeleteDatabase()
    {
        SqliteConnection.ClearAllPools();                            // pooled connections keep the file open
        File.Delete(DatabasePath);
    }
}
