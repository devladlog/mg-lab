using Microsoft.Extensions.Diagnostics.HealthChecks;

namespace Contoso.Gateway;

/// <summary>
/// Asks a downstream service for its /health. A service that is down makes the gateway Degraded, not Unhealthy:
/// the gateway itself still works, and the other routes still do.
/// </summary>
public sealed class DownstreamHealth(string name, IHttpClientFactory clients) : IHealthCheck
{
    public async Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken ct = default)
    {
        try
        {
            var http = clients.CreateClient("downstream");
            using var response = await http.GetAsync($"http://{name}/health", ct);
            return response.IsSuccessStatusCode
                ? HealthCheckResult.Healthy($"{name} answered {(int)response.StatusCode}")
                : HealthCheckResult.Degraded($"{name} answered {(int)response.StatusCode}");
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException && !ct.IsCancellationRequested)
        {
            return HealthCheckResult.Degraded($"{name} is not reachable ({e.GetType().Name})");
        }
    }
}
