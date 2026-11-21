using System.Security.Claims;

namespace TenantApi.Tenancy;

/// <summary>
/// The tenant of the current request. It has exactly one source: the signed token's tid claim.
/// Never a header, a route value, a query string or the request body (a caller controls all of those).
/// Unresolved means Guid.Empty, and every data filter treats that as "no rows".
/// </summary>
public sealed class TenantContext
{
    public Guid TenantId { get; private set; }
    public TenantInfo? Info { get; private set; }
    public bool IsResolved => TenantId != Guid.Empty;

    public void Resolve(ClaimsPrincipal user, ITenantDirectory directory)
    {
        var tid = user.FindFirst("tid")?.Value;
        if (!Guid.TryParse(tid, out var id)) return;
        TenantId = id;
        Info = directory.Find(id);
    }

    /// <summary>Tests and background jobs that act for one tenant.</summary>
    public void Use(Guid tenantId) { TenantId = tenantId; Info = null; }
}
