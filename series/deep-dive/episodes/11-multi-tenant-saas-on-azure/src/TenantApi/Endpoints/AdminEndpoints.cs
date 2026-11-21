using Microsoft.EntityFrameworkCore;
using TenantApi.Data;
using TenantApi.Tenancy;

namespace TenantApi.Endpoints;

public sealed record TenantUpsert(string? Name, string? Plan, string? Status);

/// <summary>Onboarding: the provider's own staff register customer tenants in the catalog.</summary>
public static class AdminEndpoints
{
    public static void MapAdminEndpoints(this IEndpointRouteBuilder app)
    {
        var g = app.MapGroup("/admin/tenants").RequireAuthorization(Policies.PlatformAdmin);

        g.MapGet("/", async (AppDbContext db, CancellationToken ct) =>
            Results.Ok(await db.Tenants.AsNoTracking().OrderBy(t => t.Name).ToListAsync(ct)));

        g.MapPut("/{tenantId:guid}", async (Guid tenantId, TenantUpsert body, AppDbContext db, PlanCatalog plans, ITenantDirectory dir, TimeProvider clock, CancellationToken ct) =>
        {
            var errors = new Dictionary<string, string[]>();
            if (string.IsNullOrWhiteSpace(body.Name) || body.Name.Length > 200) errors["name"] = ["Name is required, up to 200 characters."];
            var plan = (body.Plan ?? "starter").ToLowerInvariant();
            if (!plans.IsKnown(plan)) errors["plan"] = [$"Unknown plan. Known: {string.Join(", ", plans.Plans.Keys)}."];
            var status = (body.Status ?? TenantStatus.Active).ToLowerInvariant();
            if (!TenantStatus.IsValid(status)) errors["status"] = ["Status must be active or suspended."];
            if (tenantId == Guid.Empty) errors["tenantId"] = ["Tenant ID must not be empty."];
            if (errors.Count > 0) return Results.ValidationProblem(errors);

            var row = await db.Tenants.FindAsync([tenantId], ct);
            var created = row is null;
            if (created) db.Tenants.Add(row = new Tenant { TenantId = tenantId, CreatedUtc = clock.GetUtcNow().UtcDateTime });
            row!.Name = body.Name!.Trim();
            row.Plan = plan;
            row.Status = status;
            await db.SaveChangesAsync(ct);
            dir.Forget(tenantId);
            return created ? Results.Created($"/admin/tenants/{tenantId}", row) : Results.Ok(row);
        });
    }
}
