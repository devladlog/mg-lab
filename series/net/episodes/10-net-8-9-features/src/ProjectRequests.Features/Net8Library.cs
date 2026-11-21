using System.Buffers;
using System.Collections.Frozen;
using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace ProjectRequests.Features;

public sealed record Department(string Code, string Name);

/// <summary>.NET 8: FrozenDictionary. Built once, read many times; no changes allowed afterwards.</summary>
public static class Departments
{
    public static FrozenDictionary<string, Department> ByCode { get; } =
        new Department[] { new("FIN", "Finance"), new("IT", "Information Technology"), new("OPS", "Operations") }
            .ToFrozenDictionary(d => d.Code, StringComparer.OrdinalIgnoreCase);
}

/// <summary>.NET 8 System.Text.Json: snake_case naming and populating read-only properties.</summary>
public sealed class FeedItem
{
    public int RequestId { get; set; }
    public string Title { get; set; } = "";
    public Priority Priority { get; set; }
    public List<string> Tags { get; } = ["imported"];     // no setter
}

public static class Feed
{
    public static readonly JsonSerializerOptions SnakeCase = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    public static readonly JsonSerializerOptions SnakeCasePopulate = new(SnakeCase)
    {
        PreferredObjectCreationHandling = JsonObjectCreationHandling.Populate,
    };
}

/// <summary>.NET 8 small things: SearchValues, CompositeFormat, Random.GetItems / Shuffle.</summary>
public static class SmallThings
{
    private static readonly SearchValues<char> ForbiddenInTitles = SearchValues.Create("<>&\"");
    private static readonly CompositeFormat DecisionMessage = CompositeFormat.Parse("Request {0} ({1:N2}) was {2}");

    public static bool IsCleanTitle(ReadOnlySpan<char> title) => title.IndexOfAny(ForbiddenInTitles) < 0;

    public static string Describe(RequestRecord r) =>
        string.Format(CultureInfo.InvariantCulture, DecisionMessage, r.Id, r.Budget, r.Status);

    public static RequestRecord[] Sample(RequestRecord[] pool, int count, Random random) => random.GetItems(pool, count);

    public static void ShuffleInPlace(RequestRecord[] items, Random random) => random.Shuffle(items);
}

/// <summary>The "before": what CountBy / AggregateBy replace in .NET 9. Available on every target, used to compare answers.</summary>
public static class LinqBefore
{
    public static Dictionary<string, int> CountPerDepartment(IEnumerable<RequestRecord> requests) =>
        requests.GroupBy(r => r.Department).ToDictionary(g => g.Key, g => g.Count());

    public static Dictionary<string, decimal> BudgetPerDepartment(IEnumerable<RequestRecord> requests) =>
        requests.GroupBy(r => r.Department).ToDictionary(g => g.Key, g => g.Sum(r => r.Budget));
}
