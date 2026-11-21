using System.Globalization;
using PurchaseRequests.Api.Security;

namespace PurchaseRequests.Api.Domain;

/// <summary>Section "Approval" in configuration.</summary>
public sealed class ApprovalPolicy
{
    public string Currency { get; set; } = "EUR";
    public decimal FinanceThreshold { get; set; } = 5000m;
    public decimal MaxAmount { get; set; } = 50000m;
}

public enum DecisionOutcome { Approve, Reject }

public sealed record RuleResult(bool Allowed, int StatusCode, string? Reason)
{
    public static readonly RuleResult Ok = new(true, StatusCodes.Status200OK, null);
    public static RuleResult Forbidden(string reason) => new(false, StatusCodes.Status403Forbidden, reason);
    public static RuleResult Conflict(string reason) => new(false, StatusCodes.Status409Conflict, reason);
}

/// <summary>Business rules for decisions. Pure functions: no HTTP, no database, easy to test.</summary>
public static class ApprovalRules
{
    public static RuleResult CanDecide(PurchaseRequest request, Caller caller, DecisionOutcome outcome, ApprovalPolicy policy)
    {
        if (request.Status != RequestStatus.Pending)
            return RuleResult.Conflict($"This request is already {request.Status.ToString().ToLowerInvariant()}.");

        // Segregation of duties: nobody decides on their own request, whatever roles they hold.
        if (string.Equals(request.RequestedByOid, caller.Oid, StringComparison.OrdinalIgnoreCase))
            return RuleResult.Forbidden("You can't approve or reject your own request.");

        if (outcome == DecisionOutcome.Approve && request.Amount > policy.FinanceThreshold
            && !caller.IsFinanceApprover)
            return RuleResult.Forbidden(string.Create(CultureInfo.InvariantCulture,
                $"Requests above {policy.FinanceThreshold:N0} {policy.Currency} need a finance approver."));

        return RuleResult.Ok;
    }

    /// <summary>Who may see a request: its owner, or anyone allowed to decide.</summary>
    public static bool CanRead(PurchaseRequest request, Caller caller) =>
        caller.IsApprover || string.Equals(request.RequestedByOid, caller.Oid, StringComparison.OrdinalIgnoreCase);
}
