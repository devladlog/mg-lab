namespace Contoso.Approvals.Api;

public sealed record ProjectRequestDto(string Code, string Title, string Department, string CostCenter, decimal Budget);
public sealed record BudgetDto(string CostCenter, decimal Remaining);
public sealed record ApproverDto(string Department, string Email);

/// <summary>Fictional Contoso data. Same rules family as episodes 1 and 2 (50,000 EUR = High priority).</summary>
public static class FinanceData
{
    public static readonly IReadOnlyList<ProjectRequestDto> Requests =
    [
        new("PR-2026-0101", "Laptop refresh", "IT", "CC-100", 18_000m),
        new("PR-2026-0102", "CRM rollout", "Sales", "CC-200", 75_000m),
        new("PR-2026-0103", "New data platform", "IT", "CC-100", 300_000m),
        new("PR-2026-0104", "Office move", "Operations", "CC-300", 42_000m),
        new("PR-2026-0105", "Brand refresh", "Marketing", "CC-400", 55_000m),
        new("PR-2026-0106", "Security training", "IT", "CC-100", 9_500m),
        new("PR-2026-0107", "Partner portal", "Sales", "CC-200", 120_000m),
        new("PR-2026-0108", "Fleet telematics", "Operations", "CC-300", 64_000m),
        new("PR-2026-0109", "Trade fair stand", "Marketing", "CC-400", 31_000m),
        new("PR-2026-0110", "Backup appliance", "IT", "CC-100", 27_000m),
        new("PR-2026-0111", "Sales enablement", "Sales", "CC-200", 16_000m),
        new("PR-2026-0112", "Warehouse scanners", "Operations", "CC-300", 22_000m),
    ];

    private static readonly Dictionary<string, decimal> Remaining = new(StringComparer.OrdinalIgnoreCase)
    {
        ["CC-100"] = 250_000m, ["CC-200"] = 100_000m, ["CC-300"] = 90_000m, ["CC-400"] = 40_000m,
    };

    private static readonly Dictionary<string, string> Approvers = new(StringComparer.OrdinalIgnoreCase)
    {
        ["IT"] = "kim.demo@contoso.com", ["Sales"] = "sam.demo@contoso.com",
        ["Operations"] = "alex.demo@contoso.com", ["Marketing"] = "lee.demo@contoso.com",
    };

    public static BudgetDto? Budget(string costCenter) =>
        Remaining.TryGetValue(costCenter, out var left) ? new BudgetDto(costCenter.ToUpperInvariant(), left) : null;

    public static ApproverDto? Approver(string department) =>
        Approvers.TryGetValue(department, out var email) ? new ApproverDto(department, email) : null;
}
