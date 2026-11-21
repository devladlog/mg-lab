using System.Diagnostics;
using Contoso.Orders.Api.Orders;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using OpenTelemetry;
using OpenTelemetry.Logs;
using OpenTelemetry.Metrics;
using OpenTelemetry.Trace;

namespace Contoso.Orders.Api.Tests;

/// <summary>
/// The real app (same Program.cs, same telemetry setup) with one change: an in-memory exporter is
/// added next to the distro, so tests can read the spans and metrics that would go to Azure Monitor.
/// No connection string, so nothing leaves the process.
/// </summary>
public sealed class TelemetryApp(int failurePercent = 0, int diceRoll = 99) : WebApplicationFactory<Program>
{
    public List<Activity> Spans { get; } = [];
    public List<Metric> Metrics { get; } = [];
    public List<LogRecord> Logs { get; } = [];

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseSetting("APPLICATIONINSIGHTS_CONNECTION_STRING", "");
        builder.UseSetting("Orders:BlobContainerUri", "");
        builder.UseSetting("Chaos:FailurePercent", failurePercent.ToString());
        builder.ConfigureTestServices(services =>
        {
            services.ConfigureOpenTelemetryTracerProvider(t => t.AddInMemoryExporter(Spans));
            services.ConfigureOpenTelemetryMeterProvider(m => m.AddInMemoryExporter(Metrics));
            services.ConfigureOpenTelemetryLoggerProvider(l => l.AddInMemoryExporter(Logs));
            services.AddSingleton<IFaultDice>(new FixedDice(diceRoll));
        });
    }

    /// <summary>The server span ends just after the response is written; wait for it.</summary>
    public async Task<Activity> ServerSpanAsync(string route)
    {
        for (var i = 0; i < 100; i++)
        {
            lock (Spans)
            {
                var span = Spans.FirstOrDefault(s => s.Kind == ActivityKind.Server
                    && Equals(s.GetTagItem("http.route"), route));
                if (span is not null) return span;
            }
            await Task.Delay(20);
        }
        throw new Xunit.Sdk.XunitException($"No server span for {route}. Spans: " +
            string.Join(", ", Spans.Select(s => $"{s.Kind}:{s.DisplayName}")));
    }

    public IReadOnlyList<MetricPoint> Points(string metricName)
    {
        Services.GetRequiredService<MeterProvider>().ForceFlush();
        // Cumulative temporality: the last exported batch has the totals so far
        var points = new List<MetricPoint>();
        if (Metrics.LastOrDefault(m => m.Name == metricName) is { } metric)
            foreach (ref readonly var p in metric.GetMetricPoints())
                points.Add(p);
        return points;
    }

    private sealed class FixedDice(int roll) : IFaultDice
    {
        public int Roll() => roll;
    }
}

internal static class MetricPointExtensions
{
    public static object? Tag(this MetricPoint point, string key)
    {
        foreach (var tag in point.Tags)
            if (tag.Key == key) return tag.Value;
        return null;
    }
}
