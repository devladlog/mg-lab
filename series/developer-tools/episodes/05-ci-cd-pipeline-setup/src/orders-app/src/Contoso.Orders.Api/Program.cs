using System.Runtime.InteropServices;
using Contoso.Orders.Api;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddProblemDetails();
builder.Services.AddOrdersDb(builder.Configuration);

var app = builder.Build();
await Database.InitializeAsync(app.Services, builder.Configuration.GetValue("Orders:SeedCount", 237));

app.MapGet("/healthz", async (OrdersDb db) => Results.Ok(new
{
    status = await db.Database.CanConnectAsync() ? "ok" : "degraded",
    // The commit the image was built from (Dockerfile ARG APP_VERSION); "dev" outside CI.
    version = app.Configuration["App:Version"] ?? "dev",
    database = db.Database.ProviderName?.Split('.').Last(),
    dotnet = RuntimeInformation.FrameworkDescription,
    os = RuntimeInformation.OSDescription,
    user = Environment.UserName,
    inContainer = Environment.GetEnvironmentVariable("DOTNET_RUNNING_IN_CONTAINER") == "true",
}));

app.MapGet("/orders", async (int? page, int? pageSize, OrdersDb db) =>
{
    if (Paging.Normalize(page, pageSize) is not { } p)
        return Results.ValidationProblem(new Dictionary<string, string[]> { ["page"] = ["page must be 1 or greater"] });
    var total = await db.Orders.CountAsync();
    var items = await db.Orders.AsNoTracking().OrderBy(o => o.Id)
        .Skip((p.Page - 1) * p.Size).Take(p.Size).ToListAsync();
    return Results.Ok(new Page<Order>(p.Page, p.Size, total, items));
});

app.MapGet("/orders/{id:int}", async (int id, OrdersDb db) =>
    await db.Orders.FindAsync(id) is { } order ? Results.Ok(order) : Results.NotFound());

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
});

app.Run();

public partial class Program;
