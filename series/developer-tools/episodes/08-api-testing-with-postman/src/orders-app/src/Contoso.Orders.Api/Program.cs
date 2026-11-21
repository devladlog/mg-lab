using System.Runtime.InteropServices;
using Contoso.Orders.Api;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddProblemDetails();
builder.Services.AddOpenApi();                       // the API describes itself: /openapi/v1.json (OpenAPI 3.1 on .NET 10)
builder.Services.AddOrdersDb(builder.Configuration);

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

app.Run();

public partial class Program;
