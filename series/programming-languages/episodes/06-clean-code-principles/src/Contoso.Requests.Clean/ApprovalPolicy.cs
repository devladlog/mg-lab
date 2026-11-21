namespace Contoso.Requests.Clean;

public enum Priority
{
    Normal,
    High,
    Board,
}

/// <summary>The business rules, each with a name instead of a magic number.</summary>
public static class ApprovalPolicy
{
    /// <summary>Series rule: 50,000 and above is High. The legacy code used "&gt; 50000" (see README).</summary>
    public const decimal HighPriorityFrom = 50_000m;

    public const decimal BoardFrom = 250_000m;

    public const decimal ContingencyRate = 0.15m;

    public const string FinanceApprover = "sam.demo";

    public const string BoardApprover = "board";

    public static Priority PriorityFor(decimal budget) =>
        budget >= BoardFrom ? Priority.Board
        : budget >= HighPriorityFrom ? Priority.High
        : Priority.Normal;

    public static bool NeedsJustification(Priority priority) => priority == Priority.Board;

    public static IReadOnlyList<string> ApproversFor(Priority priority, string manager) => priority switch
    {
        Priority.Board => [manager, FinanceApprover, BoardApprover],
        Priority.High => [manager, FinanceApprover],
        _ => [manager],
    };

    /// <summary>
    /// Budget plus contingency, rounded to whole euros. Math.Round's default for decimal is
    /// MidpointRounding.ToEven (banker's rounding), and the legacy code relied on it: we keep it on purpose.
    /// </summary>
    public static decimal WithContingency(decimal budget, MidpointRounding rounding = MidpointRounding.ToEven) =>
        Math.Round(budget * (1 + ContingencyRate), rounding);
}
