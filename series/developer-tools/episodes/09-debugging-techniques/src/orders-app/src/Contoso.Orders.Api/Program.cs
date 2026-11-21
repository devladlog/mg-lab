using System.Runtime.InteropServices;
using Contoso.Orders.Api;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddProblemDetails();
builder.Services.AddOpenApi();                       // the API describes itself: /openapi/v1.json (OpenAPI 3.1 on .NET 10)
builder.Services.AddOrdersDb(builder.Configuration);
// One report cache for the process. Orders:Cache:HoldMs simulates a database call made while a lock is held (0 = off).
builder.Services.AddSingleton(new ReportCache(builder.Configuration.GetValue("Orders:Cache:HoldMs", 0)));

var app = builder.Build();
await Database.InitializeAsync(app.Services, builder.Configuration.GetValue("Orders:SeedCount", 237));

// Learn's sample maps the document only in Development. Here it is a setting (default on) so the container
// the Postman collection is tested against serves it too; turn it off where the contract must stay private.
if (app.Configuration.GetValue("OpenApi:Enabled", true)) app.MapOpenApi();

app.MapGet("/healthz", async (OrdersDb db) => Results.Ok(new Health(
    Status: await db.Database.CanConnectAsync() ? "ok" : "degraded",
    // The commit the image was built from (Dockerfile ARG APP_VERSION); "dev" outside CI.
    Version: app.Configuration["App:Version"] ?? "dev",
    Database: db.Database.ProviderName?.Split('.').Last(),
    Dotnet: RuntimeInformation.FrameworkDescription,
    Os: RuntimeInformation.OSDescription,
    User: Environment.UserName,
    InContainer: Environment.GetEnvironmentVariable("DOTNET_RUNNING_IN_CONTAINER") == "true")))
    .WithName("GetHealth").Produces<Health>();

app.MapGet("/orders", async (int? page, int? pageSize, OrdersDb db) =>
{
    if (Paging.Normalize(page, pageSize) is not { } p)
        return Results.ValidationProblem(new Dictionary<string, string[]> { ["page"] = ["page must be 1 or greater"] });
    var total = await db.Orders.CountAsync();
    var items = await db.Orders.AsNoTracking().OrderBy(o => o.Id)
        .Skip((p.Page - 1) * p.Size).Take(p.Size).ToListAsync();
    return Results.Ok(new Page<Order>(p.Page, p.Size, total, items));
}).WithName("ListOrders").Produces<Page<Order>>().ProducesValidationProblem();

app.MapGet("/orders/{id:int}", async (int id, OrdersDb db) =>
    await db.Orders.FindAsync(id) is { } order ? Results.Ok(order) : Results.NotFound())
    .WithName("GetOrder").Produces<Order>().Produces(StatusCodes.Status404NotFound);

app.MapPost("/orders", async (NewOrder input, OrdersDb db) =>
{
    var errors = new Dictionary<string, string[]>();
    if (string.IsNullOrWhiteSpace(input.Customer) || input.Customer.Length > 100)
        errors["customer"] = ["customer is required (max 100 characters)"];
    if (input.Total <= 0)
        errors["total"] = ["total must be greater than zero"];
    if (errors.Count > 0) return Results.ValidationProblem(errors);

    var order = new Order { Customer = input.Customer!.Trim(), Total = input.Total, Created = DateOnly.FromDateTime(DateTime.UtcNow) };
    db.Orders.Add(order);
    await db.SaveChangesAsync();
    return Results.Created($"/orders/{order.Id}", order);
}).WithName("CreateOrder").Produces<Order>(StatusCodes.Status201Created).ProducesValidationProblem();

app.MapGet("/reports/monthly", async (string? month, OrdersDb db, ReportCache cache, ILoggerFactory loggers, CancellationToken ct) =>
{
    var log = loggers.CreateLogger("Contoso.Orders.Reports");
    if (!Reports.TryParseMonth(month, out var firstDay))
    {
        log.MonthRejected(month);
        return Results.ValidationProblem(new Dictionary<string, string[]> { ["month"] = ["month must look like 2026-03"] });
    }

    var key = firstDay.ToString("yyyy-MM");
    if (cache.TryGet(key, out var cached))
        return Results.Ok(cached);

    var report = await Reports.MonthlyRevenueAsync(db, firstDay, ct);
    cache.Set(report);
    log.MonthlyRevenueComputed(report.Month, report.Customers.Count, report.Orders, report.Total);
    return Results.Ok(report);
}).WithName("GetMonthlyRevenue").Produces<MonthlyRevenue>().ProducesValidationProblem();

app.MapGet("/reports/cache", (ReportCache cache) => Results.Ok(cache.Snapshot()))
    .WithName("GetReportCache").Produces<CacheStats>();

app.MapPost("/reports/cache/invalidate", (ReportCache cache) =>
{
    cache.Invalidate();
    return Results.NoContent();
}).WithName("InvalidateReportCache").Produces(StatusCodes.Status204NoContent);

app.Run();

public partial class Program;
