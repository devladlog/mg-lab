using System.Runtime.InteropServices;
using Contoso.Orders.Api;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddProblemDetails();
builder.Services.AddSingleton(_ => OrderCatalog.Seed(builder.Configuration.GetValue("Orders:SeedCount", 237)));

var app = builder.Build();

// Where am I running? In the dev container this prints the container's Linux, not the host's Windows.
app.MapGet("/healthz", () => Results.Ok(new
{
    status = "ok",
    dotnet = RuntimeInformation.FrameworkDescription,
    os = RuntimeInformation.OSDescription,
    // Set by Microsoft's .NET images, including the dev container image.
    inContainer = Environment.GetEnvironmentVariable("DOTNET_RUNNING_IN_CONTAINER") == "true",
}));

app.MapGet("/orders", (int? page, int? pageSize, OrderCatalog catalog) =>
    Paging.Normalize(page, pageSize) is { } p
        ? Results.Ok(catalog.GetPage(p.Page, p.Size))
        : Results.ValidationProblem(new Dictionary<string, string[]>
        {
            ["page"] = ["page must be 1 or greater"],
        }));

app.MapGet("/orders/{id:int}", (int id, OrderCatalog catalog) =>
    catalog.Find(id) is { } order ? Results.Ok(order) : Results.NotFound());

app.Run();

public partial class Program;
