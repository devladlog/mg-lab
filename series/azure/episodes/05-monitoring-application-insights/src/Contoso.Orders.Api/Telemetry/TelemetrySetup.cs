using Azure.Core;
using Azure.Identity;
using Microsoft.OpenTelemetry;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

namespace Contoso.Orders.Api.Telemetry;

/// <summary>Section "Telemetry". Choose one: TracesPerSecond (rate-limited) or SamplingRatio (fixed).</summary>
public sealed class SamplingSettings
{
    public double? TracesPerSecond { get; set; }
    public float? SamplingRatio { get; set; }

    public void Validate()
    {
        if (TracesPerSecond is not null && SamplingRatio is not null)
            throw new InvalidOperationException("Set Telemetry:TracesPerSecond or Telemetry:SamplingRatio, not both.");
        if (TracesPerSecond is < 0)
            throw new InvalidOperationException("Telemetry:TracesPerSecond must be zero or more.");
        if (SamplingRatio is < 0 or > 1)
            throw new InvalidOperationException("Telemetry:SamplingRatio must be between 0 and 1.");
    }
}

public static class TelemetrySetup
{
    public const string ServiceName = "contoso-orders-api"; // = cloud_RoleName (no service.namespace set)

    public static IServiceCollection AddOrdersTelemetry(this IServiceCollection services,
        IConfiguration config, TokenCredential credential)
    {
        var sampling = config.GetSection("Telemetry").Get<SamplingSettings>() ?? new SamplingSettings();
        sampling.Validate();
        var connectionString = config["APPLICATIONINSIGHTS_CONNECTION_STRING"];

        services.AddSingleton<OrdersTelemetry>();
        services.AddOpenTelemetry()
            .ConfigureResource(r => r.AddService(ServiceName))
            .WithTracing(t => t
                .AddSource(OrdersTelemetry.SourceName)              // our spans
                .AddProcessor<ExpectedClientErrorProcessor>())      // 400/404/422 aren't failures
            .WithMetrics(m => m.AddMeter(OrdersTelemetry.MeterName)) // our counters and histogram
            .UseMicrosoftOpenTelemetry(o =>
            {
                if (string.IsNullOrWhiteSpace(connectionString))
                {
                    // Local run and tests: spans go to the console. Not ExportTarget.None: with None
                    // the distro builds no pipeline at all and even a test exporter gets nothing.
                    o.Exporters = ExportTarget.Console;
                    return;
                }
                o.Exporters = ExportTarget.AzureMonitor;
                o.AzureMonitor.ConnectionString = connectionString;
                o.AzureMonitor.Credential = credential;             // Entra ID: local auth is off
                if (sampling.SamplingRatio is { } ratio)
                {
                    o.AzureMonitor.TracesPerSecond = null;          // required to switch to fixed rate
                    o.AzureMonitor.SamplingRatio = ratio;
                }
                else
                {
                    o.AzureMonitor.TracesPerSecond = sampling.TracesPerSecond ?? 5; // the distro default
                }
            });
        return services;
    }

    /// <summary>User-assigned managed identity in Azure (AZURE_CLIENT_ID), Azure CLI on a laptop.</summary>
    public static TokenCredential CreateCredential(IConfiguration config) =>
        config["AZURE_CLIENT_ID"] is { Length: > 0 } clientId
            ? new ManagedIdentityCredential(ManagedIdentityId.FromUserAssignedClientId(clientId))
            : new AzureCliCredential();
}
