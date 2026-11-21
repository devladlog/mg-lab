using Azure.Core;
using Azure.Identity;
using Contoso.InvoiceApproval;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Options;

var builder = FunctionsApplication.CreateBuilder(args);
builder.ConfigureFunctionsWebApplication();

builder.Services.Configure<ApprovalOptions>(builder.Configuration.GetSection("Approval"));
builder.Services.Configure<CallbackOptions>(builder.Configuration.GetSection("Callback"));
builder.Services.Configure<FlowOptions>(builder.Configuration.GetSection("Flow"));

builder.Services.AddSingleton<TokenCredential>(_ => new DefaultAzureCredential());
builder.Services.AddSingleton(sp => CallbackSigner.FromBase64(sp.GetRequiredService<IOptions<CallbackOptions>>().Value.SigningKey));
builder.Services.AddHttpClient<IFlowGateway, HttpFlowGateway>(c => c.Timeout = TimeSpan.FromSeconds(30));

builder.Build().Run();
