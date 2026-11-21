using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.IdentityModel.Tokens;

namespace PurchaseRequests.Api.Security;

/// <summary>Settings for the API's own Microsoft Entra app registration (section "Entra").</summary>
public sealed class EntraOptions
{
    public string Instance { get; set; } = "https://login.microsoftonline.com/";
    public string TenantId { get; set; } = "";
    public string ClientId { get; set; } = "";
    /// <summary>Delegated scope the Power Apps custom connector asks for.</summary>
    public string RequiredScope { get; set; } = "PurchaseRequests.ReadWrite";

    public void Validate()
    {
        if (!Guid.TryParse(TenantId, out _))
            throw new InvalidOperationException("Entra:TenantId must be the tenant GUID (not 'common' or a domain name).");
        if (!Guid.TryParse(ClientId, out _))
            throw new InvalidOperationException("Entra:ClientId must be the API app registration's client ID.");
        if (string.IsNullOrWhiteSpace(RequiredScope) || RequiredScope.Contains(' '))
            throw new InvalidOperationException("Entra:RequiredScope must be one scope name.");
    }
}

public static class EntraJwt
{
    /// <summary>
    /// Both token versions for ONE tenant. Entra issues the version the API registration asks for
    /// (requestedAccessTokenVersion): null or 1 gives v1.0 tokens (issuer sts.windows.net, audience = App ID URI),
    /// 2 gives v2.0 tokens (issuer login.microsoftonline.com/{tid}/v2.0, audience = client ID).
    /// </summary>
    public static string[] ValidIssuers(EntraOptions o) =>
    [
        $"{o.Instance.TrimEnd('/')}/{o.TenantId}/v2.0",
        $"https://sts.windows.net/{o.TenantId}/",
    ];

    public static string[] ValidAudiences(EntraOptions o) => [o.ClientId, $"api://{o.ClientId}"];

    public static AuthenticationBuilder AddEntraJwtBearer(this IServiceCollection services, EntraOptions o)
    {
        o.Validate();
        return services
            .AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
            .AddJwtBearer(options =>
            {
                // Signing keys come from the tenant's OpenID metadata (same keys sign v1 and v2 tokens).
                options.Authority = $"{o.Instance.TrimEnd('/')}/{o.TenantId}/v2.0";
                // Keep Entra claim names as they are: "scp", "roles", "oid". With the default mapping,
                // "roles" and "scp" are renamed to long schema URIs and policies silently stop matching.
                options.MapInboundClaims = false;
                options.TokenValidationParameters = new TokenValidationParameters
                {
                    ValidateIssuer = true,
                    ValidIssuers = ValidIssuers(o),
                    ValidateAudience = true,
                    ValidAudiences = ValidAudiences(o),
                    ValidateLifetime = true,
                    ValidateIssuerSigningKey = true,
                    RequireSignedTokens = true,
                    ClockSkew = TimeSpan.FromMinutes(2),
                    NameClaimType = "name",
                    RoleClaimType = "roles",
                };
            });
    }
}
