using System.Text.Json.Serialization;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using PurchaseRequests.Api.Data;
using PurchaseRequests.Api.Domain;
using PurchaseRequests.Api.Security;

namespace PurchaseRequests.Api.Endpoints;

// Unknown JSON properties are an error, not silently ignored: a client can't slip in "requestedByOid" or "status".
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record SubmitRequest(string? Title, string? Justification, decimal Amount, string? Currency);

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record DecisionRequest(string? Outcome, string? Comment);

public sealed record RequestView(
    Guid Id, string Title, string Justification, decimal Amount, string Currency, string Status,
    string RequestedByName, DateTime CreatedAtUtc, string? DecidedByName, DateTime? DecidedAtUtc, string? DecisionComment)
{
    public static RequestView From(PurchaseRequest r) => new(
        r.Id, r.Title, r.Justification, r.Amount, r.Currency, r.Status.ToString(), r.RequestedByName,
        r.CreatedAtUtc, r.DecidedByName, r.DecidedAtUtc, r.DecisionComment);
}

public sealed record AuditView(string Action, string ActorOid, string Detail, DateTime AtUtc);

public static class RequestEndpoints
{
    public const string WritePolicy = "writes";

    public static void MapRequestEndpoints(this IEndpointRouteBuilder app)
    {
        var api = app.MapGroup("/api/requests");

        api.MapPost("/", Submit).RequireAuthorization(Policies.Submit).RequireRateLimiting(WritePolicy)
            .WithName("SubmitRequest");
        api.MapGet("/mine", Mine).RequireAuthorization(Policies.Read).WithName("ListMyRequests");
        api.MapGet("/pending", Pending).RequireAuthorization(Policies.Decide).WithName("ListPendingRequests");
        api.MapGet("/{id:guid}", GetOne).RequireAuthorization(Policies.Read).WithName("GetRequest");
        api.MapPost("/{id:guid}/decision", Decide).RequireAuthorization(Policies.Decide).RequireRateLimiting(WritePolicy)
            .WithName("DecideRequest");
        api.MapGet("/{id:guid}/audit", Audit).RequireAuthorization(Policies.Read).WithName("GetRequestAudit");
    }

    internal static Dictionary<string, string[]> Validate(SubmitRequest body, ApprovalPolicy policy)
    {
        var errors = new Dictionary<string, string[]>();
        var title = body.Title?.Trim() ?? "";
        var justification = body.Justification?.Trim() ?? "";
        if (title.Length is < 3 or > 120) errors["title"] = ["Title must be 3 to 120 characters."];
        if (justification.Length is < 10 or > 2000) errors["justification"] = ["Justification must be 10 to 2000 characters."];
        if (body.Amount <= 0) errors["amount"] = ["Amount must be greater than zero."];
        else if (body.Amount > policy.MaxAmount) errors["amount"] = [$"Amount can't be above {policy.MaxAmount:0} {policy.Currency}."];
        else if (decimal.Round(body.Amount, 2) != body.Amount) errors["amount"] = ["Amount can have at most two decimals."];
        if (!string.Equals(body.Currency, policy.Currency, StringComparison.Ordinal))
            errors["currency"] = [$"Currency must be {policy.Currency}."];
        return errors;
    }

    static async Task<IResult> Submit(SubmitRequest body, HttpContext http, AppDbContext db,
        IOptions<ApprovalPolicy> policy, TimeProvider clock)
    {
        var errors = Validate(body, policy.Value);
        if (errors.Count > 0) return Results.ValidationProblem(errors);

        var caller = Caller.From(http.User);
        var now = clock.GetUtcNow().UtcDateTime;
        var request = new PurchaseRequest
        {
            Id = Guid.CreateVersion7(),
            Title = body.Title!.Trim(),
            Justification = body.Justification!.Trim(),
            Amount = body.Amount,
            Currency = policy.Value.Currency,
            RequestedByOid = caller.Oid,          // from the token, never from the body
            RequestedByName = caller.Name,
            CreatedAtUtc = now,
        };
        db.PurchaseRequests.Add(request);
        db.AuditEntries.Add(NewAudit(request.Id, AuditActions.Submitted, caller, $"{request.Amount:0.00} {request.Currency}", now, http));
        await db.SaveChangesAsync();   // request + audit entry in one transaction
        return Results.Created($"/api/requests/{request.Id}", RequestView.From(request));
    }

    static async Task<IResult> Mine(HttpContext http, AppDbContext db)
    {
        var caller = Caller.From(http.User);
        var items = await db.PurchaseRequests.AsNoTracking()
            .Where(r => r.RequestedByOid == caller.Oid)
            .OrderByDescending(r => r.CreatedAtUtc).Take(100).ToListAsync();
        return Results.Ok(items.Select(RequestView.From));
    }

