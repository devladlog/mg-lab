using PurchaseRequests.Api;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddPurchaseRequestsApi(builder.Configuration, builder.Environment);

var app = builder.Build();
app.UsePurchaseRequestsApi();
app.Run();

// Lets WebApplicationFactory<Program> find the entry point in tests.
public partial class Program;
