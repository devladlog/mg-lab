using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;

namespace TenantApi.Tenancy;

/// <summary>
/// Issuer validation for a multitenant API. Signing keys come from the shared "organizations" metadata, whose issuer
/// is a template, so the standard check cannot work. Instead: the token must be a v2.0 token, its issuer must be
/// exactly login.microsoftonline.com/{tid}/v2.0 for its OWN tid claim, and that tid must be an onboarded tenant (or the provider's home tenant).
/// </summary>
public static class TenantIssuer
{
    public static string ExpectedIssuer(string instance, Guid tenantId) =>
        $"{instance.TrimEnd('/')}/{tenantId:D}/v2.0";

    public static string Validate(string issuer, SecurityToken token, string instance, Guid homeTenantId, ITenantDirectory directory)
    {
        if (token is not JsonWebToken jwt)
            throw new SecurityTokenInvalidIssuerException("Unsupported token type.") { InvalidIssuer = issuer };

        if (!jwt.TryGetPayloadValue<string>("tid", out var tid) || !Guid.TryParse(tid, out var tenantId))
            throw new SecurityTokenInvalidIssuerException("Token has no valid tid claim.") { InvalidIssuer = issuer };

        if (!string.Equals(issuer, ExpectedIssuer(instance, tenantId), StringComparison.Ordinal))
            throw new SecurityTokenInvalidIssuerException("Issuer does not match the token's tenant.") { InvalidIssuer = issuer };

        // The provider's own staff sign in from the home tenant, which is not a customer and not in the catalog.
        if (tenantId != homeTenantId && directory.Find(tenantId) is null)
            throw new SecurityTokenInvalidIssuerException("Tenant is not onboarded.") { InvalidIssuer = issuer };

        return issuer;
    }
}
