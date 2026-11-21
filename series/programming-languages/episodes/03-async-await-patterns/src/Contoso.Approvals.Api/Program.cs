using System.Runtime.CompilerServices;
using Contoso.Approvals.Api;

var builder = WebApplication.CreateBuilder(args);
var options = builder.Configuration.GetSection("Api").Get<ApiOptions>() ?? new ApiOptions();
builder.Services.AddSingleton(options);
builder.Services.AddSingleton<CallStats>();

var app = builder.Build();

// Streams the pending requests one by one (an IAsyncEnumerable is written as a JSON array as items arrive).
app.MapGet("/requests", (CancellationToken ct) => StreamRequests(ct));

// A CancellationToken parameter in a minimal API handler is bound to HttpContext.RequestAborted.
app.MapGet("/budget/{costCenter}", async (string costCenter, CallStats stats, CancellationToken ct) =>
{
    if (FinanceData.Budget(costCenter) is not { } budget) return Results.NotFound();
    if (stats.ShouldFail(costCenter))
    {
        stats.Failed($"budget {costCenter}");
        return Results.StatusCode(StatusCodes.Status503ServiceUnavailable);
    }
    return Results.Ok(await stats.TrackAsync($"budget {costCenter}", () => budget, ct));
});

app.MapGet("/approver/{department}", async (string department, CallStats stats, CancellationToken ct) =>
    FinanceData.Approver(department) is { } approver
        ? Results.Ok(await stats.TrackAsync($"approver {department}", () => approver, ct))
        : Results.NotFound());

app.MapGet("/stats", (CallStats stats) => stats.Snapshot());
app.MapPost("/stats/reset", (CallStats stats) =>
{
    stats.Reset();
    return Results.NoContent();
});

app.Run();

static async IAsyncEnumerable<ProjectRequestDto> StreamRequests([EnumeratorCancellation] CancellationToken ct)
{
    foreach (var request in FinanceData.Requests)
    {
        await Task.Delay(20, ct);
        yield return request;
    }
}

/// <summary>Makes the entry point visible to WebApplicationFactory in the integration tests.</summary>
public partial class Program;
