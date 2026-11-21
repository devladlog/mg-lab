using Contoso.PurchaseStatus;

var builder = WebApplication.CreateBuilder(args);
builder.WebHost.ConfigureKestrel(o => o.AddServerHeader = false);
var app = builder.Build();

app.Use(async (ctx, next) =>
{
    ctx.Response.Headers["X-Content-Type-Options"] = "nosniff";
    ctx.Response.Headers["Cache-Control"] = "no-store";
    await next();
});

app.MapGet("/healthz", () => Results.Ok(new { status = "ok" }));

app.MapGet("/api/status/{id}", (string id) =>
{
    if (!StatusStore.IsValidId(id)) return Results.BadRequest(new { error = "id must look like PR-1001" });
    return StatusStore.Find(id) is { } s ? Results.Ok(s) : Results.NotFound();
});

app.Run();

public partial class Program;
