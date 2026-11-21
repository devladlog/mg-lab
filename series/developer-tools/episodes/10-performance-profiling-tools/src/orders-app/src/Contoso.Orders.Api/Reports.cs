using System.Globalization;
using Microsoft.EntityFrameworkCore;

namespace Contoso.Orders.Api;

public sealed record RevenueRow(string Customer, int Orders, decimal Revenue);

public sealed record MonthlyRevenue(string Month, int Orders, decimal Total, IReadOnlyList<RevenueRow> Customers);

/// <summary>"Revenue per customer for one month": the report finance asks for on the first working day of every month.</summary>
public static class Reports
{
    /// <summary>"2026-03" is March 2026. Anything else (2026-3, 2026-13, "") is not a month.</summary>
    public static bool TryParseMonth(string? text, out DateOnly firstDay) =>
        DateOnly.TryParseExact($"{text}-01", "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out firstDay);

    public static async Task<MonthlyRevenue> MonthlyRevenueAsync(OrdersDb db, DateOnly firstDay, CancellationToken ct = default)
    {
        var nextMonth = firstDay.AddMonths(1);
        // The month is a half-open range: first day of the month up to, not including, the first day of the next one.
        // The database filters and groups: one row per customer comes back, not every order of the month.
        var rows = await db.Orders.AsNoTracking()
            .Where(o => o.Created >= firstDay && o.Created < nextMonth)
            .GroupBy(o => o.Customer)
            .Select(g => new RevenueRow(g.Key, g.Count(), g.Sum(o => o.Total)))
            .ToListAsync(ct);

        var customers = rows.OrderByDescending(r => r.Revenue).ToList();
        return new MonthlyRevenue(firstDay.ToString("yyyy-MM", CultureInfo.InvariantCulture), customers.Sum(c => c.Orders),
            customers.Sum(c => c.Revenue), customers);
    }
}

public sealed record CacheStats(int Entries, int Hits, int Misses);

/// <summary>
/// Caches finished reports per month. Two locks: <c>_entries</c> guards the dictionary, <c>_stats</c> the counters.
/// Rule: whoever needs both takes <c>_entries</c> first, then <c>_stats</c>.
/// <c>holdMs</c> stands in for the database call that real code makes while it holds a lock (0 = none).
/// </summary>
public sealed class ReportCache(int holdMs = 0)
{
    private readonly object _entries = new();
    private readonly object _stats = new();
    private readonly Dictionary<string, MonthlyRevenue> _byMonth = [];
    private int _hits;
    private int _misses;

    public bool TryGet(string month, out MonthlyRevenue? report)
    {
        lock (_entries)
        {
            var found = _byMonth.TryGetValue(month, out report);
            lock (_stats)
            {
                if (found) _hits++; else _misses++;
            }
            return found;
        }
    }

    public void Set(MonthlyRevenue report)
    {
        lock (_entries) _byMonth[report.Month] = report;
    }

    /// <summary>Drops every cached report (after a late order was posted to a closed month).</summary>
    public void Invalidate()
    {
        lock (_entries)
        {
            _byMonth.Clear();
            Hold();
            lock (_stats)
            {
                _hits = 0;
                _misses = 0;
            }
        }
    }

    public CacheStats Snapshot()
    {
        lock (_entries)
        {
            Hold();
            lock (_stats)
            {
                return new CacheStats(_byMonth.Count, _hits, _misses);
            }
        }
    }

    private void Hold()
    {
        if (holdMs > 0) Thread.Sleep(holdMs);
    }
}

internal static partial class ReportLog
{
    [LoggerMessage(EventId = 1, Level = LogLevel.Information,
        Message = "Monthly revenue {Month}: {Customers} customers, {Orders} orders, total {Total}")]
    public static partial void MonthlyRevenueComputed(this ILogger logger, string month, int customers, int orders, decimal total);

    [LoggerMessage(EventId = 2, Level = LogLevel.Warning, Message = "Rejected month {Month}: expected yyyy-MM")]
    public static partial void MonthRejected(this ILogger logger, string? month);
}
