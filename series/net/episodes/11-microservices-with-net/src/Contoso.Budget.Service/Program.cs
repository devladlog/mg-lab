using System.ComponentModel.DataAnnotations;
using Contoso.Budget.Service;
using Contoso.ServiceDefaults;

var builder = WebApplication.CreateBuilder(args);
builder.AddServiceDefaults();
builder.Services.AddProblemDetails();
builder.Services.Configure<FaultOptions>(builder.Configuration.GetSection("Faults"));
builder.Services.AddSingleton<FaultInjector>();
builder.Services.AddSingleton(sp => new BudgetLedger(
    builder.Configuration.GetSection("Budget:Limits").GetChildren().ToDictionary(c => c.Key, c => decimal.Parse(c.Value!, System.Globalization.CultureInfo.InvariantCulture))));

var app = builder.Build();
app.UseExceptionHandler();
app.MapDefaultEndpoints();

app.MapGet("/api/budgets", (BudgetLedger ledger) => ledger.All());

app.MapGet("/api/budgets/{department}", (string department, BudgetLedger ledger) =>
    ledger.Status(department) is { } status
        ? Results.Ok(status)
        : Results.Problem($"No budget for department '{department}'.", statusCode: StatusCodes.Status404NotFound));

app.MapPost("/api/budgets/{department}/reservations", (
    string department,
    ReserveRequest body,
    HttpRequest http,
    BudgetLedger ledger,
    FaultInjector faults,
    ILogger<Program> log) =>
{
    if (!Guid.TryParse(http.Headers[Idempotency.Header], out var key))
        return Results.Problem("Send an Idempotency-Key header with a GUID: a reservation can be retried only with one.",
            statusCode: StatusCodes.Status400BadRequest);

    var errors = new List<ValidationResult>();
    if (!Validator.TryValidateObject(body, new ValidationContext(body), errors, validateAllProperties: true))
        return Results.ValidationProblem(errors.ToDictionary(e => e.MemberNames.FirstOrDefault() ?? "", e => new[] { e.ErrorMessage ?? "invalid" }));

    var fail = faults.ShouldFail(key, out var afterCommit);
    if (fail && !afterCommit)
    {
        log.LogWarning("Fault injection: failing attempt {Attempt} for key {Key} before doing anything", faults.AttemptsSeen(key), key);
        return Results.StatusCode(StatusCodes.Status503ServiceUnavailable);
    }

    var (outcome, reservation) = ledger.Reserve(key, department, body.Amount, body.Reference);
    log.LogInformation("Reserve {Amount} for {Department}: {Outcome}", body.Amount, department, outcome);

    if (fail && afterCommit)
    {
        log.LogWarning("Fault injection: reservation made ({Outcome}), answer for attempt {Attempt} is lost", outcome, faults.AttemptsSeen(key));
        return Results.StatusCode(StatusCodes.Status503ServiceUnavailable);
    }

    return outcome switch
    {
        ReserveOutcome.Created => Results.Created($"/api/budgets/{department}", reservation),
        ReserveOutcome.Replayed => Results.Ok(reservation),   // same key, same request: the first answer again
        ReserveOutcome.OverBudget => Results.Problem($"Department {department.ToUpperInvariant()} has less than {body.Amount:N2} left.",
            statusCode: StatusCodes.Status422UnprocessableEntity, title: "Over budget"),
        ReserveOutcome.KeyReusedForDifferentRequest => Results.Problem("That Idempotency-Key was already used for a different reservation.",
            statusCode: StatusCodes.Status409Conflict),
        _ => Results.Problem($"No budget for department '{department}'.", statusCode: StatusCodes.Status404NotFound),
    };
});

app.Run();

public sealed class ReserveRequest
{
    [Range(typeof(decimal), "0.01", "10000000")]
    public decimal Amount { get; set; }

    [Required, StringLength(100)]
    public string Reference { get; set; } = "";
}

/// <summary>Lets the test project start this service with WebApplicationFactory without a public Program type (every service has one).</summary>
public sealed class BudgetServiceMarker;
