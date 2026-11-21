using Contoso.Approvals.Patterns.Approvers;
using Contoso.Approvals.Patterns.Events;
using Contoso.Approvals.Patterns.Routing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Options;

namespace Contoso.Approvals.Patterns;

/// <summary>The composition root: every pattern in this episode is wired here, and only here.</summary>
public static class ServiceCollectionExtensions
{
    public static IServiceCollection AddApprovals(this IServiceCollection services, IConfiguration configuration) =>
        services.AddApprovalCore(configuration).AddRequestObservers();

    public static IServiceCollection AddApprovalCore(this IServiceCollection services, IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);

        // Options: bound from configuration, validated when the host starts (not on first use).
        services.AddOptions<ApprovalPolicyOptions>()
            .Bind(configuration.GetSection(ApprovalPolicyOptions.SectionName))
            .ValidateDataAnnotations()
            .Validate(p => p.BoardThreshold > p.HighThreshold,
                "Policy:BoardThreshold must be greater than Policy:HighThreshold.")
            .ValidateOnStart();
        services.AddOptions<ApproverDirectoryOptions>()
            .Bind(configuration.GetSection(ApproverDirectoryOptions.SectionName))
            .ValidateDataAnnotations()
            .ValidateOnStart();
        services.AddOptions<OutboxOptions>()
            .Bind(configuration.GetSection(OutboxOptions.SectionName))
            .ValidateDataAnnotations()
            .ValidateOnStart();
        services.TryAddSingleton(TimeProvider.System);

        // Strategy: one registration per route; RouteCatalog gets them all as IEnumerable<IApprovalRoute>.
        services.AddSingleton<IApprovalRoute, StandardRoute>();
        services.AddSingleton<IApprovalRoute, HighValueRoute>();
        services.AddSingleton<IApprovalRoute, BoardRoute>();
        services.AddSingleton<RouteCatalog>();

        // Decorator: Metered -> Caching -> JsonFile. The inner layers are keyed, so nobody can skip the cache.
        services.AddSingleton<DirectoryStats>();
        services.AddKeyedSingleton<IApproverDirectory, JsonFileApproverDirectory>(DirectoryKeys.Source);
        services.AddKeyedSingleton<IApproverDirectory>(DirectoryKeys.Cached, (sp, _) =>
            new CachingApproverDirectory(
                sp.GetRequiredKeyedService<IApproverDirectory>(DirectoryKeys.Source),
                sp.GetRequiredService<TimeProvider>(),
                sp.GetRequiredService<IOptions<ApproverDirectoryOptions>>()));
        services.AddSingleton<IApproverDirectory>(sp =>
            new MeteredApproverDirectory(
                sp.GetRequiredKeyedService<IApproverDirectory>(DirectoryKeys.Cached),
                sp.GetRequiredService<DirectoryStats>()));

        services.AddScoped<ApprovalService>();
        return services;
    }

    /// <summary>Observer: each observer is one registration; they run in this order.</summary>
    public static IServiceCollection AddRequestObservers(this IServiceCollection services)
    {
        services.AddScoped<AuditTrail>();
        services.AddScoped<IRequestObserver, AuditObserver>();      // scoped: writes to this scope's AuditTrail
        services.AddSingleton<IRequestObserver, OutboxObserver>();
        services.AddSingleton<BudgetTally>();
        services.AddSingleton<IRequestObserver, BudgetTallyObserver>();
        return services;
    }
}
