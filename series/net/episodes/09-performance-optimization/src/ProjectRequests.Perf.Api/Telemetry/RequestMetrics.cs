using System.Diagnostics.Metrics;

namespace ProjectRequests.Perf.Api.Telemetry;

/// <summary>
/// Custom metrics on System.Diagnostics.Metrics. The Meter comes from IMeterFactory (registered by ASP.NET Core),
/// so tests can listen to one app instance without seeing the others.
/// </summary>
public sealed class RequestMetrics
{
    public const string MeterName = "ProjectRequests.Perf";

    private readonly Counter<long> _summaryComputed;
    private readonly Counter<long> _created;

    public RequestMetrics(IMeterFactory meterFactory)
    {
        var meter = meterFactory.Create(MeterName);
        _summaryComputed = meter.CreateCounter<long>("mglab.perf.summary.computed", unit: "{computation}",
            description: "How many times the summary was really computed (cache misses).");
        _created = meter.CreateCounter<long>("mglab.perf.requests.created", unit: "{request}",
            description: "Project requests created through the API.");
    }

    public void SummaryComputed() => _summaryComputed.Add(1);
    public void RequestCreated() => _created.Add(1);
}
