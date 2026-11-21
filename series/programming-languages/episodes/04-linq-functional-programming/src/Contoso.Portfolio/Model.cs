namespace Contoso.Portfolio;

public enum RequestStatus { Draft, Submitted, Approved, Rejected }
public enum Priority { Standard, High }

public sealed record Department(string Code, string Name);

/// <summary>Immutable. EF Core binds the constructor parameters to the properties of the same name.</summary>
public sealed record ProjectRequest(
    int Id, string Code, string Title, string DepartmentCode, decimal Budget, RequestStatus Status, DateOnly SubmittedOn);

/// <summary>Same rules as episodes 1-3. Pure functions: same input, same output, no side effects.</summary>
public static class Policy
{
    public const decimal HighPriorityFrom = 50_000m;
    public const decimal BoardFrom = 250_000m;

    public static Priority PriorityFor(decimal budget) => budget >= HighPriorityFrom ? Priority.High : Priority.Standard;

    /// <summary>A plain C# method: fine in LINQ to Objects, but EF Core can't turn it into SQL (see the gotcha).</summary>
    public static bool IsStrategic(ProjectRequest request) =>
        request.Budget >= BoardFrom || request.Title.Contains("platform", StringComparison.OrdinalIgnoreCase);
}
