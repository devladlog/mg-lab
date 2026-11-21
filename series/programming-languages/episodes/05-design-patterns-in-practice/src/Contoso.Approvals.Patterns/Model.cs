namespace Contoso.Approvals.Patterns;

/// <summary>A Contoso project request, same rules as episodes 1-4 of the series.</summary>
public sealed record ProjectRequest(
    string Code,
    string Title,
    string Department,
    decimal Budget,
    string RequestedBy,
    string? Justification = null);

public enum ApproverRole
{
    Manager,
    Finance,
    Board,
}

/// <summary>What a route strategy decides: which roles approve, in which order, and how fast.</summary>
public sealed record RoutePlan(string Route, IReadOnlyList<ApproverRole> Roles, int DueInDays, IReadOnlyList<string> Warnings);

public sealed record ApprovalStep(ApproverRole Role, string Approver);

/// <summary>The event observers receive once a request has a route and named approvers.</summary>
public sealed record RequestRouted(
    ProjectRequest Request,
    string Route,
    IReadOnlyList<ApprovalStep> Steps,
    int DueInDays,
    IReadOnlyList<string> Warnings);

/// <summary>Result of a submission: the routed request plus any observer that failed (the others still ran).</summary>
public sealed record SubmitResult(RequestRouted Routed, IReadOnlyList<string> ObserverFailures);
