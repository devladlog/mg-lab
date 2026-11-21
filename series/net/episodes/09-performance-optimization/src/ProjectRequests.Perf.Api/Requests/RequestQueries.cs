using Microsoft.EntityFrameworkCore;
using ProjectRequests.Perf.Api.Data;

namespace ProjectRequests.Perf.Api.Requests;

/// <summary>
/// The same listing written four ways. The endpoints use the first (to be measured) and the last (the fix);
/// the benchmarks run all four against the same data. Everything here returns the same rows.
/// </summary>
public static class RequestQueries
{
    /// <summary>BEFORE: tracked entities, then two extra queries per row. 1 + 2N round trips.</summary>
    public static async Task<List<RequestDto>> NPlusOneAsync(PerfDbContext db, string? departmentCode, int take, CancellationToken ct = default)
    {
        var query = db.Requests.AsQueryable();
        if (departmentCode is not null)
            query = query.Where(r => r.Department.Code == departmentCode);

        var rows = await query.OrderBy(r => r.Id).Take(take).ToListAsync(ct);   // tracking query: every row is snapshotted

        var result = new List<RequestDto>(rows.Count);
        foreach (var r in rows)
        {
            // The classic N+1: a query inside the loop for data a JOIN would have brought along.
            var requester = await db.Requesters.Where(p => p.Id == r.RequesterId).FirstAsync(ct);
            var department = await db.Departments.Where(d => d.Id == r.DepartmentId).FirstAsync(ct);
            result.Add(new RequestDto(r.Id, r.Title, r.Budget, department.Code, requester.Name,
                r.Priority, r.Status, r.CreatedAtUtc));
        }
        return result;
    }

    /// <summary>Better: one query with Include, but still whole tracked entities (3 entity types per row).</summary>
    public static async Task<List<RequestDto>> IncludeTrackedAsync(PerfDbContext db, string? departmentCode, int take, CancellationToken ct = default)
    {
        var rows = await Filtered(db.Requests.Include(r => r.Department).Include(r => r.Requester), departmentCode)
            .OrderBy(r => r.Id).Take(take).ToListAsync(ct);
        return rows.Select(r => new RequestDto(r.Id, r.Title, r.Budget, r.Department.Code, r.Requester.Name,
            r.Priority, r.Status, r.CreatedAtUtc)).ToList();
    }

    /// <summary>Same query, read-only: no change tracking, no snapshots (Learn: no-tracking queries).</summary>
    public static async Task<List<RequestDto>> IncludeNoTrackingAsync(PerfDbContext db, string? departmentCode, int take, CancellationToken ct = default)
    {
        var rows = await Filtered(db.Requests.AsNoTracking().Include(r => r.Department).Include(r => r.Requester), departmentCode)
            .OrderBy(r => r.Id).Take(take).ToListAsync(ct);
        return rows.Select(r => new RequestDto(r.Id, r.Title, r.Budget, r.Department.Code, r.Requester.Name,
            r.Priority, r.Status, r.CreatedAtUtc)).ToList();
    }

    /// <summary>AFTER: project in the query. One SELECT with the JOINs, only the needed columns, nothing tracked.</summary>
    public static Task<List<RequestDto>> ProjectedAsync(PerfDbContext db, string? departmentCode, int skip, int take, CancellationToken ct = default) =>
        Filtered(db.Requests.AsNoTracking(), departmentCode)
            .OrderBy(r => r.Id).Skip(skip).Take(take)
            .Select(r => new RequestDto(r.Id, r.Title, r.Budget, r.Department.Code, r.Requester.Name,
                r.Priority, r.Status, r.CreatedAtUtc))
            .ToListAsync(ct);

    public static Task<int> CountAsync(PerfDbContext db, string? departmentCode, CancellationToken ct = default) =>
        Filtered(db.Requests.AsNoTracking(), departmentCode).CountAsync(ct);

    /// <summary>Totals: let the database aggregate (compare SumLoadAllAsync in the benchmarks).</summary>
    public static async Task<decimal> SumInDatabaseAsync(PerfDbContext db, CancellationToken ct = default) =>
        await db.Requests.SumAsync(r => r.Budget, ct);

    /// <summary>Anti-pattern kept for the benchmark: load every entity, add up in memory.</summary>
    public static async Task<decimal> SumLoadAllAsync(PerfDbContext db, CancellationToken ct = default) =>
        (await db.Requests.ToListAsync(ct)).Sum(r => r.Budget);

    private static IQueryable<ProjectRequest> Filtered(IQueryable<ProjectRequest> query, string? departmentCode) =>
        departmentCode is null ? query : query.Where(r => r.Department.Code == departmentCode);
}
