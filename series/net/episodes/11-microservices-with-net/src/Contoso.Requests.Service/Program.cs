using Contoso.Requests.Service.Budget;
using Contoso.Requests.Service.Data;
using Contoso.Requests.Service.Requests;
using Contoso.ServiceDefaults;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

builder.AddServiceDefaults(o =>
{
    // The defaults (30 s total, 3 retries 2 s apart, breaker after 100 calls) suit nobody on a laptop. Tuned, from configuration.
    var r = builder.Configuration.GetSection("Resilience");
    o.Retry.MaxRetryAttempts = r.GetValue("MaxRetries", 3);
    o.Retry.Delay = TimeSpan.FromMilliseconds(r.GetValue("RetryDelayMs", 300));
    o.Retry.UseJitter = false;
    o.AttemptTimeout.Timeout = TimeSpan.FromSeconds(r.GetValue("AttemptTimeoutSeconds", 2));
    o.TotalRequestTimeout.Timeout = TimeSpan.FromSeconds(r.GetValue("TotalTimeoutSeconds", 10));
    o.CircuitBreaker.SamplingDuration = TimeSpan.FromSeconds(r.GetValue("AttemptTimeoutSeconds", 2) * 5);
    o.CircuitBreaker.MinimumThroughput = r.GetValue("BreakerMinimumThroughput", 5);
    o.CircuitBreaker.BreakDuration = TimeSpan.FromSeconds(r.GetValue("BreakDurationSeconds", 15));
});

builder.Services.AddProblemDetails();
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddDbContext<RequestsDb>(o => o.UseSqlite(builder.Configuration.GetConnectionString("Requests")));
builder.Services.AddHttpClient<BudgetClient>(c => c.BaseAddress = new Uri("http://budget"));   // a name, not an address
builder.Services.AddSingleton<BudgetRechecker>();
builder.Services.AddHostedService<BudgetRecheckService>();

// Ready = the database answers. The Budget service is deliberately NOT part of it: Requests still works when Budget is down.
builder.Services.AddHealthChecks().AddDbContextCheck<RequestsDb>();

var app = builder.Build();

using (var scope = app.Services.CreateScope())
    scope.ServiceProvider.GetRequiredService<RequestsDb>().Database.EnsureCreated();

app.UseExceptionHandler();
app.MapDefaultEndpoints();
app.MapRequests();
app.Run();

public sealed class RequestsServiceMarker;
