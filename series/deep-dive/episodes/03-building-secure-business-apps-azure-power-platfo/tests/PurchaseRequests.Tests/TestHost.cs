using System.Net.Http.Headers;
using System.Security.Cryptography;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Protocols;
using Microsoft.IdentityModel.Protocols.OpenIdConnect;
using Microsoft.IdentityModel.Tokens;
using PurchaseRequests.Api.Data;

namespace PurchaseRequests.Tests;

/// <summary>Fictional identifiers only (zero GUIDs).</summary>
public static class Ids
{
    public const string Tenant = "00000000-0000-0000-0000-000000000000";
    public const string OtherTenant = "00000000-0000-0000-0000-0000000000ff";
    public const string ApiClient = "00000000-0000-0000-0000-0000000000a1";
    public const string Alex = "00000000-0000-0000-0000-00000000a1e0";   // requester
    public const string Riley = "00000000-0000-0000-0000-00000000a1e1";  // another requester
    public const string Sam = "00000000-0000-0000-0000-00000000a1e2";    // approver
    public const string Jordan = "00000000-0000-0000-0000-00000000a1e3"; // approver + finance
}

/// <summary>Issues real RS256 JWTs shaped like Entra access tokens, signed by a key only the tests know.</summary>
public static class TestTokens
{
    public static readonly RsaSecurityKey SigningKey = new(RSA.Create(2048)) { KeyId = "test-key" };
    static readonly RsaSecurityKey OtherKey = new(RSA.Create(2048)) { KeyId = "test-key" };

    public sealed record Options
    {
        public string Oid { get; init; } = Ids.Alex;
        public string Name { get; init; } = "Alex Demo";
        public string[] Roles { get; init; } = ["Requester"];
        public string? Scope { get; init; } = "PurchaseRequests.ReadWrite";
        public int Version { get; init; } = 2;
        public string Tenant { get; init; } = Ids.Tenant;
        public string? Audience { get; init; }
        public string? Issuer { get; init; }
        public TimeSpan Lifetime { get; init; } = TimeSpan.FromMinutes(60);
        public DateTime? NotBefore { get; init; }
        public bool WrongKey { get; init; }
    }

    public static string Create(Options o)
    {
        var issuer = o.Issuer ?? (o.Version == 2
            ? $"https://login.microsoftonline.com/{o.Tenant}/v2.0"
            : $"https://sts.windows.net/{o.Tenant}/");
        var audience = o.Audience ?? (o.Version == 2 ? Ids.ApiClient : $"api://{Ids.ApiClient}");
        var claims = new Dictionary<string, object>
        {
            ["oid"] = o.Oid,
            ["name"] = o.Name,
            ["tid"] = o.Tenant,
            ["ver"] = o.Version == 2 ? "2.0" : "1.0",
        };
        if (o.Scope is not null) claims["scp"] = o.Scope;
        if (o.Roles.Length > 0) claims["roles"] = o.Roles;

        var notBefore = o.NotBefore ?? DateTime.UtcNow.AddMinutes(-1);
        return new JsonWebTokenHandler().CreateToken(new SecurityTokenDescriptor
        {
            Issuer = issuer,
            Audience = audience,
            Claims = claims,
            NotBefore = notBefore,
            IssuedAt = notBefore,
            Expires = notBefore + o.Lifetime,
            SigningCredentials = new SigningCredentials(o.WrongKey ? OtherKey : SigningKey, SecurityAlgorithms.RsaSha256),
        });
    }

    public static Options Alex => new();
    public static Options Riley => new() { Oid = Ids.Riley, Name = "Riley Demo" };
    public static Options Sam => new() { Oid = Ids.Sam, Name = "Sam Demo", Roles = ["Approver", "Requester"] };
    public static Options Jordan => new() { Oid = Ids.Jordan, Name = "Jordan Demo", Roles = ["Approver", "Finance.Approver"] };
}

/// <summary>
/// The real app with its real authentication and authorization. Only two things change for tests:
/// the database is SQLite in memory, and the signing keys come from <see cref="TestTokens"/> instead of the
/// tenant's metadata endpoint. Issuer, audience, lifetime and claim rules are the production ones.
/// </summary>
public sealed class ApiFactory : WebApplicationFactory<Program>
{
    readonly SqliteConnection _connection = new("DataSource=:memory:");
    public int WritesPerMinute { get; init; } = 1000;
    /// <summary>Only for the test that shows why the app turns claim mapping off.</summary>
    public bool MapInboundClaims { get; init; }

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        _connection.Open();
        builder.UseEnvironment("Production");
        // UseSetting (not ConfigureAppConfiguration): Program reads configuration before Build(),
        // and only host settings are visible that early with the minimal hosting model.
        builder.UseSetting("Entra:TenantId", Ids.Tenant);
        builder.UseSetting("Entra:ClientId", Ids.ApiClient);
        builder.UseSetting("ConnectionStrings:Sql", "Server=tcp:sql-unused.invalid,1433;Database=pr;Authentication=Active Directory Default;Encrypt=True");
        builder.UseSetting("RateLimit:WritesPerMinute", WritesPerMinute.ToString());
        builder.ConfigureServices(services =>
        {
            services.RemoveAll<DbContextOptions<AppDbContext>>();
            services.RemoveAll<IDbContextOptionsConfiguration<AppDbContext>>();
            services.AddDbContext<AppDbContext>(o => o.UseSqlite(_connection));

            services.PostConfigure<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme, o =>
            {
                var cfg = new OpenIdConnectConfiguration();
                cfg.SigningKeys.Add(TestTokens.SigningKey);
                o.Configuration = cfg;
                o.ConfigurationManager = new StaticConfigurationManager<OpenIdConnectConfiguration>(cfg);
                if (MapInboundClaims)
                {
                    o.MapInboundClaims = true;
                    o.TokenHandlers.Clear();
                    o.TokenHandlers.Add(new JsonWebTokenHandler { MapInboundClaims = true });
                }
            });
        });
    }

    public HttpClient ClientFor(TestTokens.Options? who)
    {
        var client = CreateClient();
        if (who is not null)
            client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", TestTokens.Create(who));
        return client;
    }

    /// <summary>Each factory owns one in-memory database; call once before the first request.</summary>
    public ApiFactory Start()
    {
        using var scope = Services.CreateScope();
        scope.ServiceProvider.GetRequiredService<AppDbContext>().Database.EnsureCreated();
        return this;
    }

    protected override void Dispose(bool disposing)
    {
        base.Dispose(disposing);
        if (disposing) _connection.Dispose();
    }
}
