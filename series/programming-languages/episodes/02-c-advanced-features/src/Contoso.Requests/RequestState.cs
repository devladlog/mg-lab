namespace Contoso.Requests;

/// <summary>
/// A closed set of states: the private constructor means only the nested records can derive.
/// The compiler still can't prove the switch is exhaustive (C# has no closed hierarchies), see Rules.Describe.
/// </summary>
public abstract record RequestState
{
    private RequestState() { }

    public sealed record Draft : RequestState;
    public sealed record Submitted(DateTimeOffset At) : RequestState;
    public sealed record Approved(string By, DateTimeOffset At) : RequestState;
    public sealed record Rejected(string By, string Reason) : RequestState;
}

public sealed record Approval(string Approver, string Role, DateTimeOffset At);
