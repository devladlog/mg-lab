using System.Data.Common;
using Contoso.Orders.Api;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;

namespace Contoso.Orders.Api.Tests;

[CollectionDefinition("perf", DisableParallelization = true)]
public sealed class PerfCollection;

/// <summary>
/// Performance guards that do not depend on how fast the build machine is: how many queries, what they ask for, how much
/// memory one report allocates. Wall-clock budgets are flaky on a shared CI runner; counts and bytes are not.
/// The functional tests in ReportsTests stay green when the report loads every order and filters in memory: these do not.
/// </summary>
[Collection("perf")]
public sealed class ReportPerformanceTests : IDisposable
{
    private const int Rows = 20_000;                       // 2026-01-01 .. 2026-10-27, about 66 orders a day
    private const long AllocationBudgetBytes = 1_000_000;  // one report; measured value is far below, see the README

    private readonly string _path = Path.Combine(Path.GetTempPath(), $"orders-perf-{Guid.NewGuid():N}.db");
    private readonly SqlCapture _sql = new();

    public ReportPerformanceTests()
    {
        using var db = NewDb();
        db.Database.EnsureCreated();
        db.Orders.AddRange(OrdersDb.SeedData(Rows));
        db.SaveChanges();
        _sql.Commands.Clear();
    }

    private OrdersDb NewDb() => new(new DbContextOptionsBuilder<OrdersDb>()
        .UseSqlite($"Data Source={_path};Pooling=False").AddInterceptors(_sql).Options);

    [Fact]
    public async Task The_report_is_one_query_and_the_database_does_the_filtering_and_grouping()
    {
        using var db = NewDb();
        await Reports.MonthlyRevenueAsync(db, new DateOnly(2026, 3, 1));

        var sql = Assert.Single(_sql.Commands);
        Assert.Contains("WHERE", sql);
        Assert.Contains("GROUP BY", sql);
    }

    [Fact]
    public async Task One_report_stays_inside_its_allocation_budget()
    {
        using var db = NewDb();
        await Reports.MonthlyRevenueAsync(db, new DateOnly(2026, 3, 1));      // warm-up: JIT, EF model, query cache

        var before = GC.GetTotalAllocatedBytes(precise: true);
        await Reports.MonthlyRevenueAsync(db, new DateOnly(2026, 4, 1));
        var allocated = GC.GetTotalAllocatedBytes(precise: true) - before;

        Assert.True(allocated < AllocationBudgetBytes,
            $"one report allocated {allocated:N0} bytes for {Rows:N0} orders in the table, the budget is {AllocationBudgetBytes:N0}");
    }

    [Fact]
    public async Task The_numbers_are_the_same_as_plain_LINQ_over_the_seed()
    {
        using var db = NewDb();
        var report = await Reports.MonthlyRevenueAsync(db, new DateOnly(2026, 3, 1));

        var expected = OrdersDb.SeedData(Rows).Where(o => o.Created.Month == 3).ToList();
        Assert.Equal(expected.Count, report.Orders);
        Assert.Equal(expected.Sum(o => o.Total), report.Total);
        Assert.Equal(expected.GroupBy(o => o.Customer).Count(), report.Customers.Count);
    }

    public void Dispose()
    {
        foreach (var file in Directory.GetFiles(Path.GetTempPath(), Path.GetFileName(_path) + "*"))
            File.Delete(file);
    }

    private sealed class SqlCapture : DbCommandInterceptor
    {
        public List<string> Commands { get; } = [];

        public override InterceptionResult<DbDataReader> ReaderExecuting(DbCommand command, CommandEventData eventData,
            InterceptionResult<DbDataReader> result)
        {
            Commands.Add(command.CommandText);
            return base.ReaderExecuting(command, eventData, result);
        }

        public override ValueTask<InterceptionResult<DbDataReader>> ReaderExecutingAsync(DbCommand command,
            CommandEventData eventData, InterceptionResult<DbDataReader> result, CancellationToken cancellationToken = default)
        {
            Commands.Add(command.CommandText);
            return base.ReaderExecutingAsync(command, eventData, result, cancellationToken);
        }
    }
}
