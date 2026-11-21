namespace Contoso.Portfolio;

/// <summary>Fictional Contoso portfolio. Legal has no requests on purpose (left join).</summary>
public static class SampleData
{
    public static IReadOnlyList<Department> Departments { get; } =
    [
        new("IT", "Information Technology"), new("SAL", "Sales"), new("OPS", "Operations"),
        new("MKT", "Marketing"), new("LEG", "Legal"),
    ];

    public static IReadOnlyList<ProjectRequest> Requests { get; } =
    [
        new(1, "PR-2026-0101", "Laptop refresh", "IT", 18_000m, RequestStatus.Approved, new(2026, 9, 1)),
        new(2, "PR-2026-0102", "CRM rollout", "SAL", 75_000m, RequestStatus.Submitted, new(2026, 9, 3)),
        new(3, "PR-2026-0103", "New data platform", "IT", 300_000m, RequestStatus.Submitted, new(2026, 9, 8)),
        new(4, "PR-2026-0104", "Office move", "OPS", 42_000m, RequestStatus.Approved, new(2026, 9, 10)),
        new(5, "PR-2026-0105", "Brand refresh", "MKT", 55_000m, RequestStatus.Rejected, new(2026, 9, 15)),
        new(6, "PR-2026-0106", "Security training", "IT", 9_500m, RequestStatus.Approved, new(2026, 9, 18)),
        new(7, "PR-2026-0107", "Partner portal", "SAL", 120_000m, RequestStatus.Draft, new(2026, 9, 22)),
        new(8, "PR-2026-0108", "Fleet telematics", "OPS", 64_000m, RequestStatus.Submitted, new(2026, 9, 25)),
        new(9, "PR-2026-0109", "Trade fair stand", "MKT", 31_000m, RequestStatus.Approved, new(2026, 10, 1)),
        new(10, "PR-2026-0110", "Backup appliance", "IT", 27_000m, RequestStatus.Submitted, new(2026, 10, 6)),
        new(11, "PR-2026-0111", "Sales enablement", "SAL", 16_000m, RequestStatus.Draft, new(2026, 10, 9)),
        new(12, "PR-2026-0112", "Warehouse scanners", "OPS", 22_000m, RequestStatus.Approved, new(2026, 10, 14)),
    ];
}
