using System.Diagnostics;
using System.Reflection;
using System.Text.RegularExpressions;
using Contoso.Orders.Api;

namespace Contoso.Orders.Api.Tests;

public class ReportCacheTests
{
    private static MonthlyRevenue Report(string month) => new(month, 0, 0m, []);

    [Fact]
    public void Hits_and_misses_are_counted()
    {
        var cache = new ReportCache();
        Assert.False(cache.TryGet("2026-01", out _));
        cache.Set(Report("2026-01"));
        Assert.True(cache.TryGet("2026-01", out var report));
        Assert.Equal("2026-01", report!.Month);
        Assert.Equal(new CacheStats(1, 1, 1), cache.Snapshot());
    }

    /// <summary>
    /// Two threads that each need both locks. With one lock order for everybody this always finishes; if one method
    /// takes the locks in the other order, the same test hangs (the deadlock patch in bugs/ does that) and the
    /// timeout turns the hang into a failure instead of a stuck test run.
    /// </summary>
    [Fact]
    public async Task Invalidate_and_Snapshot_at_the_same_time_do_not_deadlock()
    {
        var cache = new ReportCache(holdMs: 20);      // wide enough for the race to be certain, not just possible
        var work = Task.WhenAll(
            Task.Factory.StartNew(() => { for (var i = 0; i < 5; i++) cache.Invalidate(); }, TaskCreationOptions.LongRunning),
            Task.Factory.StartNew(() => { for (var i = 0; i < 5; i++) cache.Snapshot(); }, TaskCreationOptions.LongRunning));

        var finished = await Task.WhenAny(work, Task.Delay(TimeSpan.FromSeconds(20)));
        Assert.True(finished == work, "Invalidate and Snapshot did not finish in 20 s: the two locks are taken in different orders");
    }
}

public class DebuggerDisplayTests
{
    [Fact]
    public void Order_shows_its_values_in_the_debugger_without_expanding_the_object()
    {
        var attribute = typeof(Order).GetCustomAttribute<DebuggerDisplayAttribute>();
        Assert.NotNull(attribute);

        // Every {name} in the template must be a member of Order, or the debugger shows "error CS0103" in the Locals window.
        var names = Regex.Matches(attribute.Value, @"\{(\w+)\}").Select(m => m.Groups[1].Value).ToList();
        Assert.Equal(["Id", "Customer", "Total", "Created"], names);
        Assert.All(names, n => Assert.NotNull(typeof(Order).GetProperty(n)));
    }
}
