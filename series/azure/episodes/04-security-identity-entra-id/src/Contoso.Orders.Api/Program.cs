using System.Collections.Concurrent;
using System.Security.Claims;
using Contoso.Orders.Api;
using Microsoft.Identity.Web;

var builder = WebApplication.CreateBuilder(args);

// Validates Entra access tokens: signature (keys from the tenant's metadata), issuer, lifetime and audience.
// Config section "AzureAd": Instance, TenantId, ClientId (the API's own app registration).
builder.Services.AddMicrosoftIdentityWebApiAuthentication(builder.Configuration, "AzureAd");
builder.Services.AddAuthorizationBuilder().AddOrdersPolicies();
builder.Services.AddSingleton<OrderStore>();

var app = builder.Build();
app.UseAuthentication();
app.UseAuthorization();

app.MapGet("/healthz", () => Results.Ok(new { status = "Healthy" })).AllowAnonymous();

app.MapGet("/orders", (OrderStore store) => Results.Ok(store.All()))
   .RequireAuthorization(AuthPolicies.ReadOrders);

app.MapPost("/orders", (NewOrder order, OrderStore store, ClaimsPrincipal caller) =>
{
    if (string.IsNullOrWhiteSpace(order.Customer) || order.Quantity is < 1 or > 100)
        return Results.ValidationProblem(new Dictionary<string, string[]>
        {
            ["order"] = ["customer is required and quantity must be 1-100"],
        });
    // Record which workload wrote it: azp = client ID of the calling app (v2.0 tokens)
    var saved = store.Add(order, caller.FindFirstValue("azp") ?? "unknown");
    return Results.Created($"/orders/{saved.Id}", saved);
}).RequireAuthorization(AuthPolicies.WriteOrders);

app.MapGet("/me", (ClaimsPrincipal caller) => Results.Ok(new
{
    kind = caller.FindFirstValue("idtyp") == "app" ? "app-only" : "delegated",
    scopes = caller.FindFirstValue("http://schemas.microsoft.com/identity/claims/scope")
             ?? caller.FindFirstValue("scp"),
    roles = caller.FindAll(ClaimTypes.Role).Select(c => c.Value)
            .Concat(caller.FindAll("roles").Select(c => c.Value)).Distinct(),
})).RequireAuthorization(AuthPolicies.ReadOrders);

app.Run();

public record NewOrder(string Customer, string Sku, int Quantity);
public record Order(string Id, string Customer, string Sku, int Quantity, string CreatedBy);

public sealed class OrderStore
{
    private readonly ConcurrentDictionary<string, Order> orders = new();

    public IEnumerable<Order> All() => orders.Values.OrderBy(o => o.Id);

    public Order Add(NewOrder o, string createdBy)
    {
        var saved = new Order($"ORD-{orders.Count + 1:D4}", o.Customer, o.Sku, o.Quantity, createdBy);
        orders[saved.Id] = saved;
        return saved;
    }
}

public partial class Program;
