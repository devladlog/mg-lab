namespace Contoso.Portfolio;

public sealed record DepartmentTotal(string DepartmentCode, int Count, decimal Total);
public sealed record DepartmentLine(string Name, int Count, decimal Total);
public sealed record RankedRequest(int Rank, string Code, string Title, decimal Budget);

/// <summary>
/// The functional core: static, pure functions from data to data. No I/O, no clock, no mutation of the input.
/// Each one is a small pipeline of LINQ operators.
/// </summary>
public static class Reports
{
    /// <summary>.NET 9 AggregateBy: one pass, one accumulator per key, no intermediate groups.</summary>
    public static IReadOnlyList<DepartmentTotal> TotalsByDepartment(IEnumerable<ProjectRequest> requests) =>
    [
        .. requests
            .AggregateBy(r => r.DepartmentCode, _ => (Count: 0, Total: 0m),
                (acc, r) => (acc.Count + 1, acc.Total + r.Budget))
            .Select(kv => new DepartmentTotal(kv.Key, kv.Value.Count, kv.Value.Total))
            .OrderByDescending(t => t.Total),
    ];

    /// <summary>The same report in query syntax with GroupBy. Pinned equal by a test.</summary>
    public static IReadOnlyList<DepartmentTotal> TotalsByDepartmentQuerySyntax(IEnumerable<ProjectRequest> requests) =>
    [
        .. from r in requests
           group r by r.DepartmentCode into g
           let total = g.Sum(x => x.Budget)
           orderby total descending
           select new DepartmentTotal(g.Key, g.Count(), total),
    ];

    /// <summary>.NET 9 CountBy.</summary>
    public static IReadOnlyDictionary<RequestStatus, int> CountByStatus(IEnumerable<ProjectRequest> requests) =>
        requests.CountBy(r => r.Status).ToDictionary();

    /// <summary>CountBy per department, sorted by key (compared with the SQL version in the tests).</summary>
    public static IReadOnlyList<KeyValuePair<string, int>> CountByDepartmentInMemory(IEnumerable<ProjectRequest> requests) =>
        [.. requests.CountBy(r => r.DepartmentCode).OrderBy(kv => kv.Key, StringComparer.Ordinal)];

    /// <summary>.NET 9 Index(): (position, item) tuples, so the rank needs no counter variable.</summary>
    public static IReadOnlyList<RankedRequest> Top(IEnumerable<ProjectRequest> requests, int count) =>
    [
        .. requests
            .OrderByDescending(r => r.Budget)
            .Take(count)
            .Index()
            .Select(x => new RankedRequest(x.Index + 1, x.Item.Code, x.Item.Title, x.Item.Budget)),
    ];

    /// <summary>.NET 10 LeftJoin: every department, also the ones without requests.</summary>
    public static IReadOnlyList<DepartmentLine> AllDepartments(
        IEnumerable<Department> departments, IEnumerable<ProjectRequest> requests) =>
    [
        .. departments
            .LeftJoin(TotalsByDepartment(requests), d => d.Code, t => t.DepartmentCode,
                (d, t) => new DepartmentLine(d.Name, t?.Count ?? 0, t?.Total ?? 0m))
            .OrderByDescending(l => l.Total)
            .ThenBy(l => l.Name, StringComparer.Ordinal),
    ];

    /// <summary>Higher-order function: the caller passes the rule, we return a new sequence. Nothing is mutated.</summary>
    public static IEnumerable<ProjectRequest> Needing(this IEnumerable<ProjectRequest> requests, Func<ProjectRequest, bool> rule) =>
        requests.Where(r => r.Status is RequestStatus.Submitted).Where(rule);
}
