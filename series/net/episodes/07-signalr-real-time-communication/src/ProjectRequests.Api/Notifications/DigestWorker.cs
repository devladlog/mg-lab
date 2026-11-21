using Microsoft.Extensions.Options;

namespace ProjectRequests.Api.Notifications;

/// <summary>
/// Hosted services are singletons. So this class never takes the DbContext (scoped) in its constructor:
/// it takes IServiceScopeFactory and creates one scope - one DbContext - per run.
/// </summary>
public sealed class DigestWorker(
    IServiceScopeFactory scopes,
    IOptionsMonitor<NotificationOptions> options,      // singleton-safe; IOptionsSnapshot is scoped
    TimeProvider clock,
    ILogger<DigestWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!options.CurrentValue.DigestEnabled)
            return;

        using var timer = new PeriodicTimer(options.CurrentValue.DigestInterval, clock);
        while (await timer.WaitForNextTickAsync(stoppingToken))
        {
            try
            {
                await RunOnceAsync(stoppingToken);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                // Without this catch, one failed webhook call would stop the whole host (StopHost is the default).
                logger.LogError(ex, "Digest run failed; trying again in {Interval}", options.CurrentValue.DigestInterval);
            }
        }
    }

    public async Task<PendingDigest> RunOnceAsync(CancellationToken ct)
    {
        await using var scope = scopes.CreateAsyncScope();             // new scope = new DbContext, disposed after
        var digest = await scope.ServiceProvider.GetRequiredService<PendingDigestBuilder>().BuildAsync(ct);
        logger.LogInformation("Digest worker run: {Count} pending request(s)", digest.TotalRequests);

        if (digest.Lines.Count > 0)
            await scope.ServiceProvider.GetRequiredService<INotificationChannel>().SendAsync(digest, ct);

        return digest;
    }
}
