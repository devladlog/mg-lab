using System.Threading.RateLimiting;
using Microsoft.EntityFrameworkCore;
using PurchaseRequests.Api.Data;
using PurchaseRequests.Api.Domain;
using PurchaseRequests.Api.Endpoints;
using PurchaseRequests.Api.Security;

namespace PurchaseRequests.Api;

public static class ServiceSetup
{
    public static IServiceCollection AddPurchaseRequestsApi(this IServiceCollection services, IConfiguration config, IHostEnvironment env)
    {
        var entra = config.GetSection("Entra").Get<EntraOptions>() ?? new EntraOptions();
        services.AddEntraJwtBearer(entra);
        services.AddAuthorization(o => o.AddPurchaseRequestPolicies(entra.RequiredScope));

        services.Configure<ApprovalPolicy>(config.GetSection("Approval"));
        services.AddSingleton(TimeProvider.System);
        services.AddProblemDetails();   // RFC 9457 problem+json, no stack traces

        var connectionString = config.GetConnectionString("Sql");
        SqlConnectionGuard.Validate(connectionString, env.IsDevelopment());
        services.AddDbContext<AppDbContext>(o => o.UseSqlServer(connectionString, sql => sql.EnableRetryOnFailure()));

        var writesPerMinute = config.GetValue("RateLimit:WritesPerMinute", 20);
        services.AddRateLimiter(o =>
        {
            o.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
            // One bucket per signed-in user (oid), so one noisy client can't starve everyone else.
            o.AddPolicy(RequestEndpoints.WritePolicy, http => RateLimitPartition.GetFixedWindowLimiter(
                http.User.FindFirst("oid")?.Value ?? "anonymous",
                _ => new FixedWindowRateLimiterOptions { PermitLimit = writesPerMinute, Window = TimeSpan.FromMinutes(1), QueueLimit = 0 }));
        });

        services.AddHealthChecks();
        return services;
    }

    public static WebApplication UsePurchaseRequestsApi(this WebApplication app)
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
        app.UseAuthorization();
        app.UseRateLimiter();

        app.MapHealthChecks("/healthz").AllowAnonymous();
        app.MapRequestEndpoints();
        return app;
    }
}
