using Microsoft.AspNetCore.Http.HttpResults;
using Microsoft.AspNetCore.OutputCaching;
using Microsoft.EntityFrameworkCore;
using ProjectRequests.Perf.Api.Caching;
using ProjectRequests.Perf.Api.Data;
using ProjectRequests.Perf.Api.Telemetry;

namespace ProjectRequests.Perf.Api.Requests;

public static class RequestEndpoints
{
    public const string ListPolicy = "requests-list";

    public static void MapRequestEndpoints(this IEndpointRouteBuilder app, bool enableSlow, bool listCache = true)
    {
        var group = app.MapGroup("/api");

        // HTTP-level cache: whole responses, per department/page, evicted by tag when a request is created.
        // Perf:ListCache=false switches it off, so a demo can measure the query on its own, then with the cache.
        var list = group.MapGet("/requests", List);
        if (listCache) list.CacheOutput(ListPolicy);
        group.MapGet("/summary", Summary);
        group.MapPost("/requests", Create);

        // The "before" version exists to be measured. Off unless Perf:EnableSlowEndpoint is true.
        if (enableSlow) group.MapGet("/slow/requests", Slow);
    }

    public static async Task<Ok<List<RequestDto>>> Slow(PerfDbContext db, string? department, int? take, CancellationToken ct) =>
        TypedResults.Ok(await RequestQueries.NPlusOneAsync(db, Normalize(department), Math.Clamp(take ?? 200, 1, 500), ct));

    public static async Task<Results<Ok<PagedResult<RequestDto>>, ValidationProblem>> List(
        PerfDbContext db, string? department, int? page, int? pageSize, CancellationToken ct)
    {
        var p = page ?? 1;
        var size = pageSize ?? 50;
        var errors = new Dictionary<string, string[]>();
        if (p < 1) errors["page"] = ["page must be 1 or more."];
        if (size is < 1 or > 100) errors["pageSize"] = ["pageSize must be between 1 and 100."];   // never return unbounded lists
        if (errors.Count > 0) return TypedResults.ValidationProblem(errors);

        var code = Normalize(department);
        var total = await RequestQueries.CountAsync(db, code, ct);
        var items = await RequestQueries.ProjectedAsync(db, code, (p - 1) * size, size, ct);
        return TypedResults.Ok(new PagedResult<RequestDto>(items, p, size, total));
    }

    public static async Task<Ok<SummaryDto>> Summary(SummaryService summary, CancellationToken ct) =>
        TypedResults.Ok(await summary.GetAsync(ct));

    public static async Task<Results<Created<RequestDto>, ValidationProblem>> Create(
        CreateRequest body, PerfDbContext db, IOutputCacheStore outputCache, SummaryService summary,
        RequestMetrics metrics, TimeProvider clock, CancellationToken ct)
    {
        var department = await db.Departments.SingleOrDefaultAsync(d => d.Code == body.DepartmentCode.ToUpperInvariant(), ct);
        var requester = await db.Requesters.FindAsync([body.RequesterId], ct);
        var errors = new Dictionary<string, string[]>();
        if (department is null) errors[nameof(body.DepartmentCode)] = ["Unknown department."];
        if (requester is null) errors[nameof(body.RequesterId)] = ["Unknown requester."];
        if (errors.Count > 0) return TypedResults.ValidationProblem(errors);

        var entity = new ProjectRequest
        {
            Title = body.Title, Budget = body.Budget, Department = department!, Requester = requester!,
            Priority = body.Budget >= 50_000 ? Priority.High : Priority.Standard,
            Status = RequestStatus.Submitted, CreatedAtUtc = clock.GetUtcNow().UtcDateTime,
        };
        db.Requests.Add(entity);
        await db.SaveChangesAsync(ct);

        // Writes invalidate both caches by tag; the next reads recompute.
        await outputCache.EvictByTagAsync(SummaryService.Tag, ct);
        await summary.InvalidateAsync(ct);
        metrics.RequestCreated();

        var dto = new RequestDto(entity.Id, entity.Title, entity.Budget, department!.Code, requester!.Name,
            entity.Priority, entity.Status, entity.CreatedAtUtc);
        return TypedResults.Created($"/api/requests/{entity.Id}", dto);
    }

    private static string? Normalize(string? department) =>
        string.IsNullOrWhiteSpace(department) ? null : department.Trim().ToUpperInvariant();
}
