using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using ProjectRequests.Api.Data;

namespace ProjectRequests.Api.Tests;

/// <summary>
/// EF Core on SQLite in-memory. NUnit creates ONE instance of this class for all its tests, so the
/// connection is opened per test in [SetUp] and closed in [TearDown] - a field initializer would be shared.
/// </summary>
[Category("Unit")]
public sealed class DataTests
{
    private SqliteConnection _connection = null!;

    private static CancellationToken Ct => TestContext.CurrentContext.CancellationToken;

    [SetUp]
    public void OpenDatabase()
    {
        _connection = new SqliteConnection("Data Source=:memory:");
        _connection.Open();
        using var db = NewContext();
        db.Database.Migrate();
    }

    [TearDown]
    public void CloseDatabase() => _connection.Dispose();

    private SqliteRequestsDbContext NewContext() =>
        new(new DbContextOptionsBuilder<SqliteRequestsDbContext>().UseSqlite(_connection).Options);

    [Test]
    public async Task Second_writer_with_a_stale_version_gets_a_concurrency_exception()
    {
        int id;
        await using (var setup = NewContext())
        {
            var request = SqlServerTestDatabase.NewRequest(departmentId: 1, budget: 40_000m);
            setup.Requests.Add(request);
            await setup.SaveChangesAsync(Ct);
            id = request.Id;
        }

        await using var approver = NewContext();
        await using var requester = NewContext();
        var seenByApprover = await approver.Requests.SingleAsync(r => r.Id == id, Ct);
        var seenByRequester = await requester.Requests.SingleAsync(r => r.Id == id, Ct);

        seenByRequester.Budget = 90_000m;
        seenByRequester.Touch();
        await requester.SaveChangesAsync(Ct);                    // first writer wins

        seenByApprover.Status = RequestStatus.Approved;
        seenByApprover.Touch();

        // NUnit 5: ThrowsAsync returns a Task and must be awaited (NUnit.Analyzers flags it if you forget).
        var ex = await Assert.ThrowsAsync<DbUpdateConcurrencyException>(() => approver.SaveChangesAsync(Ct));

        Assert.That(ex.Entries, Has.Count.EqualTo(1));
    }

    [Test]
    public async Task Department_codes_compare_case_sensitively_on_SQLite()
    {
        await using var db = NewContext();

        using (Assert.EnterMultipleScope())
        {
            Assert.That(await db.Departments.SingleOrDefaultAsync(d => d.Code == "fin", Ct), Is.Null);
            Assert.That(await db.Departments.SingleOrDefaultAsync(d => d.Code == "FIN", Ct), Is.Not.Null);
        }
    }
}
