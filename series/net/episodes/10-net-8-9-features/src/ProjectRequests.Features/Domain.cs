using System.Text.Json.Serialization;

namespace ProjectRequests.Features;

// .NET 8: the generic converter, which also works with source generation and Native AOT
[JsonConverter(typeof(JsonStringEnumConverter<Priority>))]
public enum Priority { Standard, High }

public enum RequestStatus { Submitted, Approved, Rejected }

public sealed record RequestRecord(
    int Id, string Title, decimal Budget, string Department, string RequestedBy,
    Priority Priority, RequestStatus Status, DateTime CreatedAtUtc);

/// <summary>Fictional data, same family as the earlier episodes. A collection expression builds the list (C# 12).</summary>
public static class SampleData
{
    private static readonly DateTime Start = new(2026, 1, 5, 9, 0, 0, DateTimeKind.Utc);

    public static IReadOnlyList<RequestRecord> Requests { get; } =
    [
        new(1, "Laptop refresh", 42_000m, "IT", "alex.demo@contoso.example", Priority.Standard, RequestStatus.Approved, Start),
        new(2, "ERP upgrade", 310_000m, "IT", "sam.demo@contoso.example", Priority.High, RequestStatus.Submitted, Start.AddDays(1)),
        new(3, "Audit tooling", 58_000m, "FIN", "jordan.demo@contoso.example", Priority.High, RequestStatus.Submitted, Start.AddDays(2)),
        new(4, "Warehouse sensors", 120_000m, "OPS", "riley.demo@contoso.example", Priority.High, RequestStatus.Rejected, Start.AddDays(3)),
        new(5, "Budget planner licences", 12_500m, "FIN", "taylor.demo@contoso.example", Priority.Standard, RequestStatus.Approved, Start.AddDays(4)),
        new(6, "Meeting room displays", 24_000m, "OPS", "alex.demo@contoso.example", Priority.Standard, RequestStatus.Submitted, Start.AddDays(5)),
        new(7, "Backup storage", 76_000m, "IT", "sam.demo@contoso.example", Priority.High, RequestStatus.Approved, Start.AddDays(6)),
        new(8, "Travel portal", 31_000m, "FIN", "jordan.demo@contoso.example", Priority.Standard, RequestStatus.Submitted, Start.AddDays(7)),
    ];
}
