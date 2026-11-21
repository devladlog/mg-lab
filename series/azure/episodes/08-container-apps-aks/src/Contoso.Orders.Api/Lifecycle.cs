namespace Contoso.Orders.Api;

public sealed class LifecycleOptions
{
    /// <summary>Report not-ready for this long after start (caches, connections). 0 in tests.</summary>
    public int WarmupSeconds { get; set; } = 3;

    /// <summary>After SIGTERM: stay up, answer requests, but report not-ready so no new traffic arrives.</summary>
    public int DrainSeconds { get; set; } = 5;
}

public enum ReadyState { WarmingUp, Ready, Draining }

public sealed class Readiness(TimeProvider time, Microsoft.Extensions.Options.IOptions<LifecycleOptions> options)
{
    private readonly DateTimeOffset _started = time.GetUtcNow();
    private volatile bool _draining;

    public ReadyState State =>
        _draining ? ReadyState.Draining
        : time.GetUtcNow() - _started < TimeSpan.FromSeconds(options.Value.WarmupSeconds) ? ReadyState.WarmingUp
        : ReadyState.Ready;

    public void BeginDrain() => _draining = true;
}

/// <summary>
/// On SIGTERM the host calls StopAsync: flip readiness to 503 first, then wait DrainSeconds before the
/// server stops accepting connections, so the platform has time to take the replica out of rotation.
/// </summary>
public sealed class GracefulShutdown(Readiness readiness, TimeProvider time,
    Microsoft.Extensions.Options.IOptions<LifecycleOptions> options, ILogger<GracefulShutdown> log) : IHostedLifecycleService
{
    public Task StartingAsync(CancellationToken ct) => Task.CompletedTask;
    public Task StartAsync(CancellationToken ct) => Task.CompletedTask;
    public Task StartedAsync(CancellationToken ct) => Task.CompletedTask;

    public async Task StoppingAsync(CancellationToken ct)
    {
        readiness.BeginDrain();
        log.LogInformation("SIGTERM received: readiness is now 503, draining for {Seconds} s", options.Value.DrainSeconds);
        await Task.Delay(TimeSpan.FromSeconds(options.Value.DrainSeconds), time, ct);
    }

    public Task StopAsync(CancellationToken ct) => Task.CompletedTask;
    public Task StoppedAsync(CancellationToken ct) => Task.CompletedTask;
}
