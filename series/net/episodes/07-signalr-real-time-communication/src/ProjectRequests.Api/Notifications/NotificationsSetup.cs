using Microsoft.AspNetCore.Http.HttpResults;
using Microsoft.Extensions.Options;

namespace ProjectRequests.Api.Notifications;

public static class NotificationsSetup
{
    public static IServiceCollection AddNotifications(this IServiceCollection services, IConfiguration config)
    {
        // Options: bound, validated, and checked when the host starts.
        services.AddOptions<NotificationOptions>()
            .Bind(config.GetSection(NotificationOptions.Section))
            .ValidateDataAnnotations()                     // attributes + IValidatableObject
            .ValidateOnStart();

        // Two implementations of one interface, told apart by a key (.NET 8+ keyed services).
        services.AddKeyedSingleton<INotificationChannel, LogNotificationChannel>("log");
        services.AddHttpClient<WebhookNotificationChannel>(c => c.Timeout = TimeSpan.FromSeconds(10));
        services.AddKeyedTransient<INotificationChannel>("webhook",
            (sp, _) => sp.GetRequiredService<WebhookNotificationChannel>());

        // "The" channel: whichever key the configuration names, resolved per scope.
        services.AddScoped<INotificationChannel>(sp => sp.GetRequiredKeyedService<INotificationChannel>(
            sp.GetRequiredService<IOptionsSnapshot<NotificationOptions>>().Value.Channel));

        services.AddScoped<PendingDigestBuilder>();

        // One instance, reachable both as a hosted service and directly (tests, the send-now endpoint).
        services.AddSingleton<DigestWorker>();
        services.AddHostedService(sp => sp.GetRequiredService<DigestWorker>());

        return services;
    }

    public static IEndpointRouteBuilder MapDigestApi(this IEndpointRouteBuilder app)
    {
        app.MapPost("/api/digest/send", SendNow).WithTags("Digest").WithName("SendDigestNow");
        return app;
    }

    /// <summary>Same work as one worker run, but in the request's scope (its DbContext, its channel).</summary>
    public static async Task<Ok<SentDigest>> SendNow(
        PendingDigestBuilder builder, INotificationChannel channel, CancellationToken ct)
    {
        var digest = await builder.BuildAsync(ct);
        if (digest.Lines.Count > 0)
            await channel.SendAsync(digest, ct);
        return TypedResults.Ok(new SentDigest(channel.Name, digest.Lines.Count > 0, digest));
    }
}

public sealed record SentDigest(string Channel, bool Sent, PendingDigest Digest);
