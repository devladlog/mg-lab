using Microsoft.EntityFrameworkCore;

namespace ProjectRequests.Api.Tests;

/// <summary>
/// The same migrations on a real SQL Server. Skipped (not passed) unless REQUESTS_TEST_SQLSERVER is set:
/// xUnit v3 can skip at run time with Assert.SkipWhen / Assert.SkipUnless.
/// </summary>
[Trait("Category", "SqlServer")]
public sealed class SqlServerTests
{
    [Fact]
    public void Each_run_gets_its_own_database_and_keeps_the_server_settings()     // no server needed
    {
        const string server = "Server=10.20.0.30;User ID=requests_tests;TrustServerCertificate=True";

        using var first = SqlServerTestDatabase.CreateContext(server, "xunit");
        using var second = SqlServerTestDatabase.CreateContext(server, "xunit");

        var a = new Microsoft.Data.SqlClient.SqlConnectionStringBuilder(first.Database.GetConnectionString());
        var b = new Microsoft.Data.SqlClient.SqlConnectionStringBuilder(second.Database.GetConnectionString());
        Assert.StartsWith("ProjectRequests_xunit_", a.InitialCatalog);
        Assert.NotEqual(a.InitialCatalog, b.InitialCatalog);
        Assert.Equal("10.20.0.30", a.DataSource);
        Assert.True(a.TrustServerCertificate);
    }

    [Fact]
    public async Task Migrations_apply_and_codes_compare_case_insensitively_on_SQL_Server()
    {
        var server = SqlServerTestDatabase.ServerConnectionString;
        Assert.SkipWhen(string.IsNullOrWhiteSpace(server), SqlServerTestDatabase.SkipReason);

        await using var db = SqlServerTestDatabase.CreateContext(server!, "xunit");
        try
        {
            await db.Database.MigrateAsync(Ct);                              // creates the database, applies both migrations
            db.Requests.Add(SqlServerTestDatabase.NewRequest(departmentId: 1, budget: 75_000m));
            await db.SaveChangesAsync(Ct);

            Assert.Equal(3, await db.Departments.CountAsync(Ct));            // HasData seed, same as SQLite
            Assert.NotNull(await db.Departments.SingleOrDefaultAsync(d => d.Code == "fin", Ct));   // SQLite: null
            Assert.Equal(75_000m, await db.Requests.SumAsync(r => r.Budget, Ct));
        }
        finally
        {
            await db.Database.EnsureDeletedAsync(Ct);
        }
    }
}
