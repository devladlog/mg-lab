using System.ComponentModel.DataAnnotations;
using System.Diagnostics;
using Contoso.Requests.Service.Budget;
using Contoso.Requests.Service.Data;
using Contoso.ServiceDefaults;
using Microsoft.EntityFrameworkCore;

namespace Contoso.Requests.Service.Requests;

public sealed class CreateRequestInput
{
    [Required, StringLength(100, MinimumLength = 3)]
    public string Title { get; set; } = "";

    [Required, StringLength(8)]
    public string DepartmentCode { get; set; } = "";

    [Range(typeof(decimal), "1", "10000000")]
    public decimal Amount { get; set; }

    [Required, EmailAddress, StringLength(254)]
    public string RequestedBy { get; set; } = "";
}

public sealed record RequestDto(int Id, string Title, string Department, decimal Amount, string RequestedBy,
    string BudgetState, Guid IdempotencyKey, string? TraceId, DateTime CreatedAtUtc)
{
    public static RequestDto From(ProjectRequest r) =>
        new(r.Id, r.Title, r.Department, r.Amount, r.RequestedBy, r.BudgetState.ToString(), r.IdempotencyKey, r.TraceId, r.CreatedAtUtc);
}

public static class RequestEndpoints
{
    public static void MapRequests(this IEndpointRouteBuilder app)
    {
        var group = app.MapGroup("/api/requests");
        group.MapGet("/", async (RequestsDb db, CancellationToken ct) =>
            (await db.Requests.AsNoTracking().OrderBy(r => r.Id).ToListAsync(ct)).Select(RequestDto.From));

        group.MapGet("/{id:int}", async (int id, RequestsDb db, CancellationToken ct) =>
            await db.Requests.AsNoTracking().FirstOrDefaultAsync(r => r.Id == id, ct) is { } r
                ? Results.Ok(RequestDto.From(r))
                : Results.Problem($"Request {id} not found.", statusCode: StatusCodes.Status404NotFound));

        group.MapPost("/", Create);
    }

    private static async Task<IResult> Create(
        CreateRequestInput input, HttpRequest http, HttpResponse response, RequestsDb db, BudgetClient budget,
        TimeProvider clock, CancellationToken ct)
    {
        var errors = new List<ValidationResult>();
        if (!Validator.TryValidateObject(input, new ValidationContext(input), errors, validateAllProperties: true))
            return Results.ValidationProblem(errors.ToDictionary(e => e.MemberNames.FirstOrDefault() ?? "", e => new[] { e.ErrorMessage ?? "invalid" }));

        // The caller's key (if any) identifies this request end to end: here, and in the Budget service.
        Guid key;
        if (http.Headers.TryGetValue(Idempotency.Header, out var header))
        {
            if (!Guid.TryParse(header, out key))
                return Results.Problem("Idempotency-Key must be a GUID.", statusCode: StatusCodes.Status400BadRequest);
            if (await db.Requests.AsNoTracking().FirstOrDefaultAsync(r => r.IdempotencyKey == key, ct) is { } seen)
            {
                response.Headers["Idempotent-Replayed"] = "true";
                return Results.Ok(RequestDto.From(seen));
            }
        }
        else key = Guid.NewGuid();

        // Save first, as Pending, THEN ask the Budget service: if anything fails from here on, the request exists and the
        // re-check worker finishes the job. (The other order would lose requests whenever the Budget service is down.)
        var request = new ProjectRequest
        {
            Title = input.Title.Trim(), Department = input.DepartmentCode.Trim().ToUpperInvariant(), Amount = input.Amount,
            RequestedBy = input.RequestedBy.Trim(), IdempotencyKey = key, BudgetState = BudgetState.Pending,
            TraceId = Activity.Current?.TraceId.ToString(), CreatedAtUtc = clock.GetUtcNow().UtcDateTime,
        };
        db.Requests.Add(request);
        try { await db.SaveChangesAsync(ct); }
        catch (DbUpdateException)   // two parallel calls with the same key: the unique index let only one in
        {
            db.ChangeTracker.Clear();
            var winner = await db.Requests.AsNoTracking().FirstAsync(r => r.IdempotencyKey == key, ct);
            response.Headers["Idempotent-Replayed"] = "true";
            return Results.Ok(RequestDto.From(winner));
        }

        var result = await budget.ReserveAsync(request.Department, request.Amount, $"request-{request.Id}", key, ct);
        BudgetRechecker.Apply(request, result);
        await db.SaveChangesAsync(ct);

        var dto = RequestDto.From(request);
        return request.BudgetState == BudgetState.Pending
            ? Results.Accepted($"/api/requests/{request.Id}", dto)   // 202: we have it, the budget check is not done
            : Results.Created($"/api/requests/{request.Id}", dto);
    }
}
