namespace TenantApi.Tenancy;

/// <summary>What a plan allows. Bound from the "Plans" configuration section, so tests (and ops) can change it.</summary>
public sealed class PlanLimits
{
    /// <summary>Purchase requests a tenant may store.</summary>
    public int MaxRequests { get; set; }
    /// <summary>Calls per minute for the whole tenant, shared by all its users.</summary>
    public int RequestsPerMinute { get; set; }
}

public sealed class PlanCatalog
{
    public Dictionary<string, PlanLimits> Plans { get; } = new(StringComparer.OrdinalIgnoreCase)
    {
        ["starter"] = new PlanLimits { MaxRequests = 25, RequestsPerMinute = 30 },
        ["business"] = new PlanLimits { MaxRequests = 1000, RequestsPerMinute = 120 },
    };

    public bool IsKnown(string plan) => Plans.ContainsKey(plan);

    /// <summary>Unknown plan names fall back to the smallest plan: a typo must never mean "unlimited".</summary>
    public PlanLimits For(string plan) =>
        Plans.TryGetValue(plan, out var l) ? l : Plans.Values.OrderBy(p => p.MaxRequests).First();
}
