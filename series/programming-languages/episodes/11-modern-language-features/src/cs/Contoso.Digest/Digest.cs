using System.Globalization;
using System.Text.Json;

namespace Contoso.Digest;

public enum Route { TeamLead, Finance, Board }

public sealed record RawRequest(string Code, string Title, string Department, decimal Budget, string RequestedBy);

public sealed record Request(string Code, string Title, string Department, long Cents)
{
    public Route Route => DigestBuilder.RouteFor(Cents);
}

public sealed record Rejection(string Code, string Reason);

public sealed record DepartmentTotal(string Department, int Count, long Cents);

public sealed record DigestResult(
    IReadOnlyList<Request> Accepted,
    IReadOnlyList<Rejection> Rejected,
    long TotalCents,
    int HighPriority,
    IReadOnlyDictionary<Route, int> Routes,
    IReadOnlyList<DepartmentTotal> Departments,
    IReadOnlyList<Request> Largest,
    IReadOnlyList<string[]> Batches);

public static class DigestBuilder
{
    public const long HighPriorityCents = 5_000_000;   // 50,000.00 EUR
    public const long BoardCents = 25_000_000;         // 250,000.00 EUR
    public const int BatchSize = 4;

    // .NET 9/10 System.Text.Json: honour `string` vs `string?` and required constructor
    // parameters, and refuse duplicate properties. Strict at the boundary, no extra library.
    private static readonly JsonSerializerOptions Strict = new(JsonSerializerOptions.Web)
    {
        RespectNullableAnnotations = true,
        RespectRequiredConstructorParameters = true,
        AllowDuplicateProperties = false,
    };

    public static IReadOnlyList<RawRequest> Parse(string json) =>
        JsonSerializer.Deserialize<List<RawRequest>>(json, Strict)
        ?? throw new JsonException("expected a JSON array of requests");

    public static Route RouteFor(long cents) => cents switch
    {
        >= BoardCents => Route.Board,
        >= HighPriorityCents => Route.Finance,
        _ => Route.TeamLead,
    };

    // decimal keeps 49999.99 exact; Math.Round is only a guard for budgets with extra decimals.
    public static long ToCents(decimal budget) => (long)Math.Round(budget * 100m, MidpointRounding.ToEven);

    public static DigestResult Build(IEnumerable<RawRequest> raws)
    {
        List<Request> accepted = [];
        List<Rejection> rejected = [];
        foreach (var raw in raws)
        {
            if (raw.Budget <= 0)
            {
                rejected.Add(new(raw.Code, "budget must be greater than zero"));
            }
            else
            {
                accepted.Add(new(raw.Code, raw.Title, raw.Department.Trim().ToUpperInvariant(), ToCents(raw.Budget)));
            }
        }

        // CountBy and AggregateBy (.NET 9): grouping without a GroupBy allocation per key.
        var counted = accepted.CountBy(r => r.Route).ToDictionary();
        Dictionary<Route, int> routes = Enum.GetValues<Route>().ToDictionary(route => route, route => counted.GetValueOrDefault(route));

        var departments = accepted
            .AggregateBy(r => r.Department, (Count: 0, Cents: 0L), (total, r) => (total.Count + 1, total.Cents + r.Cents))
            .OrderByDescending(kv => kv.Value.Cents)
            .ThenBy(kv => kv.Key, StringComparer.Ordinal)
            .Select(kv => new DepartmentTotal(kv.Key, kv.Value.Count, kv.Value.Cents))
            .ToList();

        return new DigestResult(
            accepted,
            rejected,
            accepted.Sum(r => r.Cents),
            accepted.Count(r => r.Cents >= HighPriorityCents),
            routes,
            departments,
            [.. accepted.OrderByDescending(r => r.Cents).ThenBy(r => r.Code, StringComparer.Ordinal).Take(3)],
            [.. accepted.Select(r => r.Code).Chunk(BatchSize)]);
    }

    public static string Money(long cents) =>
        (cents / 100m).ToString("N2", CultureInfo.InvariantCulture);

    public static string Render(DigestResult digest)
    {
        List<string> lines =
        [
            "Contoso request digest",
            $"accepted {digest.Accepted.Count}, rejected {digest.Rejected.Count}, total {Money(digest.TotalCents)} EUR, high priority {digest.HighPriority}",
            "rejected:",
            .. digest.Rejected.Select(r => $"  {r.Code}  {r.Reason}"),
            "by route:",
            .. digest.Routes.Select(kv => $"  {kv.Key,-9}{kv.Value,2}"),
            "by department:",
            .. digest.Departments.Select(d => $"  {d.Department,-6}{d.Count,2}  {Money(d.Cents),13} EUR"),
            "largest three:",
            .. digest.Largest.Select((r, i) => $"  {i + 1}. {r.Code}  {r.Title}  {Money(r.Cents)} EUR"),
            $"review batches of {BatchSize}:",
            .. digest.Batches.Select((codes, i) => $"  {i + 1}: {string.Join(", ", codes)}"),
        ];
        return string.Join('\n', lines) + "\n";
    }
}
