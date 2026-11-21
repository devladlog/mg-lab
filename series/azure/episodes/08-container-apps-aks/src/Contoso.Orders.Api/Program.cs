using System.Reflection;
using Contoso.Orders.Api;

var builder = WebApplication.CreateBuilder(args);
builder.Services.Configure<LifecycleOptions>(builder.Configuration.GetSection("Lifecycle"));
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddSingleton<Readiness>();
builder.Services.AddHostedService<GracefulShutdown>();
// Give in-flight requests time to finish after SIGTERM (Kubernetes and Container Apps send it before stopping a replica)
builder.Services.Configure<HostOptions>(o => o.ShutdownTimeout = TimeSpan.FromSeconds(25));

var app = builder.Build();

var version = Assembly.GetExecutingAssembly().GetCustomAttribute<AssemblyInformationalVersionAttribute>()!
    .InformationalVersion.Split('+')[0];

app.Use(async (ctx, next) =>
{
    ctx.Response.Headers["X-App-Version"] = version;
    await next();
});

// Who answered: version + where it runs. Container Apps sets CONTAINER_APP_NAME / _REVISION / _REPLICA_NAME;
// Kubernetes sets KUBERNETES_SERVICE_HOST, and k8s/deployment.yaml passes POD_NAME through the downward API.
app.MapGet("/", () => Results.Ok(new
{
    service = "contoso-orders-api",
    version,
    platform = Env("CONTAINER_APP_NAME") is not null ? "container-apps" : Env("KUBERNETES_SERVICE_HOST") is not null ? "kubernetes" : "local",
    revision = Env("CONTAINER_APP_REVISION"),
    replica = Env("CONTAINER_APP_REPLICA_NAME") ?? Env("POD_NAME") ?? Environment.MachineName,
}));

// Liveness: the process can answer. Never checks dependencies (a slow database must not restart every replica).
app.MapGet("/healthz/live", () => Results.Ok("live"));

// Readiness: send me traffic. False while warming up and while draining after SIGTERM.
app.MapGet("/healthz/ready", (Readiness r) =>
    r.State == ReadyState.Ready ? Results.Ok("ready") : Results.Json(new { state = r.State.ToString() }, statusCode: 503));

// Stateless pricing (episode 1's catalogue): any replica can answer any request, so it scales out and to zero.
app.MapPost("/quotes", (QuoteRequest? request) =>
{
    var errors = Pricing.Validate(request);
    if (errors.Count > 0) return Results.ValidationProblem(new Dictionary<string, string[]> { ["quote"] = [.. errors] });
    var quote = Pricing.Price(request!);
    return quote is null ? Results.Problem("Unknown SKU.", statusCode: 422) : Results.Ok(quote);
});

app.Run();

static string? Env(string name) => Environment.GetEnvironmentVariable(name);

public partial class Program;
