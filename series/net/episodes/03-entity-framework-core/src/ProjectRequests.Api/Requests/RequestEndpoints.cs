using System.Linq.Expressions;
using Microsoft.AspNetCore.Http.HttpResults;
using Microsoft.EntityFrameworkCore;
using ProjectRequests.Api.Data;

namespace ProjectRequests.Api.Requests;

public static class RequestEndpoints
{
    public static RouteGroupBuilder MapRequestsApi(this IEndpointRouteBuilder app)
    {
        var group = app.MapGroup("/api/requests").WithTags("Project requests");

        group.MapGet("/", List).WithName("ListRequests");
        group.MapGet("/summary", Summary).WithName("RequestSummary");
        group.MapGet("/{id:int}", GetById).WithName("GetRequest");
        group.MapPost("/", Create).WithName("CreateRequest").ProducesValidationProblem();
        group.MapPut("/{id:int}/budget", UpdateBudget).WithName("UpdateBudget")
            .ProducesValidationProblem().ProducesProblem(StatusCodes.Status409Conflict);
        group.MapPost("/{id:int}/decision", Decide).WithName("DecideRequest")
            .ProducesValidationProblem().ProducesProblem(StatusCodes.Status409Conflict);

        return group;
    }

    /// <summary>
    /// One projection for every read. EF Core translates it to a single SELECT with a JOIN to Departments,
    /// reads only these columns, and tracks nothing (the result isn't an entity type).
    /// </summary>
    public static readonly Expression<Func<ProjectRequest, RequestDto>> ToDto = r => new RequestDto(
        r.Id, r.Title, r.Budget, r.Department.Code, r.RequestedBy, r.Justification,
        r.Priority, r.Status, r.CreatedAtUtc, r.DecidedBy, r.DecidedAtUtc, r.Version);

    private static readonly Func<ProjectRequest, RequestDto> AsDto = ToDto.Compile();   // same mapping, in memory

    public static async Task<Ok<List<RequestDto>>> List(
        RequestsDbContext db, Priority? priority, string? department, CancellationToken ct)
    {
        var query = db.Requests.AsQueryable();
        if (priority is not null)
            query = query.Where(r => r.Priority == priority);
        if (!string.IsNullOrWhiteSpace(department))
        {
            var code = department.Trim().ToUpperInvariant();   // SQLite compares case-sensitively, SQL Server doesn't
            query = query.Where(r => r.Department.Code == code);
        }

        return TypedResults.Ok(await query.OrderBy(r => r.Id).Select(ToDto).ToListAsync(ct));
    }

    public static async Task<Results<Ok<RequestDto>, NotFound>> GetById(int id, RequestsDbContext db, CancellationToken ct) =>
        await db.Requests.Where(r => r.Id == id).Select(ToDto).FirstOrDefaultAsync(ct) is { } dto
            ? TypedResults.Ok(dto)
            : TypedResults.NotFound();

    /// <summary>Totals per department, computed by the database (correlated COUNT and SUM).</summary>
    public static async Task<Ok<List<DepartmentSummary>>> Summary(RequestsDbContext db, CancellationToken ct) =>
        TypedResults.Ok(await db.Departments
            .OrderBy(d => d.Code)
            .Select(d => new DepartmentSummary(
                d.Code,
                d.Requests.Count,
                d.Requests.Sum(r => r.Budget),
                d.Requests.Where(r => r.Status == RequestStatus.Approved).Sum(r => r.Budget)))
            .ToListAsync(ct));