    static async Task<IResult> Pending(HttpContext http, AppDbContext db)
    {
        var caller = Caller.From(http.User);
        var items = await db.PurchaseRequests.AsNoTracking()
            .Where(r => r.Status == RequestStatus.Pending && r.RequestedByOid != caller.Oid)
            .OrderBy(r => r.CreatedAtUtc).Take(100).ToListAsync();
        return Results.Ok(items.Select(RequestView.From));
    }

    static async Task<IResult> GetOne(Guid id, HttpContext http, AppDbContext db)
    {
        var request = await db.PurchaseRequests.AsNoTracking().FirstOrDefaultAsync(r => r.Id == id);
        // Someone else's request answers 404, not 403: the API doesn't confirm that the ID exists.
        if (request is null || !ApprovalRules.CanRead(request, Caller.From(http.User))) return Results.NotFound();
        return Results.Ok(RequestView.From(request));
    }

    static async Task<IResult> Decide(Guid id, DecisionRequest body, HttpContext http, AppDbContext db,
        IOptions<ApprovalPolicy> policy, TimeProvider clock, ILoggerFactory loggers)
    {
        DecisionOutcome? parsed = body.Outcome switch
        {
            "Approve" => DecisionOutcome.Approve,
            "Reject" => DecisionOutcome.Reject,
            _ => null,                       // no numbers, no other casing
        };
        if (parsed is not { } outcome)
            return Results.ValidationProblem(new Dictionary<string, string[]> { ["outcome"] = ["Outcome must be Approve or Reject."] });
        var comment = body.Comment?.Trim();
        if (comment is { Length: > 500 })
            return Results.ValidationProblem(new Dictionary<string, string[]> { ["comment"] = ["Comment can be at most 500 characters."] });

        var request = await db.PurchaseRequests.FirstOrDefaultAsync(r => r.Id == id);
        if (request is null) return Results.NotFound();

        var caller = Caller.From(http.User);
        var now = clock.GetUtcNow().UtcDateTime;
        var rule = ApprovalRules.CanDecide(request, caller, outcome, policy.Value);
        if (!rule.Allowed)
        {
            if (rule.StatusCode == StatusCodes.Status403Forbidden)
            {
                // A refused decision is a security event: keep it in the audit trail and the logs (oid only).
                db.AuditEntries.Add(NewAudit(request.Id, AuditActions.DecisionDenied, caller, rule.Reason!, now, http));
                await db.SaveChangesAsync();
                loggers.CreateLogger("Decisions").LogWarning("Decision on {RequestId} denied for {Oid}: {Reason}", request.Id, caller.Oid, rule.Reason);
            }
            return Results.Problem(statusCode: rule.StatusCode, title: "Decision not allowed", detail: rule.Reason);
        }

        request.Status = outcome == DecisionOutcome.Approve ? RequestStatus.Approved : RequestStatus.Rejected;
        request.DecidedByOid = caller.Oid;
        request.DecidedByName = caller.Name;
        request.DecidedAtUtc = now;
        request.DecisionComment = comment;
        request.Version++;
        db.AuditEntries.Add(NewAudit(request.Id,
            outcome == DecisionOutcome.Approve ? AuditActions.Approved : AuditActions.Rejected, caller, comment ?? "", now, http));
        try
        {
            await db.SaveChangesAsync();
        }
        catch (DbUpdateConcurrencyException)
        {
            return Results.Problem(statusCode: StatusCodes.Status409Conflict, title: "Decision not allowed",
                detail: "Someone else decided on this request a moment ago. Refresh and check.");
        }
        return Results.Ok(RequestView.From(request));
    }

    static async Task<IResult> Audit(Guid id, HttpContext http, AppDbContext db)
    {
        var request = await db.PurchaseRequests.AsNoTracking().FirstOrDefaultAsync(r => r.Id == id);
        if (request is null || !ApprovalRules.CanRead(request, Caller.From(http.User))) return Results.NotFound();
        var entries = await db.AuditEntries.AsNoTracking().Where(a => a.RequestId == id).OrderBy(a => a.Id).ToListAsync();
        return Results.Ok(entries.Select(a => new AuditView(a.Action, a.ActorOid, a.Detail, a.AtUtc)));
    }

    static AuditEntry NewAudit(Guid requestId, string action, Caller caller, string detail, DateTime now, HttpContext http) => new()
    {
        RequestId = requestId,
        Action = action,
        ActorOid = caller.Oid,
        Detail = detail.Length > 400 ? detail[..400] : detail,
        AtUtc = now,
        CorrelationId = http.TraceIdentifier.Length > 64 ? http.TraceIdentifier[..64] : http.TraceIdentifier,
    };
}
