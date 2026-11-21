using System.Text.Json.Serialization;
using ProjectRequests.Api.Data;
using ProjectRequests.Api.Diagnostics;
using ProjectRequests.Api.Live;
using ProjectRequests.Api.Notifications;
using ProjectRequests.Api.Requests;
using ProjectRequests.Api.Rpc;

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

// Episode 6: the Blazor WebAssembly client calls this API from the browser, from another origin.
// Only the origins in Cors:AllowedOrigins may; nothing is allowed by default.
builder.Services.AddCors(o => o.AddDefaultPolicy(policy => policy
    .WithOrigins(builder.Configuration.GetSection("Cors:AllowedOrigins").Get<string[]>() ?? [])
    .WithMethods("GET", "POST", "PUT")
    .WithHeaders("Content-Type")));

// Episode 7: real-time updates. A SignalR hub at /hubs/requests, its own CORS policy, and IRequestEvents
// for the endpoints to push "created" / "updated" after every successful write.
builder.Services.AddLiveUpdates(builder.Configuration);

// Episode 8: gRPC next to REST, same DbContext, same rules. gRPC needs HTTP/2: on plain http that means an
// HTTP/2-only endpoint (Kestrel:Endpoints:Grpc in appsettings.Development.json, http://localhost:5208).
builder.Services.AddGrpc(o =>
{
    o.EnableDetailedErrors = builder.Environment.IsDevelopment();   // exception messages on the wire: development only
    o.Interceptors.Add<CancellationStatusInterceptor>();             // cancelled / deadline -> the right status code
});

var app = builder.Build();                                          // Development: ValidateScopes + ValidateOnBuild

app.UseExceptionHandler();
app.UseStatusCodePages();
app.UseCors();

if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
    app.MapLifetimeDiagnostics();                                   // GET /diagnostics/lifetimes
}

app.MapHealthChecks("/healthz");
app.MapRequestsApi();
app.MapDigestApi();
app.MapLiveUpdates();                                               // GET/POST /hubs/requests (+ WebSocket)
app.MapGrpcService<RequestsGrpcService>();                          // POST /projectrequests.v1.Requests/{Method} (HTTP/2)

await app.MigrateIfConfiguredAsync();
app.Run();
