using Microsoft.EntityFrameworkCore;

namespace ProjectRequests.Api.Tests;

/// <summary>Same opt-in SQL Server test as the xUnit project. NUnit skips at run time with Assert.Ignore.</summary>
[Category("SqlServer")]
public sealed class SqlServerTests
{
    private static CancellationToken Ct => TestContext.CurrentContext.CancellationToken;

    [Test]
    public async Task Migrations_apply_and_codes_compare_case_insensitively_on_SQL_Server()
    {
        var server = SqlServerTestDatabase.ServerConnectionString;
        if (string.IsNullOrWhiteSpace(server))
            Assert.Ignore(SqlServerTestDatabase.SkipReason);

        await using var db = SqlServerTestDatabase.CreateContext(server!, "nunit");
        try
        {
            await db.Database.MigrateAsync(Ct);
            db.Requests.Add(SqlServerTestDatabase.NewRequest(departmentId: 1, budget: 75_000m));
            await db.SaveChangesAsync(Ct);

            using (Assert.EnterMultipleScope())
            {
                Assert.That(await db.Departments.CountAsync(Ct), Is.EqualTo(3));
                Assert.That(await db.Departments.SingleOrDefaultAsync(d => d.Code == "fin", Ct), Is.Not.Null);
                Assert.That(await db.Requests.SumAsync(r => r.Budget, Ct), Is.EqualTo(75_000m));
            }
        }
        finally
        {
            await db.Database.EnsureDeletedAsync(Ct);
        }
    }
}
