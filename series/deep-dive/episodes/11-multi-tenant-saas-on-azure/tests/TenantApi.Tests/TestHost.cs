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
using TenantApi.Data;
using TenantApi.Tenancy;

namespace TenantApi.Tests;

/// <summary>Fictional identifiers only.</summary>
public static class Ids
{
    public const string Home = "00000000-0000-0000-0000-000000000001";        // the provider's own tenant
    public const string Northwind = "00000000-0000-0000-0000-0000000000b1";   // business plan
    public const string AdventureWorks = "00000000-0000-0000-0000-0000000000b2"; // starter plan
    public const string Fabrikam = "00000000-0000-0000-0000-0000000000b3";    // suspended
    public const string NotOnboarded = "00000000-0000-0000-0000-0000000000b9";
    public const string ApiClient = "00000000-0000-0000-0000-0000000000a1";
    public const string Alex = "00000000-0000-0000-0000-00000000a1e0";
    public const string Riley = "00000000-0000-0000-0000-00000000a1e1";
    public const string Sam = "00000000-0000-0000-0000-00000000a1e2";
}

/// <summary>Real RS256 JWTs shaped like Entra v2.0 access tokens, signed by a key only the tests know.</summary>
public static class TestTokens
{
    public static readonly RsaSecurityKey SigningKey = new(RSA.Create(2048)) { KeyId = "test-key" };
    static readonly RsaSecurityKey OtherKey = new(RSA.Create(2048)) { KeyId = "test-key" };

    public sealed record Options
    {
        public string Tenant { get; init; } = Ids.Northwind;
        public string Oid { get; init; } = Ids.Alex;
        public string[] Roles { get; init; } = [];
        public string? Scope { get; init; } = "Requests.ReadWrite";
        public int Version { get; init; } = 2;
        public string? Audience { get; init; }
        /// <summary>Overrides the iss claim (e.g. a different tenant's issuer on a token whose tid is this tenant).</summary>
        public string? Issuer { get; init; }
        public bool WrongKey { get; init; }
    }

    public static string Create(Options o)
    {
        var issuer = o.Issuer ?? (o.Version == 2 ? $"https://login.microsoftonline.com/{o.Tenant}/v2.0" : $"https://sts.windows.net/{o.Tenant}/");
        var claims = new Dictionary<string, object> { ["oid"] = o.Oid, ["name"] = "Alex Demo", ["tid"] = o.Tenant, ["ver"] = o.Version == 2 ? "2.0" : "1.0" };
        if (o.Scope is not null) claims["scp"] = o.Scope;
        if (o.Roles.Length > 0) claims["roles"] = o.Roles;
        var now = DateTime.UtcNow.AddMinutes(-1);
        return new JsonWebTokenHandler().CreateToken(new SecurityTokenDescriptor
        {
            Issuer = issuer,
            Audience = o.Audience ?? Ids.ApiClient,
            Claims = claims,
            NotBefore = now,
            IssuedAt = now,
            Expires = now.AddMinutes(60),
            SigningCredentials = new SigningCredentials(o.WrongKey ? OtherKey : SigningKey, SecurityAlgorithms.RsaSha256),
        });
    }

    public static Options Northwind(string oid = Ids.Alex) => new() { Tenant = Ids.Northwind, Oid = oid };
    public static Options AdventureWorks(string oid = Ids.Alex) => new() { Tenant = Ids.AdventureWorks, Oid = oid };
    public static Options Admin => new() { Tenant = Ids.Home, Roles = ["Platform.Admin"], Scope = null };
}

/// <summary>
/// The real app with its real authentication, tenant resolution, authorization and rate limiting. Only the database
/// (SQLite in memory) and the source of signing keys change. Plan sizes are made small so limits can be reached in a test.
/// </summary>
public sealed class TenantApiFactory : WebApplicationFactory<Program>
{
    readonly SqliteConnection _connection = new("DataSource=:memory:");
    public int StarterMaxRequests { get; init; } = 3;
    public int StarterPerMinute { get; init; } = 100;
    public int BusinessPerMinute { get; init; } = 1000;

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        _connection.Open();
        builder.UseEnvironment("Production");
        builder.UseSetting("Entra:ClientId", Ids.ApiClient);
        builder.UseSetting("Entra:HomeTenantId", Ids.Home);
        builder.UseSetting("ConnectionStrings:Sql", "Server=tcp:sql-unused.invalid,1433;Database=t;Authentication=Active Directory Default;Encrypt=True");
        builder.UseSetting("Plans:starter:MaxRequests", StarterMaxRequests.ToString());
        builder.UseSetting("Plans:starter:RequestsPerMinute", StarterPerMinute.ToString());
        builder.UseSetting("Plans:business:MaxRequests", "1000");
        builder.UseSetting("Plans:business:RequestsPerMinute", BusinessPerMinute.ToString());
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
            });
        });
    }

    public HttpClient ClientFor(TestTokens.Options? who)
    {
        var client = CreateClient();
        if (who is not null) client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", TestTokens.Create(who));
        return client;
    }

    /// <summary>Creates the schema and the catalog: Northwind (business), Adventure Works (starter), Fabrikam (suspended).</summary>
    public TenantApiFactory Start()
    {
        using var scope = Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        db.Database.EnsureCreated();
        db.Tenants.AddRange(
            new Tenant { TenantId = Guid.Parse(Ids.Northwind), Name = "Northwind Traders", Plan = "business", CreatedUtc = DateTime.UtcNow },
            new Tenant { TenantId = Guid.Parse(Ids.AdventureWorks), Name = "Adventure Works", Plan = "starter", CreatedUtc = DateTime.UtcNow },
            new Tenant { TenantId = Guid.Parse(Ids.Fabrikam), Name = "Fabrikam", Plan = "starter", Status = TenantStatus.Suspended, CreatedUtc = DateTime.UtcNow });
        db.SaveChanges();
        return this;
    }

    /// <summary>Rows per tenant straight from the database, bypassing the filter (tests only).</summary>
    public Dictionary<Guid, int> RowCounts()
    {
        using var scope = Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        return db.PurchaseRequests.IgnoreQueryFilters().GroupBy(p => p.TenantId).ToDictionary(g => g.Key, g => g.Count());
    }

    protected override void Dispose(bool disposing)
    {
        base.Dispose(disposing);
        if (disposing) _connection.Dispose();
    }
}
