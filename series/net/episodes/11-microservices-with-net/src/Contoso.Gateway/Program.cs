using System.Text.Json;
using Contoso.Gateway;
using Contoso.ServiceDefaults;
using Microsoft.AspNetCore.Diagnostics.HealthChecks;
using Microsoft.Extensions.Diagnostics.HealthChecks;

var builder = WebApplication.CreateBuilder(args);
builder.AddServiceDefaults();

builder.Services.AddReverseProxy()
    .LoadFromConfig(builder.Configuration.GetSection("ReverseProxy"))
    .AddServiceDiscoveryDestinationResolver();   // "http://requests/" in the YARP config is resolved by service discovery

// A health probe must answer fast and must not retry: no resilience handler on this client.
#pragma warning disable EXTEXP0001   // RemoveAllResilienceHandlers is marked experimental (it is on Learn, too)
builder.Services.AddHttpClient("downstream", c => c.Timeout = TimeSpan.FromSeconds(2)).RemoveAllResilienceHandlers();
#pragma warning restore EXTEXP0001
builder.Services.AddHealthChecks()
    .Add(new HealthCheckRegistration("requests", sp => new DownstreamHealth("requests", sp.GetRequiredService<IHttpClientFactory>()),
        HealthStatus.Degraded, ["downstream"]))
    .Add(new HealthCheckRegistration("budget", sp => new DownstreamHealth("budget", sp.GetRequiredService<IHttpClientFactory>()),
        HealthStatus.Degraded, ["downstream"]));

var app = builder.Build();
app.MapDefaultEndpoints();
app.MapHealthChecks("/health/services", new HealthCheckOptions
{
    Predicate = r => r.Tags.Contains("downstream"),
    ResponseWriter = async (context, report) =>
    {
        context.Response.ContentType = "application/json";
        await context.Response.WriteAsync(JsonSerializer.Serialize(new
        {
            status = report.Status.ToString(),
            services = report.Entries.ToDictionary(e => e.Key, e => new { status = e.Value.Status.ToString(), detail = e.Value.Description }),
        }, new JsonSerializerOptions { WriteIndented = true }));
    },
});
app.MapReverseProxy();
app.Run();

public sealed class GatewayMarker;
