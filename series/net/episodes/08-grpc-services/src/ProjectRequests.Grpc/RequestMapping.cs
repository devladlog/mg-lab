using Google.Protobuf.WellKnownTypes;
using ProjectRequests.Contracts;

namespace ProjectRequests.Grpc;

/// <summary>Between the shared DTOs (REST, SignalR, Blazor) and the protobuf messages.</summary>
public static class RequestMapping
{
    public static RequestReply ToReply(this RequestDto r) => new()
    {
        Id = r.Id,
        Title = r.Title,
        Budget = r.Budget,                                       // implicit decimal -> DecimalValue
        Department = r.Department,
        RequestedBy = r.RequestedBy,
        Justification = r.Justification,                         // StringValue wrapper: null allowed
        Priority = r.Priority switch
        {
            Contracts.Priority.High => Priority.High,
            _ => Priority.Standard,
        },
        Status = r.Status switch
        {
            Contracts.RequestStatus.Approved => RequestStatus.Approved,
            Contracts.RequestStatus.Rejected => RequestStatus.Rejected,
            _ => RequestStatus.Submitted,
        },
        CreatedAt = Timestamp.FromDateTime(r.CreatedAtUtc),       // throws unless DateTimeKind.Utc
        DecidedBy = r.DecidedBy,
        DecidedAt = r.DecidedAtUtc is { } decided ? Timestamp.FromDateTime(decided) : null,
        Version = r.Version.ToString(),
    };

    /// <summary>To the same input model the REST API validates, so both front doors share every rule.</summary>
    public static CreateProjectRequest ToCreateRequest(this NewRequestMessage m) => new()
    {
        Title = m.Title,
        Budget = m.Budget ?? 0m,                                 // a missing message field reads as null
        RequestedBy = m.RequestedBy,
        DepartmentCode = m.DepartmentCode,
        Justification = m.Justification,
    };
}
