#if NET9_0_OR_GREATER
using System.Buffers.Text;
using System.Collections.ObjectModel;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;

namespace ProjectRequests.Features;

/// <summary>.NET 9 LINQ: CountBy, AggregateBy, Index. Same answers as the GroupBy versions, without the groups.</summary>
public static class Net9Linq
{
    public static Dictionary<string, int> CountPerDepartment(IEnumerable<RequestRecord> requests) =>
        requests.CountBy(r => r.Department).ToDictionary(p => p.Key, p => p.Value);

    public static Dictionary<string, decimal> BudgetPerDepartment(IEnumerable<RequestRecord> requests) =>
        requests.AggregateBy(r => r.Department, 0m, (sum, r) => sum + r.Budget).ToDictionary(p => p.Key, p => p.Value);

    public static IEnumerable<string> Numbered(IEnumerable<RequestRecord> requests) =>
        requests.Index().Select(x => $"{x.Index + 1}. {x.Item.Title}");
}

/// <summary>C# 13: params with spans (no array allocated) and params with any collection the compiler can build.</summary>
public static class Net9Params
{
    public static bool AnyOf(RequestRecord request, params ReadOnlySpan<Priority> priorities)
    {
        foreach (var p in priorities)
            if (request.Priority == p) return true;
        return false;
    }

    public static bool AnyOfArray(RequestRecord request, params Priority[] priorities)
    {
        foreach (var p in priorities)
            if (request.Priority == p) return true;
        return false;
    }

    public static string JoinTitles(params IEnumerable<RequestRecord> requests) =>
        string.Join(", ", requests.Select(r => r.Title));
}

/// <summary>.NET 9 System.Threading.Lock and the C# 13 lock statement.</summary>
public sealed class RequestNumbers
{
    private readonly Lock _gate = new();
    private int _next;

    public int Next()
    {
        lock (_gate)                 // the compiler uses Lock.EnterScope() here, not Monitor
        {
            return ++_next;
        }
    }

    public int NextWithScope()
    {
        using (_gate.EnterScope())   // the same thing, spelled out
        {
            return ++_next;
        }
    }

    /// <summary>Same lock, statement target typed as Lock: true. Typed as object, the compiler falls back to Monitor: false.</summary>
    public static bool HeldInsideLockStatement(Lock gate) { lock (gate) { return gate.IsHeldByCurrentThread; } }
    public static bool HeldInsideLockStatementAsObject(object gate) { lock (gate) { return ((Lock)gate).IsHeldByCurrentThread; } }
}

/// <summary>.NET 9 Guid.CreateVersion7: time-ordered identifiers.</summary>
public static class RequestIds
{
    public static Guid At(DateTimeOffset when) => Guid.CreateVersion7(when);
    public static Guid Now(TimeProvider clock) => Guid.CreateVersion7(clock.GetUtcNow());
}

/// <summary>.NET 9 Base64Url: paging cursors that are safe in a URL without escaping.</summary>
public static class PageCursor
{
    public static string Encode(int lastId, DateTime createdAtUtc) =>
        Base64Url.EncodeToString(Encoding.UTF8.GetBytes($"{lastId}|{createdAtUtc:O}"));

    public static (int LastId, DateTime CreatedAtUtc) Decode(string cursor)
    {
        var parts = Encoding.UTF8.GetString(Base64Url.DecodeFromChars(cursor)).Split('|');
        return (int.Parse(parts[0], System.Globalization.CultureInfo.InvariantCulture),
                DateTime.Parse(parts[1], System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.RoundtripKind));
    }
}

/// <summary>.NET 9 Task.WhenEach: handle results in the order they finish.</summary>
public static class Notifier
{
    public static async Task<List<string>> InCompletionOrderAsync(IEnumerable<Task<string>> sends)
    {
        List<string> finished = [];
        await foreach (var task in Task.WhenEach(sends))
            finished.Add(await task);
        return finished;
    }
}

/// <summary>.NET 9 collections: OrderedDictionary&lt;TKey,TValue&gt; and ReadOnlySet&lt;T&gt;.</summary>
public sealed class Workflow
{
    private readonly OrderedDictionary<string, int> _stages = new() { ["Submitted"] = 0, ["Approved"] = 2 };
    private readonly HashSet<string> _departments = ["FIN", "IT"];
    private ReadOnlySet<string>? _departmentsView;

    public Workflow() => _stages.Insert(1, "Review", 1);         // keeps insertion order and gives O(1) key lookup

    public IReadOnlyList<string> StageNames => [.. _stages.Keys];
    public int IndexOf(string stage) => _stages.IndexOf(stage);
    public bool RemoveFirst() { _stages.RemoveAt(0); return true; }

    public ReadOnlySet<string> Departments => _departmentsView ??= new ReadOnlySet<string>(_departments);
    public void AddDepartment(string code) => _departments.Add(code);
}

/// <summary>.NET 9: JsonSerializerOptions.Web, SearchValues&lt;string&gt;, TimeSpan integer overloads.</summary>
public static class Net9Misc
{
    public static string ToWebJson<T>(T value) => JsonSerializer.Serialize(value, JsonSerializerOptions.Web);
    public static T? FromWebJson<T>(string json) => JsonSerializer.Deserialize<T>(json, JsonSerializerOptions.Web);

    private static readonly System.Buffers.SearchValues<string> Banned =
        System.Buffers.SearchValues.Create(["drop table", "<script", "javascript:"], StringComparison.OrdinalIgnoreCase);

    public static bool LooksMalicious(string text) => text.AsSpan().IndexOfAny(Banned) >= 0;

    public static TimeSpan Exact(int seconds, int milliseconds) => TimeSpan.FromSeconds(seconds, milliseconds);
}
#endif
