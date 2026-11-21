using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Caching.Memory;
using TenantApi.Data;

namespace TenantApi.Tenancy;

/// <summary>Looks up an onboarded tenant by its Entra tenant ID. Used on every request, so it is cached.</summary>
public interface ITenantDirectory
{
    TenantInfo? Find(Guid tenantId);
    /// <summary>Call after the catalog changes so the change is visible at once on this instance.</summary>
    void Forget(Guid tenantId);
}

public sealed class TenantDirectory(IServiceScopeFactory scopes, IMemoryCache cache) : ITenantDirectory
{
    static readonly TimeSpan Ttl = TimeSpan.FromSeconds(30);

    public TenantInfo? Find(Guid tenantId) =>
        cache.GetOrCreate(Key(tenantId), entry =>
        {
            // Unknown tenants are cached too (null), so a flood of tokens from strangers does not become a flood of queries.
            entry.AbsoluteExpirationRelativeToNow = Ttl;
            using var scope = scopes.CreateScope();
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            return db.Tenants.AsNoTracking()
                .Where(t => t.TenantId == tenantId)
                .Select(t => new TenantInfo(t.TenantId, t.Name, t.Plan, t.Status))
                .FirstOrDefault();
        });

    public void Forget(Guid tenantId) => cache.Remove(Key(tenantId));

    static string Key(Guid id) => "tenant:" + id.ToString("D");
}
