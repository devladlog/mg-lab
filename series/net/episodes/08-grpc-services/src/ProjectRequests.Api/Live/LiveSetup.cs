using System.Text.Json.Serialization;

namespace ProjectRequests.Api.Live;

public static class LiveSetup
{
    public const string CorsPolicy = "signalr";

    public static IServiceCollection AddLiveUpdates(this IServiceCollection services, IConfiguration config)
    {
        services.AddSignalR()
            // ConfigureHttpJsonOptions does NOT apply to SignalR: the hub protocol has its own serializer options.
            // Without this, enums travel as numbers (0, 1) while the REST API sends "High", "Approved".
            .AddJsonProtocol(o => o.PayloadSerializerOptions.Converters.Add(new JsonStringEnumConverter()));

        // SignalR's CORS needs differ from the REST API's (Learn, SignalR security): GET + POST + DELETE
        // (long polling cleans up with DELETE), credentials allowed (cookie-based sticky sessions), and the
        // client's own headers. Applied to the hub endpoint only; the REST endpoints keep the default policy.
        services.AddCors(o => o.AddPolicy(CorsPolicy, policy => policy
            .WithOrigins(config.GetSection("Cors:AllowedOrigins").Get<string[]>() ?? [])
            .WithMethods("GET", "POST", "DELETE")
            .AllowAnyHeader()
            .AllowCredentials()));

        services.AddSingleton<IRequestEvents, SignalRRequestEvents>();   // IHubContext is a singleton too
        return services;
    }

    public static IEndpointRouteBuilder MapLiveUpdates(this IEndpointRouteBuilder app)
    {
        app.MapHub<RequestsHub>("/" + RequestsHubContract.Path).RequireCors(CorsPolicy);
        return app;
    }
}
