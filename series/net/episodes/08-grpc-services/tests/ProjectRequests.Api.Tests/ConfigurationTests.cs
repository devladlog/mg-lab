using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using ProjectRequests.Api.Data;

namespace ProjectRequests.Api.Tests;

/// <summary>The Azure wiring, checked without Azure: no connection is opened in these tests.</summary>
public sealed class ConfigurationTests
{
    private const string AzureSql =
        "Server=tcp:contoso-sql.database.windows.net,1433;Database=requests;Authentication=Active Directory Default;Encrypt=True;";

    private static ServiceProvider Build(Dictionary<string, string?> settings)
    {
        var config = new ConfigurationBuilder().AddInMemoryCollection(settings).Build();
        return new ServiceCollection().AddRequestsDatabase(config).BuildServiceProvider();
    }

    [Fact]
    public void App_Service_connection_string_env_var_becomes_ConnectionStrings()
    {
        // App Service exposes a connection string of type SQLAzure as SQLAZURECONNSTR_<name>.
        Environment.SetEnvironmentVariable("SQLAZURECONNSTR_MglabProbe", AzureSql);
        try
        {
            var config = new ConfigurationBuilder().AddEnvironmentVariables().Build();
            Assert.Equal(AzureSql, config.GetConnectionString("MglabProbe"));
        }
        finally
        {
            Environment.SetEnvironmentVariable("SQLAZURECONNSTR_MglabProbe", null);
        }
    }

    [Fact]
    public void SqlServer_provider_uses_sql_server_with_retries()
    {
        using var sp = Build(new() { ["Database:Provider"] = "SqlServer", ["ConnectionStrings:Requests"] = AzureSql });
        using var scope = sp.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<RequestsDbContext>();

        Assert.True(db.Database.IsSqlServer());
        Assert.IsType<SqlServerRetryingExecutionStrategy>(db.Database.CreateExecutionStrategy());
        Assert.Equal(typeof(RequestsDbContext), db.GetType());   // -> Migrations/SqlServer
    }

    [Fact]
    public void Sqlite_provider_resolves_the_sqlite_context_for_the_same_service()
    {
        using var sp = Build(new() { ["Database:Provider"] = "Sqlite", ["ConnectionStrings:Requests"] = "Data Source=:memory:" });
        using var scope = sp.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<RequestsDbContext>();

        Assert.True(db.Database.IsSqlite());
        Assert.IsType<SqliteRequestsDbContext>(db);               // -> Migrations/Sqlite
        Assert.Same(db, scope.ServiceProvider.GetRequiredService<SqliteRequestsDbContext>());
    }

    [Fact]
    public void Missing_connection_string_fails_at_startup_with_a_clear_message()
    {
        var ex = Assert.Throws<InvalidOperationException>(() => Build(new() { ["Database:Provider"] = "SqlServer" }));
        Assert.Contains("ConnectionStrings:Requests", ex.Message);
    }
}
