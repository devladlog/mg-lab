using System.Security.Claims;
using Microsoft.EntityFrameworkCore;
using TenantApi.Data;
using TenantApi.Tenancy;

namespace TenantApi.Endpoints;

public sealed record NewRequest(string? Title, decimal? Amount);

public static class RequestEndpoints
{
    public const string RateLimitPolicy = "per-tenant";

    public static void MapRequestEndpoints(this IEndpointRouteBuilder app)
    {
        var g = app.MapGroup("/")
            .RequireAuthorization(Policies.Tenant)
            .RequireRateLimiting(RateLimitPolicy)
            .AddEndpointFilter(RequireActiveTenant);

        g.MapGet("/me", (TenantContext t, PlanCatalog plans, ClaimsPrincipal user) =>
        {
            var limits = plans.For(t.Info!.Plan);
            return Results.Ok(new
            {
                tenantId = t.TenantId,
                tenant = t.Info.Name,
                plan = t.Info.Plan,
                limits.MaxRequests,
                limits.RequestsPerMinute,
                user = user.FindFirst("oid")?.Value,
            });
        });

        g.MapGet("/requests", async (AppDbContext db, CancellationToken ct) =>
            Results.Ok(await db.PurchaseRequests.AsNoTracking().OrderByDescending(p => p.CreatedUtc).ThenBy(p => p.Id).ToListAsync(ct)));

        g.MapGet("/requests/{id:guid}", async (Guid id, AppDbContext db, CancellationToken ct) =>
            await db.PurchaseRequests.AsNoTracking().FirstOrDefaultAsync(p => p.Id == id, ct) is { } found
                ? Results.Ok(found)
                : Results.NotFound());   // another tenant's id looks exactly like an id that does not exist

        g.MapPost("/requests", async (NewRequest body, AppDbContext db, TenantContext t, PlanCatalog plans, ClaimsPrincipal user, TimeProvider clock, CancellationToken ct) =>
        {
            var errors = new Dictionary<string, string[]>();
            if (string.IsNullOrWhiteSpace(body.Title) || body.Title.Length > 200) errors["title"] = ["Title is required, up to 200 characters."];
            if (body.Amount is null or <= 0 or > 1_000_000) errors["amount"] = ["Amount must be above 0 and at most 1,000,000."];
            if (errors.Count > 0) return Results.ValidationProblem(errors);

            // The query filter makes this count the current tenant's rows only.
            var limits = plans.For(t.Info!.Plan);
            if (await db.PurchaseRequests.CountAsync(ct) >= limits.MaxRequests)
                return Results.Problem(statusCode: 409, title: "Plan limit reached",
                    detail: $"The {t.Info.Plan} plan allows {limits.MaxRequests} purchase requests.", type: "https://contoso.example/problems/plan-limit");

            var row = new PurchaseRequest
            {
                Id = Guid.NewGuid(),
                Title = body.Title!.Trim(),
                Amount = body.Amount!.Value,
                CreatedBy = user.FindFirst("oid")?.Value ?? "",
                CreatedUtc = clock.GetUtcNow().UtcDateTime,
            };
            db.PurchaseRequests.Add(row);          // TenantId is stamped by the context, not taken from the caller
            await db.SaveChangesAsync(ct);
            return Results.Created($"/requests/{row.Id}", row);
        });
    }

    static async ValueTask<object?> RequireActiveTenant(EndpointFilterInvocationContext ctx, EndpointFilterDelegate next)
    {
        var t = ctx.HttpContext.RequestServices.GetRequiredService<TenantContext>();
        if (t.Info is null || !t.Info.IsActive)
            return Results.Problem(statusCode: 403, title: "Tenant not active",
                detail: "This organisation is not onboarded or has been suspended.", type: "https://contoso.example/problems/tenant-inactive");
        return await next(ctx);
    }
}
