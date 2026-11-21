using System.Text.Json.Serialization;
using ProjectRequests.Api.Data;
using ProjectRequests.Api.Diagnostics;
using ProjectRequests.Api.Notifications;
using ProjectRequests.Api.Requests;

var builder = WebApplication.CreateBuilder(args);

// Framework services
builder.Services.AddOpenApi();
builder.Services.AddValidation();
builder.Services.AddProblemDetails();
builder.Services.ConfigureHttpJsonOptions(o =>
    o.SerializerOptions.Converters.Add(new JsonStringEnumConverter()));

// Our services, one extension method per feature
builder.Services.AddSingleton(TimeProvider.System);                 // singleton: stateless, thread-safe
builder.Services.AddRequestsDatabase(builder.Configuration);        // DbContext: scoped (AddDbContext default)
builder.Services.AddNotifications(builder.Configuration);           // options, keyed channels, worker
builder.Services.AddLifetimeProbes();
builder.Services.AddHealthChecks().AddDbContextCheck<RequestsDbContext>();

var app = builder.Build();                                          // Development: ValidateScopes + ValidateOnBuild

app.UseExceptionHandler();
app.UseStatusCodePages();

if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
    app.MapLifetimeDiagnostics();                                   // GET /diagnostics/lifetimes
}

app.MapHealthChecks("/healthz");
app.MapRequestsApi();
app.MapDigestApi();

await app.MigrateIfConfiguredAsync();
app.Run();
