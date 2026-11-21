using System.Diagnostics;

namespace Contoso.Requests;

public enum Route { TeamLead, Finance, Board }

public static class Rules
{
    public static readonly Euros HighPriorityFrom = new(50_000m);
    public static readonly Euros JustificationFrom = new(250_000m);

    public static Priority PriorityFor(Euros budget) => budget >= HighPriorityFrom ? Priority.High : Priority.Standard;

    /// <summary>Relational and property patterns: the routing table reads like the policy document.</summary>
    public static Route RouteFor(ProjectRequest request) => request switch
    {
        { Budget.Amount: >= 250_000m } => Route.Board,
        { Budget.Amount: >= 50_000m } or { Justification: not null } => Route.Finance,
        _ => Route.TeamLead,
    };

    /// <summary>
    /// List patterns over the approvals. Board requests need Finance first and the Board last.
    /// </summary>
    public static bool IsFullyApproved(ProjectRequest request) => (RouteFor(request), request.Approvals) switch
    {
        (Route.TeamLead, [_, ..]) => true,
        (Route.Finance, [.., { Role: "Finance" }]) => true,
        (Route.Board, [{ Role: "Finance" }, .., { Role: "Board" }]) => true,
        _ => false,
    };

    /// <summary>
    /// Type patterns with deconstruction. The discard arm is required: RequestState has a private constructor,
    /// but the compiler doesn't treat the hierarchy as closed, so without `_` we'd get CS8509.
    /// </summary>
    public static string Describe(RequestState state) => state switch
    {
        RequestState.Draft => "Draft",
        RequestState.Submitted(var at) => $"Waiting for approval since {at:yyyy-MM-dd}",
        RequestState.Approved(var by, _) => $"Approved by {by}",
        RequestState.Rejected(var by, var reason) => $"Rejected by {by}: {reason}",
        _ => throw new UnreachableException($"Unknown state {state.GetType().Name}"),
    };
}
