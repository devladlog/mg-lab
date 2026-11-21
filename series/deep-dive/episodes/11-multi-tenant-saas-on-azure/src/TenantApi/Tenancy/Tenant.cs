namespace TenantApi.Tenancy;

public static class TenantStatus
{
    public const string Active = "active";
    public const string Suspended = "suspended";
    public static bool IsValid(string s) => s is Active or Suspended;
}

/// <summary>One row of the tenant catalog. TenantId is the customer's Microsoft Entra tenant ID (the token's tid).</summary>
public sealed class Tenant
{
    public Guid TenantId { get; set; }
    public string Name { get; set; } = "";
    public string Plan { get; set; } = "starter";
    public string Status { get; set; } = TenantStatus.Active;
    public DateTime CreatedUtc { get; set; }
}

public sealed record TenantInfo(Guid TenantId, string Name, string Plan, string Status)
{
    public bool IsActive => Status == TenantStatus.Active;
}
