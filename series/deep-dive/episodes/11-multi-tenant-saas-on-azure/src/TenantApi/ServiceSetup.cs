using System.Threading.RateLimiting;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using TenantApi.Data;
using TenantApi.Endpoints;
using TenantApi.Tenancy;

namespace TenantApi;

public sealed class EntraOptions
{
    public string Instance { get; set; } = "https://login.microsoftonline.com";
    /// <summary>Client ID of the multitenant API registration (the token audience for v2.0 tokens).</summary>
    public string ClientId { get; set; } = "";
    /// <summary>The provider's own tenant: the only one whose Platform.Admin role counts.</summary>
    public string HomeTenantId { get; set; } = "";
    public string RequiredScope { get; set; } = "Requests.ReadWrite";

    public void Validate()
    {
        if (!Guid.TryParse(ClientId, out _)) throw new InvalidOperationException("Entra:ClientId must be the API app registration's client ID.");
        if (!Guid.TryParse(HomeTenantId, out _)) throw new InvalidOperationException("Entra:HomeTenantId must be the provider tenant GUID.");
        if (string.IsNullOrWhiteSpace(RequiredScope) || RequiredScope.Contains(' ')) throw new InvalidOperationException("Entra:RequiredScope must be one scope name.");
    }
}

public static class ServiceSetup
{
    public static IServiceCollection AddTenantApi(this IServiceCollection services, IConfiguration config, IHostEnvironment env)
    {
        var entra = config.GetSection("Entra").Get<EntraOptions>() ?? new EntraOptions();
        entra.Validate();

        var catalog = new PlanCatalog();
        foreach (var (name, limits) in config.GetSection("Plans").Get<Dictionary<string, PlanLimits>>() ?? []) catalog.Plans[name] = limits;
        services.AddSingleton(catalog);

        services.AddMemoryCache();
        services.AddSingleton<ITenantDirectory, TenantDirectory>();
        services.AddScoped<TenantContext>();
        services.AddSingleton(TimeProvider.System);
        services.AddProblemDetails();

        services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme).AddJwtBearer();
        services.AddOptions<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme)
            .Configure<ITenantDirectory>((o, directory) =>
            {
                // Keys and metadata are shared by all tenants: the "organizations" authority (work and school accounts only).
                o.Authority = $"{entra.Instance.TrimEnd('/')}/organizations/v2.0";
                o.MapInboundClaims = false;   // keep "scp", "roles", "tid" as they are
                o.TokenValidationParameters = new TokenValidationParameters
                {
                    ValidateIssuer = true,
                    IssuerValidator = (issuer, token, _) => TenantIssuer.Validate(issuer, token, entra.Instance, Guid.Parse(entra.HomeTenantId), directory),
                    ValidateAudience = true,
                    ValidAudience = entra.ClientId,   // v2.0 tokens: the API's client ID
                    ValidateLifetime = true,
                    ValidateIssuerSigningKey = true,
                    RequireSignedTokens = true,
                    ClockSkew = TimeSpan.FromMinutes(2),
                    NameClaimType = "name",
                    RoleClaimType = "roles",
                };
            });
        services.AddAuthorization(o => o.AddTenantPolicies(entra.RequiredScope, Guid.Parse(entra.HomeTenantId)));

        var connectionString = config.GetConnectionString("Sql") ?? throw new InvalidOperationException("ConnectionStrings:Sql is missing.");
        services.AddDbContext<AppDbContext>(o => o
            .UseSqlServer(connectionString, sql => sql.EnableRetryOnFailure())
            .AddInterceptors(TenantSessionContextInterceptor.Shared));

        services.AddRateLimiter(o =>
        {
            o.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
            // One bucket per TENANT (tid), sized by the tenant's plan: users of one customer share it,
            // and a busy customer cannot use up another customer's calls.
            o.AddPolicy(RequestEndpoints.RateLimitPolicy, http =>
            {
                var tenant = http.RequestServices.GetRequiredService<TenantContext>();
                var plan = tenant.Info?.Plan ?? "starter";
                return RateLimitPartition.GetFixedWindowLimiter(tenant.TenantId.ToString("D"),
                    _ => new FixedWindowRateLimiterOptions { PermitLimit = catalog.For(plan).RequestsPerMinute, Window = TimeSpan.FromMinutes(1), QueueLimit = 0 });
            });
        });

        services.AddHealthChecks();
        return services;
    }

    public static WebApplication UseTenantApi(this WebApplication app)
    {
        app.UseExceptionHandler();
        app.UseStatusCodePages();
        if (!app.Environment.IsDevelopment()) app.UseHsts();
        app.Use(async (http, next) =>
        {
            http.Response.Headers.XContentTypeOptions = "nosniff";
            http.Response.Headers.CacheControl = "no-store";
            await next();
        });

        app.UseAuthentication();
        app.Use(async (http, next) =>   // tenant context: from the validated token, nowhere else
        {
            if (http.User.Identity?.IsAuthenticated == true)
                http.RequestServices.GetRequiredService<TenantContext>().Resolve(http.User, http.RequestServices.GetRequiredService<ITenantDirectory>());
            await next();
        });
        app.UseAuthorization();
        app.UseRateLimiter();

        app.MapHealthChecks("/healthz").AllowAnonymous();
        app.MapRequestEndpoints();
        app.MapAdminEndpoints();
        return app;
    }
}
