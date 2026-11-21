using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Caching.Hybrid;
using ProjectRequests.Perf.Api.Data;
using ProjectRequests.Perf.Api.Requests;
using ProjectRequests.Perf.Api.Telemetry;

namespace ProjectRequests.Perf.Api.Caching;

/// <summary>
/// Data-level cache. HybridCache gives us two things IMemoryCache doesn't: stampede protection (one caller
/// runs the factory, the others wait for it) and tags, so a write can invalidate every entry about requests.
/// </summary>
public sealed class SummaryService(HybridCache cache, PerfDbContext db, RequestMetrics metrics)
{
    public const string Tag = "requests";
    private static readonly string[] Tags = [Tag];

    public ValueTask<SummaryDto> GetAsync(CancellationToken ct = default) =>
        cache.GetOrCreateAsync("summary:all", async token =>
            {
                metrics.SummaryComputed();                       // counts real computations = cache misses
                return await ComputeAsync(token);
            },
            new HybridCacheEntryOptions { Expiration = TimeSpan.FromMinutes(1), LocalCacheExpiration = TimeSpan.FromMinutes(1) },
            Tags, ct);

    public ValueTask InvalidateAsync(CancellationToken ct = default) => cache.RemoveByTagAsync(Tag, ct);

    private async Task<SummaryDto> ComputeAsync(CancellationToken ct)
    {
        var departments = await db.Requests.AsNoTracking()
            .GroupBy(r => r.Department.Code)
            .OrderBy(g => g.Key)                               // order the groups, then project (see README gotcha)
            .Select(g => new DepartmentSummary(g.Key, g.Count(), g.Sum(r => r.Budget)))
            .ToListAsync(ct);
        return new SummaryDto(departments, departments.Sum(d => d.Count), departments.Sum(d => d.Budget), DateTime.UtcNow);
    }
}
