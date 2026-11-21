using System.Globalization;
using Microsoft.Extensions.Options;

namespace ProjectRequests.Api.Notifications;

/// <summary>Where the digest goes. Registered as keyed services: "log" and "webhook".</summary>
public interface INotificationChannel
{
    string Name { get; }
    Task SendAsync(PendingDigest digest, CancellationToken ct);
}

/// <summary>Writes the digest to the log (App Service log stream, Application Insights, console).</summary>
public sealed class LogNotificationChannel(ILogger<LogNotificationChannel> logger) : INotificationChannel
{
    public string Name => "log";

    public Task SendAsync(PendingDigest digest, CancellationToken ct)
    {
        logger.LogInformation("Digest: {Count} request(s) waiting more than {Days} day(s) for a decision",
            digest.TotalRequests, digest.StaleAfterDays);
        foreach (var line in digest.Lines)
            logger.LogInformation("  {Department}: {Requests} request(s), {Budget} total, oldest {Oldest:yyyy-MM-dd}",
                line.Department, line.Requests, line.TotalBudget.ToString("N0", CultureInfo.InvariantCulture),
                line.OldestCreatedAtUtc);
        return Task.CompletedTask;
    }
}

/// <summary>
/// POSTs the digest as JSON to Notifications:WebhookUrl. A typed HttpClient: IHttpClientFactory creates it
/// (transient) and manages the handler underneath, so it must never be captured by a singleton.
/// </summary>
public sealed class WebhookNotificationChannel(HttpClient http, IOptionsMonitor<NotificationOptions> options)
    : INotificationChannel
{
    public string Name => "webhook";

    public async Task SendAsync(PendingDigest digest, CancellationToken ct)
    {
        using var response = await http.PostAsJsonAsync(options.CurrentValue.WebhookUrl, digest, ct);
        response.EnsureSuccessStatusCode();
    }
}
