namespace Contoso.Mobile.Core.Models;

/// <summary>A request as the gateway returns it (episode 11). Unknown JSON fields (idempotencyKey, traceId) are ignored.</summary>
public sealed record RequestItem(
    int Id, string Title, string Department, decimal Amount, string RequestedBy, string BudgetState, DateTime CreatedAtUtc);

/// <summary>
/// A request the user submitted, kept on the device until the server has it. <see cref="Key"/> is created once, when the user taps
/// Submit, and is sent as the Idempotency-Key on every attempt: sending the same draft twice can never create two requests.
/// </summary>
public sealed record DraftRequest(
    Guid Key, string Title, string DepartmentCode, decimal Amount, string RequestedBy, DateTime QueuedAtUtc, string? Error = null)
{
    public bool NeedsAttention => Error is not null;
}

public enum SubmitOutcome
{
    Created,       // 201: stored, budget reserved or declined
    Replayed,      // 200: the server already had this key
    Accepted,      // 202: stored, budget check still pending on the server
    Rejected,      // 4xx: the server will never accept this as it is
    Unavailable,   // no network, timeout, 5xx: try again later
}

public sealed record SubmitResult(SubmitOutcome Outcome, RequestItem? Item = null, string? Error = null)
{
    public bool IsStored => Outcome is SubmitOutcome.Created or SubmitOutcome.Replayed or SubmitOutcome.Accepted;
}

public sealed record SyncReport(int Sent, int Rejected, int Remaining, bool Skipped);
