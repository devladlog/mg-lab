namespace Contoso.Requests.Clean;

/// <summary>Why a line was rejected. The numbers are the legacy ERR codes, kept for the output format.</summary>
public enum Rejection
{
    WrongFieldCount = 0,
    InvalidCode = 1,
    InvalidBudget = 2,
    UnknownDepartment = 3,
    MissingJustification = 4,
}

public abstract record Outcome;

public sealed record Routed(string Code, Priority Priority, IReadOnlyList<string> Approvers, decimal TotalWithContingency)
    : Outcome;

public sealed record Rejected(Rejection Reason) : Outcome;

/// <summary>Guard clauses, in the same order as the legacy checks (the golden master pins the order).</summary>
public sealed class RequestProcessor(MidpointRounding rounding = MidpointRounding.ToEven)
{
    public Outcome Process(string line)
    {
        if (!RequestFields.TrySplit(line, out var request))
        {
            return new Rejected(Rejection.WrongFieldCount);
        }

        if (!request.HasValidCode)
        {
            return new Rejected(Rejection.InvalidCode);
        }

        if (!request.TryGetBudget(out var budget))
        {
            return new Rejected(Rejection.InvalidBudget);
        }

        var priority = ApprovalPolicy.PriorityFor(budget);
        if (ApprovalPolicy.NeedsJustification(priority) && !request.HasJustification)
        {
            return new Rejected(Rejection.MissingJustification);
        }

        if (!DepartmentManagers.TryFind(request.Department, out var manager))
        {
            return new Rejected(Rejection.UnknownDepartment);
        }

        return new Routed(request.Code, priority, ApprovalPolicy.ApproversFor(priority, manager),
            ApprovalPolicy.WithContingency(budget, rounding));
    }
}
