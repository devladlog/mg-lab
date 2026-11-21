using Azure.Core;
using Azure.Identity;
using Azure.Security.KeyVault.Secrets;
using Azure.Storage.Blobs;
using Microsoft.AspNetCore.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;
using ReadinessProbe;
using System.Text.Json;

var builder = WebApplication.CreateBuilder(args);

// Misconfiguration fails at startup (the deployment shows it), not at the first health ping.
builder.Services.AddOptions<ProbeOptions>()
    .Bind(builder.Configuration.GetSection(ProbeOptions.Section))
    .Validate(o => o.BlobContainerUri is not null, "Probe:BlobContainerUri is required.")
    .Validate(o => o.KeyVaultUri is not null, "Probe:KeyVaultUri is required.")
    .ValidateOnStart();

// One credential for every client. On App Service, AZURE_CLIENT_ID selects the user-assigned identity.
builder.Services.AddSingleton<TokenCredential>(_ => new DefaultAzureCredential());
builder.Services.AddSingleton(sp =>
{
    var options = sp.GetRequiredService<IOptions<ProbeOptions>>().Value;
    return new BlobContainerClient(options.BlobContainerUri, sp.GetRequiredService<TokenCredential>());
});
builder.Services.AddSingleton(sp =>
{
    var options = sp.GetRequiredService<IOptions<ProbeOptions>>().Value;
    return new SecretClient(options.KeyVaultUri, sp.GetRequiredService<TokenCredential>());
});

builder.Services.AddHealthChecks()
    .AddCheck<BlobContainerCheck>("storage")
    .AddCheck<KeyVaultSecretCheck>("keyvault");

var app = builder.Build();

app.MapGet("/", () => Results.Ok(new { service = "readiness-probe", health = "/healthz" }));

// App Service Health check pings this path (siteConfig.healthCheckPath). 200 = healthy, 503 = unhealthy.
app.MapHealthChecks("/healthz", new HealthCheckOptions { ResponseWriter = HealthReportWriter.WriteAsync });

app.Run();

public partial class Program;

public static class HealthReportWriter
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public static Task WriteAsync(HttpContext http, Microsoft.Extensions.Diagnostics.HealthChecks.HealthReport report)
    {
        http.Response.ContentType = "application/json";
        var body = new
        {
            status = report.Status.ToString(),
            checks = report.Entries.Select(e => new { name = e.Key, status = e.Value.Status.ToString(), detail = e.Value.Description }),
        };
        return http.Response.WriteAsync(JsonSerializer.Serialize(body, Json));
    }
}
