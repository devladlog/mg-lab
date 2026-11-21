using Microsoft.Data.SqlClient;
using Microsoft.EntityFrameworkCore;
using ProjectRequests.Api.Data;

namespace ProjectRequests.Api.Tests;

/// <summary>
/// Opt-in tests against a real SQL Server (in the lab: CON-SQL01). Set the environment variable to a
/// connection string WITHOUT a database name; every test creates its own database and drops it afterwards.
/// Not set (CI, this container): the tests report "skipped" with the reason, they don't silently pass.
/// Framework-agnostic: linked into both the xUnit and the NUnit project.
/// </summary>
public static class SqlServerTestDatabase
{
    public const string Variable = "REQUESTS_TEST_SQLSERVER";

    public static string? ServerConnectionString => Environment.GetEnvironmentVariable(Variable);

    public static string SkipReason => $"Set {Variable} to a SQL Server connection string to run this test.";

    /// <summary>A context on a brand-new database name; MigrateAsync creates it.</summary>
    public static RequestsDbContext CreateContext(string serverConnectionString, string testName)
    {
        var builder = new SqlConnectionStringBuilder(serverConnectionString)
        {
            InitialCatalog = $"ProjectRequests_{testName}_{Guid.NewGuid():N}",
        };
        return new RequestsDbContext(new DbContextOptionsBuilder<RequestsDbContext>()
            .UseSqlServer(builder.ConnectionString)
            .Options);
    }

    public static ProjectRequest NewRequest(int departmentId, decimal budget)
    {
        var request = new ProjectRequest
        {
            Title = "Laptop refresh", Budget = budget, RequestedBy = "alex.demo@contoso.com",
            Status = RequestStatus.Submitted, CreatedAtUtc = DateTime.UtcNow, DepartmentId = departmentId,
        };
        request.Touch();
        return request;
    }
}
