using System.Reflection;
using Contoso.Orders.Api.Data;
using Microsoft.Data.SqlClient;
using Microsoft.EntityFrameworkCore;

namespace Contoso.Orders.Tests;

public class DatabaseSetupTests
{
    private static readonly string Root = typeof(DatabaseSetupTests).Assembly
        .GetCustomAttributes<AssemblyMetadataAttribute>().Single(a => a.Key == "EpisodeRoot").Value!;

    [Fact]
    public void Azure_sql_connection_string_uses_entra_id_and_has_no_secret()
    {
        var cs = new SqlConnectionStringBuilder(DatabaseSetup.AzureSqlConnectionString("sql-contoso.database.windows.net", "sqldb-orders"));
        Assert.Equal(SqlAuthenticationMethod.ActiveDirectoryDefault, cs.Authentication);
        Assert.Equal(SqlConnectionEncryptOption.Mandatory, cs.Encrypt);
        Assert.False(cs.TrustServerCertificate);
        Assert.Equal(60, cs.ConnectTimeout); // long enough for a paused serverless database to resume
        Assert.Equal("", cs.Password);
        Assert.Equal("", cs.UserID);
        Assert.Equal("tcp:sql-contoso.database.windows.net,1433", cs.DataSource);
    }

    [Fact]
    public void Sql_server_provider_uses_a_retrying_execution_strategy()
    {
        var b = new DbContextOptionsBuilder<OrdersDbContext>();
        DatabaseSetup.Configure(b, new DatabaseOptions { Provider = "SqlServer", Server = "sql-contoso.database.windows.net", Database = "sqldb-orders" });
        using var db = new OrdersDbContext(b.Options);
        Assert.Equal("SqlServerRetryingExecutionStrategy", db.Database.CreateExecutionStrategy().GetType().Name);
        Assert.True(db.Database.IsSqlServer());
    }

    [Fact]
    public void Missing_server_fails_fast()
    {
        var b = new DbContextOptionsBuilder<OrdersDbContext>();
        Assert.Throws<InvalidOperationException>(() => DatabaseSetup.Configure(b, new DatabaseOptions { Provider = "SqlServer" }));
    }

    [Fact]
    public void Schema_file_matches_the_model()
    {
        // If this fails: dotnet run --project src/Contoso.Orders.Api -- --print-schema > db/schema.sql
        static string Norm(string s) => s.Replace("\r\n", "\n").Trim();
        Assert.Equal(Norm(DatabaseSetup.SqlServerCreateScript()), Norm(File.ReadAllText(Path.Combine(Root, "db", "schema.sql"))));
    }

    [Fact]
    public void Schema_has_the_indexes_the_queries_rely_on()
    {
        var sql = DatabaseSetup.SqlServerCreateScript();
        Assert.Contains("CREATE UNIQUE INDEX [IX_Orders_IdempotencyKey] ON [Orders] ([IdempotencyKey]);", sql);
        Assert.Contains("ON [Orders] ([CustomerId], [CreatedUtc] DESC, [Id] DESC);", sql);
        Assert.Contains("[Id] bigint NOT NULL IDENTITY", sql);
    }
}
