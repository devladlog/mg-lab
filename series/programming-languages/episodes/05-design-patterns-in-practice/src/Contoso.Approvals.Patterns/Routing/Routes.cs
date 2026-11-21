using Microsoft.Extensions.Options;

namespace Contoso.Approvals.Patterns.Routing;

/// <summary>Strategy: one interface, one class per way of routing a request.</summary>
public interface IApprovalRoute
{
    string Key { get; }

    RoutePlan Plan(ProjectRequest request);
}

public static class RouteKeys
{
    public const string Standard = "standard";
    public const string High = "high";
    public const string Board = "board";

    /// <summary>
    /// Not everything needs a pattern: choosing the key is one expression, kept as a pure function.
    /// </summary>
    public static string For(decimal budget, ApprovalPolicyOptions policy) =>
        budget >= policy.BoardThreshold ? Board
        : budget >= policy.HighThreshold ? High
        : Standard;
}

public sealed class StandardRoute(IOptions<ApprovalPolicyOptions> policy) : IApprovalRoute
{
    public string Key => RouteKeys.Standard;

    public RoutePlan Plan(ProjectRequest request) =>
        new(Key, [ApproverRole.Manager], policy.Value.StandardDueDays, []);
}

public sealed class HighValueRoute(IOptions<ApprovalPolicyOptions> policy) : IApprovalRoute
{
    public string Key => RouteKeys.High;

    public RoutePlan Plan(ProjectRequest request) =>
        new(Key, [ApproverRole.Manager, ApproverRole.Finance], policy.Value.HighDueDays, []);
}

/// <summary>Board requests: Finance first, Board last, and a justification is mandatory.</summary>
public sealed class BoardRoute(IOptions<ApprovalPolicyOptions> policy) : IApprovalRoute
{
    public string Key => RouteKeys.Board;

    public RoutePlan Plan(ProjectRequest request)
    {
        string[] warnings = string.IsNullOrWhiteSpace(request.Justification)
            ? ["justification required for board requests"]
            : [];
        return new(Key, [ApproverRole.Finance, ApproverRole.Board], policy.Value.BoardDueDays, warnings);
    }
}
