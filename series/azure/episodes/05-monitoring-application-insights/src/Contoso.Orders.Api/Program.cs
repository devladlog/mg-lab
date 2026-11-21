using Azure.Storage.Blobs;
using Contoso.Orders.Api.Orders;
using Contoso.Orders.Api.Telemetry;

var builder = WebApplication.CreateBuilder(args);
var credential = TelemetrySetup.CreateCredential(builder.Configuration);

builder.Services.AddOrdersTelemetry(builder.Configuration, credential);
builder.Services.AddProblemDetails();
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.Configure<ChaosOptions>(builder.Configuration.GetSection("Chaos"));
builder.Services.AddSingleton<IFaultDice, RandomFaultDice>();

// Orders:BlobContainerUri set (Azure) -> blob storage with the managed identity; otherwise in memory.
if (builder.Configuration["Orders:BlobContainerUri"] is { Length: > 0 } containerUri)
    builder.Services.AddSingleton(new BlobContainerClient(new Uri(containerUri), credential));
builder.Services.AddSingleton<IOrderStore>(sp =>
{
    var container = sp.GetService<BlobContainerClient>();
    IOrderStore inner = container is null ? new InMemoryOrderStore() : new BlobOrderStore(container);
    return ActivatorUtilities.CreateInstance<ChaosOrderStore>(sp, inner);
});

var app = builder.Build();
app.UseExceptionHandler();   // unhandled exceptions -> 500 problem details (the span records the exception)

app.MapGet("/healthz", () => Results.Ok(new { status = "Healthy" }));
app.MapOrders();

app.Run();

public partial class Program;