    public static async Task<Results<Created<RequestDto>, ValidationProblem>> Create(
        CreateProjectRequest input, RequestsDbContext db, TimeProvider clock, CancellationToken ct)
    {
        var code = input.DepartmentCode.Trim().ToUpperInvariant();
        var department = await db.Departments.SingleOrDefaultAsync(d => d.Code == code, ct);
        if (department is null)
            return TypedResults.ValidationProblem(new Dictionary<string, string[]>
            {
                [nameof(CreateProjectRequest.DepartmentCode)] = [$"Unknown department '{input.DepartmentCode}'."],
            });

        var entity = new ProjectRequest
        {
            Title = input.Title.Trim(),
            Budget = input.Budget,
            RequestedBy = input.RequestedBy.Trim().ToLowerInvariant(),
            Justification = string.IsNullOrWhiteSpace(input.Justification) ? null : input.Justification.Trim(),
            Priority = PriorityRules.Classify(input.Budget),
            Status = RequestStatus.Submitted,
            CreatedAtUtc = clock.GetUtcNow().UtcDateTime,
            Department = department,
        };
        entity.Touch();

        db.Requests.Add(entity);
        await db.SaveChangesAsync(ct);                          // INSERT ... RETURNING "Id"

        return TypedResults.Created($"/api/requests/{entity.Id}", AsDto(entity));
    }

    public static async Task<Results<Ok<RequestDto>, NotFound, ProblemHttpResult>> UpdateBudget(
        int id, UpdateBudgetRequest input, RequestsDbContext db, CancellationToken ct)
    {
        var entity = await db.Requests.Include(r => r.Department).SingleOrDefaultAsync(r => r.Id == id, ct);
        if (entity is null)
            return TypedResults.NotFound();
        if (entity.Status != RequestStatus.Submitted)
            return AlreadyDecided(entity);

        entity.Budget = input.Budget;
        entity.Priority = PriorityRules.Classify(input.Budget);
        entity.Justification = string.IsNullOrWhiteSpace(input.Justification) ? null : input.Justification.Trim();

        return await SaveWithVersionAsync(db, entity, input.Version!.Value, ct);
    }

    public static async Task<Results<Ok<RequestDto>, NotFound, ProblemHttpResult>> Decide(
        int id, DecisionRequest decision, RequestsDbContext db, TimeProvider clock, CancellationToken ct)
    {
        var entity = await db.Requests.Include(r => r.Department).SingleOrDefaultAsync(r => r.Id == id, ct);
        if (entity is null)
            return TypedResults.NotFound();
        if (entity.Status != RequestStatus.Submitted)
            return AlreadyDecided(entity);

        var decidedBy = decision.DecidedBy.Trim().ToLowerInvariant();
        if (decidedBy == entity.RequestedBy)
            return TypedResults.Problem(title: "You can't decide your own request.", statusCode: StatusCodes.Status409Conflict);

        entity.Status = decision.Approve == true ? RequestStatus.Approved : RequestStatus.Rejected;
        entity.DecidedBy = decidedBy;
        entity.DecidedAtUtc = clock.GetUtcNow().UtcDateTime;

        return await SaveWithVersionAsync(db, entity, decision.Version!.Value, ct);
    }

    /// <summary>
    /// Optimistic concurrency across HTTP requests: EF Core compares the database row with the version the
    /// CLIENT read (not the one we just loaded), so "approve what you saw" holds even if the row changed
    /// a second ago, between our SELECT and our UPDATE.
    /// </summary>
    private static async Task<Results<Ok<RequestDto>, NotFound, ProblemHttpResult>> SaveWithVersionAsync(
        RequestsDbContext db, ProjectRequest entity, Guid clientVersion, CancellationToken ct)
    {
        db.Entry(entity).Property(r => r.Version).OriginalValue = clientVersion;
        entity.Touch();

        try
        {
            await db.SaveChangesAsync(ct);                      // UPDATE ... WHERE "Id" = @id AND "Version" = @clientVersion
            return TypedResults.Ok(AsDto(entity));
        }
        catch (DbUpdateConcurrencyException)
        {
            return TypedResults.Problem(
                title: "The request changed since you read it.",
                detail: "Read it again (GET) and retry with the new version.",
                statusCode: StatusCodes.Status409Conflict);
        }
    }

    private static ProblemHttpResult AlreadyDecided(ProjectRequest entity) =>
        TypedResults.Problem(
            title: "Request already decided.",
            detail: $"Request {entity.Id} is {entity.Status}.",
            statusCode: StatusCodes.Status409Conflict);
}
