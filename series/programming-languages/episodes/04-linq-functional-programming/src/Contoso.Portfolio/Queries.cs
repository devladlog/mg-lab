using Microsoft.EntityFrameworkCore;

namespace Contoso.Portfolio;

public sealed record DepartmentRow(string Department, string? Request, decimal? Budget);

/// <summary>Database queries. IQueryable + expression trees: EF Core turns the lambdas into SQL.</summary>
public static class Queries
{
    /// <summary>IQueryable: the Where becomes a SQL WHERE. Only matching rows leave the database.</summary>
    public static IQueryable<ProjectRequest> AtLeast(IQueryable<ProjectRequest> requests, decimal threshold) =>
        requests.Where(r => r.Budget >= threshold);

    /// <summary>
    /// Same body, different parameter type. IEnumerable: the Where is LINQ to Objects, so EF reads the WHOLE table
    /// and filters in memory. Same result, no error, no warning.
    /// </summary>
    public static IEnumerable<ProjectRequest> AtLeast(IEnumerable<ProjectRequest> requests, decimal threshold) =>
        requests.Where(r => r.Budget >= threshold);

    /// <summary>
    /// .NET 10 LeftJoin, translated by EF Core 10 to LEFT JOIN. Query syntax has no left join (yet).
    /// Order on an anonymous type, project to the record last: EF Core 10 could not translate an OrderBy on a
    /// member of a record built with its constructor (we hit that, see README).
    /// </summary>
    public static IQueryable<DepartmentRow> DepartmentsWithRequests(PortfolioDb db) =>
        db.Departments
            .LeftJoin(db.Requests, d => d.Code, r => r.DepartmentCode,
                (d, r) => new { d.Name, Code = r == null ? null : r.Code, Budget = r == null ? (decimal?)null : r.Budget })
            .OrderBy(x => x.Name)
            .ThenBy(x => x.Code)
            .Select(x => new DepartmentRow(x.Name, x.Code, x.Budget));

    /// <summary>What we wrote first: compiles, then throws "could not be translated" when it runs.</summary>
    public static IQueryable<DepartmentRow> DepartmentsWithRequestsUntranslatable(PortfolioDb db) =>
        db.Departments
            .LeftJoin(db.Requests, d => d.Code, r => r.DepartmentCode,
                (d, r) => new DepartmentRow(d.Name, r == null ? null : r.Code, r == null ? null : r.Budget))
            .OrderBy(x => x.Department);

    /// <summary>
    /// Queryable.CountBy exists since .NET 9 and compiles on a DbSet, but EF Core 10 can't translate it:
    /// it throws "could not be translated" when the query runs.
    /// </summary>
    public static IQueryable<KeyValuePair<string, int>> CountByDepartmentUntranslatable(PortfolioDb db) =>
        db.Requests.CountBy(r => r.DepartmentCode);

    /// <summary>The database version: GroupBy + Count, translated to GROUP BY.</summary>
    public static IQueryable<KeyValuePair<string, int>> CountByDepartment(PortfolioDb db) =>
        db.Requests.GroupBy(r => r.DepartmentCode)
            .OrderBy(g => g.Key)
            .Select(g => new KeyValuePair<string, int>(g.Key, g.Count()));

    /// <summary>A C# method inside Where: EF Core can't translate it and throws when the query runs.</summary>
    public static IQueryable<ProjectRequest> StrategicUntranslatable(PortfolioDb db) =>
        db.Requests.Where(r => Policy.IsStrategic(r));

    /// <summary>The fix: filter what SQL can do on the server, switch to LINQ to Objects explicitly for the rest.</summary>
    public static async Task<List<ProjectRequest>> StrategicAsync(PortfolioDb db, CancellationToken ct = default)
    {
        var candidates = await db.Requests
            .Where(r => r.Status == RequestStatus.Submitted || r.Status == RequestStatus.Draft)
            .ToListAsync(ct);
        return [.. candidates.Where(Policy.IsStrategic)];
    }
}
