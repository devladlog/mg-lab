using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Diagnostics.HealthChecks;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Http.Resilience;
using Microsoft.Extensions.Logging;

namespace Contoso.ServiceDefaults;

/// <summary>The header a caller sends to say "this request is safe to repeat".</summary>
public static class Idempotency
{
    public const string Header = "Idempotency-Key";
}

public static class ServiceDefaultsExtensions
{
    public static TBuilder AddServiceDefaults<TBuilder>(
        this TBuilder builder, Action<HttpStandardResilienceOptions>? tuneResilience = null)
        where TBuilder : IHostApplicationBuilder
    {
        builder.Services.AddServiceDiscovery();   // logical names ("http://budget") -> addresses from configuration

        builder.Services.ConfigureHttpClientDefaults(http =>
        {
            http.AddStandardResilienceHandler(options =>
            {
                RetryPolicy.ApplyIdempotencyRule(options.Retry);
                tuneResilience?.Invoke(options);
            });
            http.AddServiceDiscovery();
        });

        // Live = "the process runs" (restart me if not). Ready = "my dependencies work" (send me traffic if so).
        builder.Services.AddHealthChecks().AddCheck("self", () => HealthCheckResult.Healthy(), tags: ["live"]);

        // The trace id of the request being handled goes on every log line, so one request can be followed across services.
        builder.Logging.Configure(o => o.ActivityTrackingOptions =
            ActivityTrackingOptions.TraceId | ActivityTrackingOptions.SpanId);
        builder.Logging.AddSimpleConsole(o => { o.IncludeScopes = true; o.SingleLine = true; });

        return builder;
    }

    public static WebApplication MapDefaultEndpoints(this WebApplication app)
    {
        app.MapHealthChecks("/alive", new HealthCheckOptions { Predicate = r => r.Tags.Contains("live") });
        app.MapHealthChecks("/health");
        return app;
    }
}
