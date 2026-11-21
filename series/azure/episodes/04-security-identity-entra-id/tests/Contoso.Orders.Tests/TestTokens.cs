using System.Security.Claims;
using System.Security.Cryptography;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Protocols.OpenIdConnect;
using Microsoft.IdentityModel.Tokens;

namespace Contoso.Orders.Tests;

/// <summary>
/// Mints Entra-shaped v2.0 access tokens signed with a test RSA key. The API keeps Microsoft.Identity.Web's own
/// validation (audience, lifetime, scope/role checks); only the signing keys and the issuer check are swapped,
/// because the real ones come from the tenant's OpenID metadata on the internet.
/// </summary>
public static class TestTokens
{
    public const string TenantId = "00000000-0000-0000-0000-000000000000";
    public const string ApiClientId = "00000000-0000-0000-0000-000000000001";
    public const string ProcessorClientId = "00000000-0000-0000-0000-00000000000c";
    public const string CliClientId = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"; // Microsoft Azure CLI (first-party)
    public static readonly string Issuer = $"https://login.microsoftonline.com/{TenantId}/v2.0";

    public static readonly RsaSecurityKey Key = new(RSA.Create(2048)) { KeyId = "test-key" };
    private static readonly RsaSecurityKey OtherKey = new(RSA.Create(2048)) { KeyId = "test-key" };

    public static string Create(IDictionary<string, object> claims, string? audience = ApiClientId,
        DateTime? expires = null, bool wrongKey = false)
    {
        var now = DateTime.UtcNow;
        var all = new Dictionary<string, object>(claims) { ["tid"] = TenantId, ["ver"] = "2.0" };
        var descriptor = new SecurityTokenDescriptor
        {
            Issuer = Issuer,
            Audience = audience,
            Claims = all,
            NotBefore = now.AddMinutes(-5),
            IssuedAt = now.AddMinutes(-5),
            Expires = expires ?? now.AddMinutes(55),
            SigningCredentials = new SigningCredentials(wrongKey ? OtherKey : Key, SecurityAlgorithms.RsaSha256),
        };
        return new JsonWebTokenHandler().CreateToken(descriptor);
    }

    /// <summary>A person, through the Azure CLI, with the delegated Orders.Read scope (and the Orders.Reader role).</summary>
    public static string User(string scp = "Orders.Read", string[]? roles = null) => Create(new Dictionary<string, object>
    {
        ["scp"] = scp,
        ["roles"] = roles ?? ["Orders.Reader"],
        ["azp"] = CliClientId,
        ["oid"] = "00000000-0000-0000-0000-0000000000a1",
        ["sub"] = "alex-demo",
    });

    /// <summary>The order processor's managed identity, app-only (no scp, idtyp = app).</summary>
    public static string App(string[]? roles = null, bool idtyp = true)
    {
        var claims = new Dictionary<string, object>
        {
            ["azp"] = ProcessorClientId,
            ["oid"] = "00000000-0000-0000-0000-0000000000b2",
            ["sub"] = "00000000-0000-0000-0000-0000000000b2",
        };
        if (roles is not null) claims["roles"] = roles;
        if (idtyp) claims["idtyp"] = "app";
        return Create(claims);
    }
}

public sealed class ApiFactory : WebApplicationFactory<Program>
{
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseSetting("AzureAd:Instance", "https://login.microsoftonline.com/");
        builder.UseSetting("AzureAd:TenantId", TestTokens.TenantId);
        builder.UseSetting("AzureAd:ClientId", TestTokens.ApiClientId);
        builder.ConfigureServices(services =>
            services.PostConfigure<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme, o =>
            {
                var config = new OpenIdConnectConfiguration { Issuer = TestTokens.Issuer };
                config.SigningKeys.Add(TestTokens.Key);
                o.Configuration = config;                         // no metadata download
                o.ConfigurationManager = null;
                o.TokenValidationParameters.IssuerSigningKey = TestTokens.Key;
                o.TokenValidationParameters.IssuerValidator = null;
                o.TokenValidationParameters.ValidIssuer = TestTokens.Issuer;
                // Audience validation is left exactly as Microsoft.Identity.Web configured it.
            }));
    }
}
