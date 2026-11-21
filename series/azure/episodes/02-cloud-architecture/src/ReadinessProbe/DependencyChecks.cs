using Azure.Security.KeyVault.Secrets;
using Azure.Storage.Blobs;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;

namespace ReadinessProbe;

/// <summary>
/// Reads the container's properties through the private endpoint, with the app's managed identity.
/// Success proves three things at once: DNS resolves to the private endpoint, the network path is open,
/// and the identity has a data-plane role. The storage account itself has public network access disabled.
/// </summary>
public sealed class BlobContainerCheck(BlobContainerClient container, IOptions<ProbeOptions> options) : IHealthCheck
{
    public async Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken ct = default)
    {
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(options.Value.Timeout);
        try
        {
            await container.GetPropertiesAsync(cancellationToken: cts.Token);
            return HealthCheckResult.Healthy($"container '{container.Name}' reachable");
        }
        catch (Exception ex) when (ex is not OperationCanceledException || !ct.IsCancellationRequested)
        {
            return HealthCheckResult.Unhealthy(Describe(ex));
        }
    }

    internal static string Describe(Exception ex) => ex switch
    {
        OperationCanceledException => "timed out",
        Azure.RequestFailedException rfe => $"HTTP {rfe.Status} {rfe.ErrorCode}",
        _ => ex.GetType().Name,
    };
}

/// <summary>Reads one secret through the Key Vault private endpoint (Key Vault Secrets User role).</summary>
public sealed class KeyVaultSecretCheck(SecretClient secrets, IOptions<ProbeOptions> options) : IHealthCheck
{
    public async Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken ct = default)
    {
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(options.Value.Timeout);
        try
        {
            await secrets.GetSecretAsync(options.Value.SecretName, cancellationToken: cts.Token);
            return HealthCheckResult.Healthy($"secret '{options.Value.SecretName}' readable"); // never the value
        }
        catch (Exception ex) when (ex is not OperationCanceledException || !ct.IsCancellationRequested)
        {
            return HealthCheckResult.Unhealthy(BlobContainerCheck.Describe(ex));
        }
    }
}
