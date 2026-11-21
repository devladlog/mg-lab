using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using OrderIntake.Core;

var builder = FunctionsApplication.CreateBuilder(args);

// ASP.NET Core integration: HttpRequest / IActionResult in HTTP functions.
builder.ConfigureFunctionsWebApplication();

builder.Services.AddSingleton<ICatalog, InMemoryCatalog>();
builder.Services.AddSingleton(TimeProvider.System);

builder.Build().Run();
