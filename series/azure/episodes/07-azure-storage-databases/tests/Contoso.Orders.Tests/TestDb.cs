using Contoso.Orders.Api.Data;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;

namespace Contoso.Orders.Tests;

/// <summary>
/// SQLite in memory, one open connection per test. SQLite is NOT Azure SQL: it checks the EF model,
/// the unique index, the concurrency token and the paging query shape, not T-SQL behaviour.
/// </summary>
public sealed class TestDb : IDisposable
{
    private readonly SqliteConnection _connection = new("Data Source=:memory:");

    public TestDb()
    {
        _connection.Open();
        using var db = NewContext();
        db.Database.EnsureCreated();
    }

    public OrdersDbContext NewContext() =>
        new(new DbContextOptionsBuilder<OrdersDbContext>().UseSqlite(_connection).Options);

    public void Dispose() => _connection.Dispose();
}
