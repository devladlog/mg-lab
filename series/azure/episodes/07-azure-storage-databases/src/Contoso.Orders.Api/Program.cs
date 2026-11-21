using Azure.Identity;
using Azure.Storage.Blobs;
using Contoso.Orders.Api.Data;
using Contoso.Orders.Api.Invoices;
using Contoso.Orders.Api.Orders;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

// dotnet run -- --print-schema   prints the T-SQL for the model (db/schema.sql), no connection needed
if (args.Contains("--print-schema"))
{
    Console.Write(DatabaseSetup.SqlServerCreateScript());
    return;
}

var builder = WebApplication.CreateBuilder(args);
builder.Services.Configure<DatabaseOptions>(builder.Configuration.GetSection("Database"));
builder.Services.Configure<InvoiceOptions>(builder.Configuration.GetSection("Invoices"));
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddDbContext<OrdersDbContext>((sp, b) =>
    DatabaseSetup.Configure(b, sp.GetRequiredService<IOptions<DatabaseOptions>>().Value));
builder.Services.AddScoped<OrderService>();
builder.Services.AddSingleton<IInvoiceStore>(sp =>
{
    var o = sp.GetRequiredService<IOptions<InvoiceOptions>>().Value;
    if (string.IsNullOrWhiteSpace(o.BlobServiceUri)) return new DisabledInvoiceStore();
    // Managed identity in Azure, az login / Visual Studio on a laptop. Never an account key.
    var service = new BlobServiceClient(new Uri(o.BlobServiceUri), new DefaultAzureCredential());
    return new BlobInvoiceStore(service, o.Container, sp.GetRequiredService<TimeProvider>());
});

var app = builder.Build();

// dotnet run -- --create-schema   creates the tables if the database has none (run once per environment)
if (args.Contains("--create-schema"))
{
    using var scope = app.Services.CreateScope();
    var created = await scope.ServiceProvider.GetRequiredService<OrdersDbContext>().Database.EnsureCreatedAsync();
    Console.WriteLine(created ? "Schema created." : "Database already has tables: nothing to do.");
    return;
}

// A real EF query, so it runs inside the retrying execution strategy.
// The first call after the free-tier database auto-paused shows the 40613 retries in the log.
app.MapGet("/healthz", async (OrdersDbContext db, CancellationToken ct) =>
{
    var any = await db.Orders.AnyAsync(ct);
    return Results.Ok(new { status = "ok", hasOrders = any });
});

app.MapPost("/orders", async (HttpRequest http, CreateOrderRequest? body, OrderService orders, IInvoiceStore invoices, CancellationToken ct) =>
{
    var key = http.Headers["Idempotency-Key"].ToString();
    if (key.Length is < 1 or > 64)
        return Results.Problem("Idempotency-Key header (1-64 characters) is required.", statusCode: 400);

    var errors = OrderRules.Validate(body);
    if (errors.Count > 0) return Results.ValidationProblem(new Dictionary<string, string[]> { ["order"] = [.. errors] });

    var result = await orders.CreateAsync(key, body!, ct);
    switch (result.Outcome)
    {
        case CreateOutcome.UnknownSku:
            return Results.Problem(result.Error, statusCode: 422);
        case CreateOutcome.KeyReused:
            return Results.Problem("This Idempotency-Key was already used with a different request.", statusCode: 409);
    }

    var order = result.Order!;
    // Written after the commit and on every replay: the blob name is the order id, so this is safe to repeat
    await invoices.SaveAsync(order, ct);
    http.HttpContext.Response.Headers.ETag = ETag(order);
    if (result.Outcome == CreateOutcome.Replayed)
    {
        http.HttpContext.Response.Headers["Idempotent-Replay"] = "true";
        return Results.Ok(OrderDto.From(order));
    }
    return Results.Created($"/orders/{order.Id}", OrderDto.From(order));
});

app.MapGet("/orders/{id:long}", async (long id, HttpResponse response, OrderService orders, CancellationToken ct) =>
{
    var order = await orders.GetAsync(id, ct);
    if (order is null) return Results.NotFound();
    response.Headers.ETag = ETag(order);
    return Results.Ok(OrderDto.From(order));
});

app.MapGet("/customers/{customerId}/orders", async (string customerId, string? after, int? take, OrderService orders, CancellationToken ct) =>
{
    try { return Results.Ok(await orders.ListForCustomerAsync(customerId, after, take ?? 10, ct)); }
    catch (FormatException) { return Results.Problem("Invalid cursor.", statusCode: 400); }
});

app.MapPost("/orders/{id:long}/cancel", async (long id, HttpRequest http, OrderService orders, CancellationToken ct) =>
{
    var ifMatch = http.Headers.IfMatch.ToString().Trim('"');
    if (!Guid.TryParseExact(ifMatch, "N", out var version))
        return Results.Problem("If-Match with the order's ETag is required.", statusCode: 428);

    var result = await orders.CancelAsync(id, version, ct);
    return result.Outcome switch
    {
        CancelOutcome.NotFound => Results.NotFound(),
        CancelOutcome.VersionMismatch => Results.Problem("The order changed since you read it. GET it again.", statusCode: 412),
        CancelOutcome.AlreadyCancelled => Results.Problem("Already cancelled.", statusCode: 409),
        _ => WithETag(http.HttpContext.Response, result.Order!),
    };
});

app.MapGet("/orders/{id:long}/invoice", async (long id, OrderService orders, IInvoiceStore invoices, CancellationToken ct) =>
{
    if (invoices is DisabledInvoiceStore) return Results.Problem("Invoice storage is not configured.", statusCode: 503);
    var order = await orders.GetAsync(id, ct);
    if (order is null) return Results.NotFound();
    var link = await invoices.GetReadLinkAsync(order, TimeSpan.FromMinutes(10), ct);
    return Results.Ok(new { url = link.Url, expiresOn = link.ExpiresOn });
});

app.Run();

static string ETag(Order o) => $"\"{o.Version:N}\"";

static IResult WithETag(HttpResponse response, Order o)
{
    response.Headers.ETag = ETag(o);
    return Results.Ok(OrderDto.From(o));
}

public partial class Program;
