using System.Text.Json.Serialization;
using ProjectRequests.Api.Data;
using ProjectRequests.Api.Requests;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddOpenApi();
builder.Services.AddValidation();              // .NET 10: DataAnnotations validation for Minimal APIs
builder.Services.AddProblemDetails();
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddRequestsDatabase(builder.Configuration);   // EF Core: SQLite locally, Azure SQL in Azure
builder.Services.AddHealthChecks()
    .AddDbContextCheck<RequestsDbContext>();   // /healthz is Unhealthy if the database can't be reached
builder.Services.ConfigureHttpJsonOptions(o =>
    o.SerializerOptions.Converters.Add(new JsonStringEnumConverter()));

var app = builder.Build();

app.UseExceptionHandler();
app.UseStatusCodePages();

if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
}

app.MapHealthChecks("/healthz");
app.MapRequestsApi();

await app.MigrateIfConfiguredAsync();          // tests only; Azure gets a reviewed SQL script
app.Run();
