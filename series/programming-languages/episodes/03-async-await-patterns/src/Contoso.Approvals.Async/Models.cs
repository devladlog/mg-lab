namespace Contoso.Approvals;

public sealed record ProjectRequest(string Code, string Title, string Department, string CostCenter, decimal Budget);
public sealed record BudgetInfo(string CostCenter, decimal Remaining);
public sealed record Approver(string Department, string Email);

/// <summary>A request with the two lookups it needs before somebody can approve it.</summary>
public sealed record EnrichedRequest(ProjectRequest Request, BudgetInfo Budget, Approver Approver)
{
    public bool WithinBudget => Request.Budget <= Budget.Remaining;
}
