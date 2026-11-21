using System.Text.Json.Serialization;
using ProjectRequests.Api.Requests;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddOpenApi();                 // OpenAPI 3.1 document, built in since .NET 9
builder.Services.AddValidation();              // .NET 10: DataAnnotations validation for Minimal APIs
builder.Services.AddProblemDetails();          // RFC 9457 problem+json for errors
builder.Services.AddHealthChecks();
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddSingleton<IRequestStore, InMemoryRequestStore>();
builder.Services.ConfigureHttpJsonOptions(o =>
    o.SerializerOptions.Converters.Add(new JsonStringEnumConverter()));

var app = builder.Build();

app.UseExceptionHandler();                     // unhandled exceptions -> 500 problem+json, no stack trace
app.UseStatusCodePages();                      // empty 404/405 -> problem+json body

if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();                          // GET /openapi/v1.json (Development only)
}

app.MapHealthChecks("/healthz");
app.MapRequestsApi();

app.Run();
