using ProjectRequests.Api.Data;

namespace ProjectRequests.Api.Diagnostics;

/// <summary>Three identical classes; only their registration differs. Each instance gets a new id.</summary>
public sealed class TransientProbe { public string Id { get; } = Guid.NewGuid().ToString("N")[..8]; }
public sealed class ScopedProbe { public string Id { get; } = Guid.NewGuid().ToString("N")[..8]; }
public sealed class SingletonProbe { public string Id { get; } = Guid.NewGuid().ToString("N")[..8]; }

/// <summary>A scoped service that depends on all three, plus the DbContext.</summary>
public sealed class ProbeConsumer(TransientProbe transient, ScopedProbe scoped, SingletonProbe singleton, RequestsDbContext db)
{
    public LifetimeIds Ids => new(transient.Id, scoped.Id, singleton.Id, db.ContextId.InstanceId.ToString("N")[..8]);
}

public sealed record LifetimeIds(string Transient, string Scoped, string Singleton, string DbContext);

public sealed record LifetimeReport(LifetimeIds Endpoint, LifetimeIds Consumer);

public static class LifetimeDiagnostics
{
    public static IServiceCollection AddLifetimeProbes(this IServiceCollection services) => services
        .AddTransient<TransientProbe>()
        .AddScoped<ScopedProbe>()
        .AddSingleton<SingletonProbe>()
        .AddScoped<ProbeConsumer>();

    /// <summary>GET /diagnostics/lifetimes: what this request's endpoint got vs. what ProbeConsumer got.</summary>
    public static IEndpointRouteBuilder MapLifetimeDiagnostics(this IEndpointRouteBuilder app)
    {
        app.MapGet("/diagnostics/lifetimes", (TransientProbe t, ScopedProbe s, SingletonProbe g,
                RequestsDbContext db, ProbeConsumer consumer) =>
            TypedResults.Ok(new LifetimeReport(
                new LifetimeIds(t.Id, s.Id, g.Id, db.ContextId.InstanceId.ToString("N")[..8]),
                consumer.Ids)))
            .WithTags("Diagnostics");
        return app;
    }
}
