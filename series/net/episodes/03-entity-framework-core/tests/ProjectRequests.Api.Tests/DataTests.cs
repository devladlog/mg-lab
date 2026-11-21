using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using ProjectRequests.Api.Data;

namespace ProjectRequests.Api.Tests;

/// <summary>
/// EF Core level tests on SQLite in-memory. The connection stays open for the whole test: an in-memory
/// SQLite database lives exactly as long as its connection.
/// </summary>
public sealed class DataTests : IDisposable
{
    private readonly SqliteConnection _connection = new("Data Source=:memory:");

    public DataTests()
    {
        _connection.Open();
        using var db = NewContext();
        db.Database.Migrate();                                   // the real SQLite migrations, not EnsureCreated
    }

    public void Dispose() => _connection.Dispose();

    private SqliteRequestsDbContext NewContext() =>
        new(new DbContextOptionsBuilder<SqliteRequestsDbContext>().UseSqlite(_connection).Options);

    private static RequestsDbContext SqlServerContext() => new SqlServerDesignTimeFactory().CreateDbContext([]);

    private static ProjectRequest NewRequest(int departmentId = 1, decimal budget = 40_000m)
    {
        var r = new ProjectRequest
        {
            Title = "Laptop refresh", Budget = budget, RequestedBy = "alex.demo@contoso.com",
            Status = RequestStatus.Submitted, CreatedAtUtc = DateTime.UtcNow, DepartmentId = departmentId,
        };
        r.Touch();
        return r;
    }

    [Fact]
    public void Migrations_create_the_schema_and_seed_the_departments()
    {
        using var db = NewContext();

        Assert.Equal(["20261121040059_InitialCreate", "20261121040120_AddStatusPriorityIndex"],
            db.Database.GetAppliedMigrations());
        Assert.Equal(["FIN", "IT", "OPS"], db.Departments.OrderBy(d => d.Code).Select(d => d.Code));
    }

    [Fact]
    public void Sqlite_migrations_match_the_model()
    {
        using var db = NewContext();
        Assert.False(db.Database.HasPendingModelChanges());     // "forgot dotnet ef migrations add" fails here
    }

    [Fact]
    public void SqlServer_migrations_match_the_model_without_a_SQL_Server()
    {
        using var db = SqlServerContext();
        Assert.False(db.Database.HasPendingModelChanges());
    }

    [Fact]
    public void Committed_SqlServer_script_is_the_idempotent_script_of_the_current_migrations()
    {
        using var db = SqlServerContext();
        var expected = db.GetService<IMigrator>()
            .GenerateScript(options: MigrationsSqlGenerationOptions.Idempotent);

        var committed = File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "sqlserver-migrations.sql"));

        Assert.Equal(Normalize(expected), Normalize(committed));  // regenerate with dotnet ef migrations script --idempotent
        static string Normalize(string s) => s.Replace("\r\n", "\n").Trim('﻿', '\n', ' ');
    }

    [Fact]
    public void SqlServer_gets_decimal_18_2_for_the_budget()
    {
        using var db = SqlServerContext();
        var budget = db.Model.FindEntityType(typeof(ProjectRequest))!.FindProperty(nameof(ProjectRequest.Budget))!;
        Assert.Equal("decimal(18,2)", budget.GetColumnType());
    }

    [Fact]
    public async Task Concurrency_token_stops_a_lost_update()
    {
        int id;
        await using (var setup = NewContext())
        {
            var r = NewRequest();
            setup.Requests.Add(r);
            await setup.SaveChangesAsync();
            id = r.Id;
        }

        await using var approver = NewContext();
        await using var requester = NewContext();
        var seenByApprover = await approver.Requests.SingleAsync(r => r.Id == id);
        var seenByRequester = await requester.Requests.SingleAsync(r => r.Id == id);

        seenByRequester.Budget = 400_000m;                       // requester raises the budget first
        seenByRequester.Touch();
        await requester.SaveChangesAsync();

        seenByApprover.Status = RequestStatus.Approved;          // approver still looks at 40,000
        seenByApprover.Touch();
        await Assert.ThrowsAsync<DbUpdateConcurrencyException>(() => approver.SaveChangesAsync());

        await using var check = NewContext();
        var row = await check.Requests.SingleAsync(r => r.Id == id);
        Assert.Equal(RequestStatus.Submitted, row.Status);
        Assert.Equal(400_000m, row.Budget);
    }

    [Fact]
    public async Task List_projection_is_one_select_with_a_join_and_tracks_nothing()
    {
        await using var db = NewContext();
        db.Requests.Add(NewRequest());
        await db.SaveChangesAsync();
        db.ChangeTracker.Clear();

        var query = db.Requests.OrderBy(r => r.Id).Select(Requests.RequestEndpoints.ToDto);
        var sql = query.ToQueryString();
        var items = await query.ToListAsync();

        Assert.Contains("INNER JOIN \"Departments\"", sql);
        Assert.DoesNotContain("\"Justification\" IS", sql);
        Assert.Single(items);
        Assert.Equal("FIN", items[0].Department);
        Assert.Empty(db.ChangeTracker.Entries());               // projections aren't tracked
    }

    [Fact]
    public async Task Sqlite_compares_strings_case_sensitively()
    {
        await using var db = NewContext();
        // SQL Server's default collation would find FIN here; SQLite doesn't. The API normalises codes.
        Assert.Null(await db.Departments.SingleOrDefaultAsync(d => d.Code == "fin"));
        Assert.NotNull(await db.Departments.SingleOrDefaultAsync(d => d.Code == "FIN"));
    }

    [Fact]
    public async Task Departments_with_requests_cannot_be_deleted()
    {
        await using var db = NewContext();
        db.Requests.Add(NewRequest(departmentId: 2));
        await db.SaveChangesAsync();
        db.ChangeTracker.Clear();

        db.Departments.Remove(await db.Departments.SingleAsync(d => d.Id == 2));
        await Assert.ThrowsAsync<DbUpdateException>(() => db.SaveChangesAsync());   // FK, DeleteBehavior.Restrict
    }

    [Fact]
    public async Task Decimal_sum_and_comparison_run_in_the_database_on_sqlite()
    {
        await using var db = NewContext();
        db.Requests.AddRange(NewRequest(budget: 10_000.25m), NewRequest(budget: 60_000.50m), NewRequest(budget: 300_000m));
        await db.SaveChangesAsync();

        var big = db.Requests.Where(r => r.Budget >= 50_000m);
        Assert.Equal(360_000.50m, await big.SumAsync(r => r.Budget));
        Assert.Equal(2, await big.CountAsync());
    }
}
