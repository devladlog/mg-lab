using Contoso.Approvals.Patterns.Events;
using Microsoft.Extensions.DependencyInjection;

namespace Contoso.Approvals.Patterns.Cli;

/// <summary>Wrong on purpose, for the gotcha in the video. Compiles, and in Production it even runs.</summary>
internal static class Mistakes
{
    public static IServiceCollection AddRequestObserversWithCaptiveAudit(this IServiceCollection services)
    {
        services.AddScoped<AuditTrail>();
        // "The audit observer has no state, make it a singleton." But it holds a scoped AuditTrail:
        // a captive dependency. The singleton keeps the first AuditTrail it was given, forever.
        services.AddSingleton<IRequestObserver, AuditObserver>();
        services.AddSingleton<IRequestObserver, OutboxObserver>();
        services.AddSingleton<BudgetTally>();
        services.AddSingleton<IRequestObserver, BudgetTallyObserver>();
        return services;
    }
}
