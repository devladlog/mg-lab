using Microsoft.AspNetCore.Authorization;

namespace TenantApi;

public static class Policies
{
    public const string Tenant = "tenant-user";
    public const string PlatformAdmin = "platform-admin";

    public static void AddTenantPolicies(this AuthorizationOptions o, string requiredScope, Guid homeTenantId)
    {
        // Any signed-in user of an onboarded tenant who was granted our delegated scope.
        o.AddPolicy(Tenant, p => p
            .RequireAuthenticatedUser()
            .RequireAssertion(c => HasScope(c.User, requiredScope)));

        // Platform admin: the app role AND the provider's own tenant. A customer's admin can assign any app role
        // of ours to their own users, so the role alone proves nothing: tid decides whose role it is.
        o.AddPolicy(PlatformAdmin, p => p
            .RequireAuthenticatedUser()
            .RequireClaim("roles", "Platform.Admin")
            .RequireAssertion(c => Guid.TryParse(c.User.FindFirst("tid")?.Value, out var tid) && tid == homeTenantId));
    }

    static bool HasScope(System.Security.Claims.ClaimsPrincipal user, string scope) =>
        (user.FindFirst("scp")?.Value ?? "").Split(' ', StringSplitOptions.RemoveEmptyEntries).Contains(scope, StringComparer.Ordinal);
}
