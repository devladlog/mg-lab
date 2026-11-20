using System.Globalization;
using System.Text.Json;
using Microsoft.Kiota.Abstractions.Serialization;

namespace MGLab.GraphFunction;

public sealed record ProjectRequest(
    string Title, string? Requester, string? Department, decimal? Budget, string? Status, DateOnly? DueDate)
{
    /// <summary>Maps a SharePoint list item's fields (as returned by Graph) to a typed record.</summary>
    public static ProjectRequest FromFields(IDictionary<string, object?> f) => new(
        Title: Text(f, "Title") ?? "(untitled)",
        Requester: Text(f, "Requester"),
        Department: Text(f, "Department"),
        Budget: Number(f, "Budget"),
        Status: Text(f, "RequestStatus"),
        DueDate: Date(f, "DueDate"));

    private static object? Raw(IDictionary<string, object?> f, string key) =>
        f.TryGetValue(key, out var v) ? v switch
        {
            JsonElement j => Unwrap(j),
            UntypedNode n => Unwrap(n),   // Graph SDK v5+ returns Kiota untyped nodes
            _ => v
        } : null;

    private static object? Unwrap(UntypedNode n) => n switch
    {
        UntypedString s => s.GetValue(),
        UntypedDouble d => (decimal)d.GetValue(),
        UntypedDecimal m => m.GetValue(),
        UntypedFloat fl => (decimal)fl.GetValue(),
        UntypedInteger i => (decimal)i.GetValue(),
        UntypedLong l => (decimal)l.GetValue(),
        UntypedBoolean b => b.GetValue().ToString(),
        UntypedNull => null,
        _ => null
    };

    private static object? Unwrap(JsonElement j) => j.ValueKind switch
    {
        JsonValueKind.String => j.GetString(),
        JsonValueKind.Number => j.GetDecimal(),
        JsonValueKind.Null or JsonValueKind.Undefined => null,
        _ => j.ToString()
    };

    private static string? Text(IDictionary<string, object?> f, string key) => Raw(f, key)?.ToString();

    private static decimal? Number(IDictionary<string, object?> f, string key) => Raw(f, key) switch
    {
        null => null,
        decimal d => d,
        IConvertible c => c.ToDecimal(CultureInfo.InvariantCulture),
        _ => null
    };

    private static DateOnly? Date(IDictionary<string, object?> f, string key) => Raw(f, key) switch
    {
        DateTime dt => DateOnly.FromDateTime(dt),
        DateTimeOffset dto => DateOnly.FromDateTime(dto.UtcDateTime),
        string s when DateTimeOffset.TryParse(s, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var p)
            => DateOnly.FromDateTime(p.UtcDateTime),
        _ => null
    };
}
