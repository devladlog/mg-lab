using System.Text.Json.Serialization;

namespace Contoso.InvoiceApproval;

/// <summary>Message on the Service Bus queue, sent by the "Invoice ready" flow (fields from the episode 1 library).</summary>
public sealed record InvoiceReady(
    string InvoiceKey,      // InvDedupKey from episode 1, e.g. "fabrikam|INV1001"
    int ItemId,             // SharePoint list item ID in "Invoices Inbox"
    string Vendor,
    string InvoiceNumber,
    decimal Total,
    string Currency,
    string SubmittedBy,     // e-mail of whoever uploaded the invoice
    string FileUrl);

/// <summary>Read from configuration by the starter and passed IN the orchestration input, so replays never re-read it.</summary>
public sealed record ApprovalSettings(
    string ManagerEmail,
    string FinanceEmail,
    string EscalationEmail,
    decimal FinanceThreshold,
    int StageTimeoutSeconds);

public sealed record ApprovalInput(InvoiceReady Invoice, ApprovalSettings Settings);

public sealed record Stage(string Name, string Approver, string? EscalateTo);

/// <summary>What the orchestration asks Power Automate to put in front of a person.</summary>
public sealed record ApprovalRequest(
    string InstanceId, string RequestId, string Stage, string Approver, int Attempt, DateTime DueUtc, InvoiceReady Invoice);

/// <summary>Custom status while waiting: tells the decision endpoint which request is the live one.</summary>
public sealed record PendingApproval(string Stage, string RequestId, string Approver, int Attempt, DateTime DueUtc);

/// <summary>Payload of the external event raised by the decision endpoint.</summary>
public sealed record DecisionEvent(string Outcome, string Responder, string? Comments);

public sealed record StageResult(string Stage, string Status, string? DecidedBy, string? Comments, int Attempts);

public sealed record ApprovalOutcome(string InstanceId, InvoiceReady Invoice, string Status, IReadOnlyList<StageResult> Stages, string Summary);

/// <summary>Values of the "Approval status" choice column (see contract/approval-columns.json).</summary>
public static class ApprovalStatus
{
    public const string NotStarted = "Not started";
    public const string Waiting = "Waiting for approval";
    public const string Approved = "Approved";
    public const string Rejected = "Rejected";
    public const string Expired = "Expired";

    public static readonly string[] All = [NotStarted, Waiting, Approved, Rejected, Expired];
}

/// <summary>The one message shape the "Invoice approval relay" flow receives (its trigger schema matches this).</summary>
public sealed record FlowMessage
{
    public const string ApprovalRequestKind = "approval-request";
    public const string OutcomeKind = "outcome";

    public required string Kind { get; init; }
    public required string InstanceId { get; init; }
    public required int ItemId { get; init; }
    public required string Vendor { get; init; }
    public required string InvoiceNumber { get; init; }
    public required decimal Total { get; init; }
    public required string Currency { get; init; }
    public required string FileUrl { get; init; }
    public required string SubmittedBy { get; init; }
    public required string Status { get; init; }
    public required string StatusText { get; init; }

    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? ApproverEmail { get; init; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? Stage { get; init; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public DateTime? DueUtc { get; init; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? CallbackUrl { get; init; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? DecidedBy { get; init; }
}
