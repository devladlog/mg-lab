namespace TenantApi.Data;

/// <summary>Every table whose rows belong to one tenant. The SQL security policy must cover each of them.</summary>
public interface ITenantScoped
{
    Guid TenantId { get; set; }
}

public sealed class PurchaseRequest : ITenantScoped
{
    public Guid TenantId { get; set; }
    public Guid Id { get; set; }
    public string Title { get; set; } = "";
    public decimal Amount { get; set; }
    public string Status { get; set; } = "submitted";
    /// <summary>The caller's oid claim (immutable per user). Never email or UPN: those can change and can be controlled by admins.</summary>
    public string CreatedBy { get; set; } = "";
    public DateTime CreatedUtc { get; set; }
}
