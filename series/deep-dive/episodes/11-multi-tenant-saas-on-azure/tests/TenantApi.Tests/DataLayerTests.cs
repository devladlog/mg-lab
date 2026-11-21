using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using TenantApi.Data;
using TenantApi.Tenancy;

namespace TenantApi.Tests;

public sealed class DataLayerTests : IDisposable
{
    readonly SqliteConnection _conn = new("DataSource=:memory:");
    static readonly Guid A = Guid.Parse(Ids.Northwind), B = Guid.Parse(Ids.AdventureWorks);

    public DataLayerTests()
    {
        _conn.Open();
        using var db = For(A);
        db.Database.EnsureCreated();
    }

    AppDbContext For(Guid? tenant)
    {
        var t = new TenantContext();
        if (tenant is { } id) t.Use(id);
        return new AppDbContext(new DbContextOptionsBuilder<AppDbContext>().UseSqlite(_conn).Options, t);
    }

    static PurchaseRequest Row(string title, Guid? tenant = null) =>
        new() { Id = Guid.NewGuid(), Title = title, Amount = 10, CreatedBy = Ids.Alex, CreatedUtc = DateTime.UtcNow, TenantId = tenant ?? Guid.Empty };

    [Fact]
    public void New_rows_are_stamped_with_the_context_tenant()
    {
        using (var db = For(A)) { db.PurchaseRequests.Add(Row("a")); db.SaveChanges(); }
        using var read = For(A);
        Assert.Equal(A, read.PurchaseRequests.Single().TenantId);
    }

    [Fact]
    public void Reads_without_a_tenant_return_nothing_the_filter_fails_closed()
    {
        using (var db = For(A)) { db.PurchaseRequests.Add(Row("a")); db.SaveChanges(); }
        using var nobody = For(null);
        Assert.Empty(nobody.PurchaseRequests.ToList());
    }

    [Fact]
    public void Writes_without_a_tenant_are_refused()
    {
        using var nobody = For(null);
        nobody.PurchaseRequests.Add(Row("x"));
        Assert.Throws<CrossTenantWriteException>(() => nobody.SaveChanges());
    }

    [Fact]
    public void A_row_that_names_another_tenant_is_refused()
    {
        using var db = For(A);
        db.PurchaseRequests.Add(Row("x", B));
        Assert.Throws<CrossTenantWriteException>(() => db.SaveChanges());
    }

    [Fact]
    public async Task The_async_path_enforces_the_same_rule()
    {
        await using var db = For(A);
        db.PurchaseRequests.Add(Row("x", B));
        await Assert.ThrowsAsync<CrossTenantWriteException>(() => db.SaveChangesAsync());
    }

    [Fact]
    public void TenantId_cannot_be_changed_after_the_fact()
    {
        using (var db = For(A)) { db.PurchaseRequests.Add(Row("a")); db.SaveChanges(); }
        using var edit = For(A);
        var row = edit.PurchaseRequests.Single();
        // Because TenantId is part of the primary key, EF Core itself refuses to modify it. The context's own check
        // (CrossTenantWriteException on a modified TenantId) is a second lock for the day the key changes.
        Assert.Throws<InvalidOperationException>(() => edit.Entry(row).Property(r => r.TenantId).CurrentValue = B);
    }

    [Fact]
    public void The_filter_is_application_code_IgnoreQueryFilters_sees_everything_which_is_why_the_database_repeats_the_rule()
    {
        using (var db = For(A)) { db.PurchaseRequests.Add(Row("a")); db.SaveChanges(); }
        using (var db = For(B)) { db.PurchaseRequests.Add(Row("b")); db.SaveChanges(); }
        using var read = For(A);
        Assert.Single(read.PurchaseRequests.ToList());
        Assert.Equal(2, read.PurchaseRequests.IgnoreQueryFilters().Count());
        Assert.Equal(2, read.Database.SqlQueryRaw<int>("SELECT COUNT(*) AS Value FROM PurchaseRequests").AsEnumerable().Single());   // raw SQL skips the filter too
    }

    [Fact]
    public void The_same_id_may_exist_in_two_tenants()
    {
        var id = Guid.NewGuid();
        using (var db = For(A)) { db.PurchaseRequests.Add(new PurchaseRequest { Id = id, Title = "a", Amount = 1, CreatedBy = "x", CreatedUtc = DateTime.UtcNow }); db.SaveChanges(); }
        using (var db = For(B)) { db.PurchaseRequests.Add(new PurchaseRequest { Id = id, Title = "b", Amount = 1, CreatedBy = "x", CreatedUtc = DateTime.UtcNow }); db.SaveChanges(); }
        using var read = For(B);
        Assert.Equal("b", read.PurchaseRequests.Single(p => p.Id == id).Title);
    }

    public void Dispose() => _conn.Dispose();
}

/// <summary>
/// The interceptor against a real (SQLite) connection that EF opens itself. SQLite has no SESSION_CONTEXT, so the
/// command text is swapped for one that stores the parameter in a temp table: this proves WHEN the command runs and
/// WHICH tenant it carries. The real T-SQL is parsed in <see cref="SqlScriptTests"/> and runs in the lab.
/// </summary>
public sealed class SessionContextInterceptorTests : IDisposable
{
    readonly string _file = Path.Combine(Path.GetTempPath(), $"tenantapi-{Guid.NewGuid():N}.db");

    AppDbContext Context(Guid? tenant, string sql)
    {
        var t = new TenantContext();
        if (tenant is { } id) t.Use(id);
        var options = new DbContextOptionsBuilder<AppDbContext>()
            .UseSqlite($"Data Source={_file};Pooling=False")
            .AddInterceptors(new TenantSessionContextInterceptor(sql))
            .Options;
        return new AppDbContext(options, t);
    }

    const string Store = "CREATE TEMP TABLE IF NOT EXISTS session_ctx (TenantId TEXT); DELETE FROM session_ctx; INSERT INTO session_ctx VALUES (upper(@tenant));";

    [Fact]
    public void Every_opened_connection_carries_the_tenant_of_the_context_that_opened_it()
    {
        using (var setup = Context(Guid.Parse(Ids.Northwind), Store)) setup.Database.EnsureCreated();
        foreach (var tenant in new[] { Ids.Northwind, Ids.AdventureWorks })
        {
            using var db = Context(Guid.Parse(tenant), Store);
            var seen = db.Database.SqlQueryRaw<string>("SELECT TenantId AS Value FROM temp.session_ctx").AsEnumerable().Single();
            Assert.Equal(tenant.ToUpperInvariant(), seen);
        }
    }

    [Fact]
    public async Task The_async_open_path_does_the_same()
    {
        await using (var setup = Context(Guid.Parse(Ids.Northwind), Store)) await setup.Database.EnsureCreatedAsync();
        await using var db = Context(Guid.Parse(Ids.AdventureWorks), Store);
        var seen = await db.Database.SqlQueryRaw<string>("SELECT TenantId AS Value FROM temp.session_ctx").ToListAsync();
        Assert.Equal(Ids.AdventureWorks.ToUpperInvariant(), Assert.Single(seen));
    }

    [Fact]
    public void Without_a_tenant_the_command_is_not_run_at_all()
    {
        // This command would fail if it ran: the table does not exist.
        using (var setup = Context(Guid.Parse(Ids.Northwind), "SELECT 1")) setup.Database.EnsureCreated();
        using var db = Context(null, "SELECT * FROM table_that_does_not_exist");
        Assert.Empty(db.PurchaseRequests.ToList());
    }

    public void Dispose() { try { File.Delete(_file); } catch (IOException) { } }
}
