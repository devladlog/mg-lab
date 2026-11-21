using System.Text.Json;
using Contoso.FinanceReview;

var builder = WebApplication.CreateBuilder(args);
// One readable line per event for `kubectl logs`; the framework's per-request chatter stays at Warning.
builder.Logging.ClearProviders();
builder.Logging.AddSimpleConsole(o => { o.SingleLine = true; o.TimestampFormat = "HH:mm:ss "; });
builder.Logging.AddFilter("Microsoft.AspNetCore", LogLevel.Warning);
builder.Services.AddSingleton<IFinanceReviewSink, LoggingSink>();
builder.Services.AddSingleton<Delivery>();

var app = builder.Build();

// Names the Dapr component and the Service Bus topic. Kept as constants: contract tests compare them with deploy/ and infra/.
const string PubSubName = "purchase-pubsub";
const string Topic = "purchase-events";
const string Route = "/finance-review";

app.MapGet("/healthz", () => Results.Ok(new { status = "ok" }));

// Programmatic subscription, read once by the sidecar at startup (Dapr docs). rawPayload: the publisher is not Dapr.
app.MapGet("/dapr/subscribe", () => Results.Json(new[]
{
    new
    {
        pubsubname = PubSubName,
        topic = Topic,
        routes = new { @default = Route },
        metadata = new Dictionary<string, string> { ["rawPayload"] = "true" },
    },
}));

// The sidecar posts Content-Type: application/cloudevents+json, which minimal-API body binding would refuse (415).
// So the body is read here, whatever the content type says.
app.MapPost(Route, async (HttpRequest request, Delivery delivery, ILogger<Program> log, CancellationToken ct) =>
{
    JsonDocument doc;
    try { doc = await JsonDocument.ParseAsync(request.Body, cancellationToken: ct); }
    catch (JsonException) { return Results.Json(DeliveryResult.Drop("Request body is not JSON.")); }

    using var _ = doc;
    var result = await delivery.HandleAsync(doc.RootElement, ct);
    if (result.Status != DeliveryStatus.SUCCESS) log.LogWarning("Delivery {Status}: {Reason}", result.Status, result.Reason);
    return Results.Json(result); // 200 + {"status": "..."}: Dapr acts on the status in the body
});

app.Run();

public partial class Program;
