using Microsoft.AspNetCore.Http.HttpResults;

namespace ProjectRequests.Api.Requests;

public static class RequestEndpoints
{
    public static RouteGroupBuilder MapRequestsApi(this IEndpointRouteBuilder app)
    {
        var group = app.MapGroup("/api/requests")
            .WithTags("Project requests");

        group.MapGet("/", List).WithName("ListRequests");
        group.MapGet("/{id:int}", GetById).WithName("GetRequest");

        // Writes share one endpoint filter: read-only mode.
        var writes = group.MapGroup("")
            .AddEndpointFilter<ReadOnlyModeFilter>()
            .ProducesValidationProblem()                       // 400 from AddValidation
            .ProducesProblem(StatusCodes.Status503ServiceUnavailable);
        writes.MapPost("/", Create).WithName("CreateRequest");
        writes.MapPost("/{id:int}/decision", Decide).WithName("DecideRequest")
            .ProducesProblem(StatusCodes.Status409Conflict);   // ProblemHttpResult carries no status code

        return group;
    }

    public static Ok<IReadOnlyList<ProjectRequest>> List(IRequestStore store, Priority? priority) =>
        TypedResults.Ok(store.List(priority));

    public static Results<Ok<ProjectRequest>, NotFound> GetById(int id, IRequestStore store) =>
        store.Get(id) is { } item ? TypedResults.Ok(item) : TypedResults.NotFound();

    public static Created<ProjectRequest> Create(CreateProjectRequest input, IRequestStore store)
    {
        var item = store.Add(input);
        return TypedResults.Created($"/api/requests/{item.Id}", item);
    }

    public static Results<Ok<ProjectRequest>, NotFound, ProblemHttpResult> Decide(
        int id, DecisionRequest decision, IRequestStore store)
    {
        if (store.Get(id) is not { } current)
            return TypedResults.NotFound();

        if (current.Status != RequestStatus.Submitted)
            return TypedResults.Problem(
                title: "Request already decided.",
                detail: $"Request {id} is {current.Status}.",
                statusCode: StatusCodes.Status409Conflict);

        var decidedBy = decision.DecidedBy.Trim().ToLowerInvariant();
        if (decidedBy == current.RequestedBy)
            return TypedResults.Problem(
                title: "You can't decide your own request.",
                statusCode: StatusCodes.Status409Conflict);

        var updated = current with
        {
            Status = decision.Approve == true ? RequestStatus.Approved : RequestStatus.Rejected,
            DecidedBy = decidedBy,
        };

        return store.TryUpdate(updated, current)
            ? TypedResults.Ok(updated)
            : TypedResults.Problem(title: "Request changed, read it again.", statusCode: StatusCodes.Status409Conflict);
    }
}
