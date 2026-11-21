using System.Net.Http.Headers;
using System.Security.Cryptography;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;

namespace ExpenseClaims.Api.Tests;

/// <summary>
/// Runs the real app in memory with the real JwtBearer handler. Only the trust anchor changes: instead of
/// Microsoft Entra ID (or dotnet user-jwts), tokens are signed with a key generated for this test run.
/// </summary>
public sealed class ClaimsApiFactory : WebApplicationFactory<Program>
{
    public const string Issuer = "https://issuer.test.contoso/";
    public const string Audience = "api://contoso-expense-claims";
    public const int SubmitPerMinute = 3;

    private readonly SymmetricSecurityKey _key = new(RandomNumberGenerator.GetBytes(32));

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Development");                       // so /openapi/v1.json is mapped
        builder.UseSetting("RateLimits:SubmitPerMinute", SubmitPerMinute.ToString());

        builder.ConfigureTestServices(services =>
            services.PostConfigure<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme, o =>
            {
                o.Authority = null;
                o.TokenValidationParameters.ValidIssuers = [Issuer];
                o.TokenValidationParameters.ValidAudiences = [Audience];
                o.TokenValidationParameters.IssuerSigningKeys = [_key];
            }));
    }

    /// <summary>Creates a token shaped like a Microsoft Entra access token: oid, name and a roles array.</summary>
    public string Token(string oid, bool approver = false, string audience = Audience,
        DateTime? expires = null, SecurityKey? signWith = null)
    {
        var now = DateTime.UtcNow;
        var claims = new Dictionary<string, object> { ["oid"] = oid, ["name"] = oid };
        if (approver)
            claims["roles"] = new[] { "Claims.Approve" };

        return new JsonWebTokenHandler().CreateToken(new SecurityTokenDescriptor
        {
            Issuer = Issuer,
            Audience = audience,
            Claims = claims,
            NotBefore = now.AddMinutes(-10),
            IssuedAt = now.AddMinutes(-10),
            Expires = expires ?? now.AddMinutes(30),
            SigningCredentials = new SigningCredentials(signWith ?? _key, SecurityAlgorithms.HmacSha256),
        });
    }

    public HttpClient ClientFor(string oid, bool approver = false)
    {
        var client = CreateClient();
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", Token(oid, approver));
        return client;
    }
}
