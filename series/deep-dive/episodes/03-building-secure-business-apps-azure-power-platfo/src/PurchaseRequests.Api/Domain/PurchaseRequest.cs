namespace PurchaseRequests.Api.Domain;

public enum RequestStatus { Pending, Approved, Rejected }

public sealed class PurchaseRequest
{
    public Guid Id { get; set; }
    public string Title { get; set; } = "";
    public string Justification { get; set; } = "";
    public decimal Amount { get; set; }
    public string Currency { get; set; } = "EUR";
    public string RequestedByOid { get; set; } = "";
    public string RequestedByName { get; set; } = "";
    public DateTime CreatedAtUtc { get; set; }
    public RequestStatus Status { get; set; } = RequestStatus.Pending;
    public string? DecidedByOid { get; set; }
    public string? DecidedByName { get; set; }
    public DateTime? DecidedAtUtc { get; set; }
    public string? DecisionComment { get; set; }
    /// <summary>Optimistic concurrency: two approvers can't both win.</summary>
    public int Version { get; set; }
}

/// <summary>Append-only. The API has no endpoint that updates or deletes it, and the database user is denied it.</summary>
public sealed class AuditEntry
{
    public long Id { get; set; }
    public Guid RequestId { get; set; }
    public string Action { get; set; } = "";
    public string ActorOid { get; set; } = "";
    public string Detail { get; set; } = "";
    public DateTime AtUtc { get; set; }
    public string CorrelationId { get; set; } = "";
}

public static class AuditActions
{
    public const string Submitted = "Submitted";
    public const string Approved = "Approved";
    public const string Rejected = "Rejected";
    public const string DecisionDenied = "DecisionDenied";
}
