using Azure.Core;
using Azure.Identity;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Graph;

var builder = FunctionsApplication.CreateBuilder(args);
builder.ConfigureFunctionsWebApplication();

// One credential for every environment:
//   in Azure  -> the user-assigned managed identity named by GRAPH_CLIENT_ID (no secrets, nothing to rotate)
//   locally   -> your az login / Visual Studio account
builder.Services.AddSingleton<TokenCredential>(new DefaultAzureCredential(new DefaultAzureCredentialOptions
{
    ManagedIdentityClientId = builder.Configuration["GRAPH_CLIENT_ID"]
}));
builder.Services.AddSingleton(sp =>
    new GraphServiceClient(sp.GetRequiredService<TokenCredential>(), ["https://graph.microsoft.com/.default"]));

builder.Build().Run();
