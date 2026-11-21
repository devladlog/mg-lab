using TenantApi;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddTenantApi(builder.Configuration, builder.Environment);

var app = builder.Build();
app.UseTenantApi();
app.Run();

// Lets WebApplicationFactory<Program> find the entry point in tests.
public partial class Program;
