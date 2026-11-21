using Contoso.Approvals.Patterns.Events;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Contoso.Approvals.Patterns.Tests;

internal static class TestHost
{
    public static string ApproversFile => Path.Combine(AppContext.BaseDirectory, "samples", "approvers.json");

    public static string RequestsFile => Path.Combine(AppContext.BaseDirectory, "samples", "requests.json");

    public static IConfiguration Config(params (string Key, string Value)[] overrides)
    {
        var values = new Dictionary<string, string?>
        {
            ["Directory:File"] = ApproversFile,
            ["Outbox:Folder"] = Path.Combine(Path.GetTempPath(), "mglab-ep05-" + Guid.NewGuid().ToString("N")),
        };
        foreach (var (key, value) in overrides)
        {
            values[key] = value;
        }

        return new ConfigurationBuilder().AddInMemoryCollection(values).Build();
    }

    /// <summary>The real composition root, with the scope and build validation the Development environment uses.</summary>
    public static ServiceProvider Provider(IConfiguration? config = null, Action<IServiceCollection>? extra = null)
    {
        var services = new ServiceCollection();
        services.AddApprovals(config ?? Config());
        extra?.Invoke(services);
        return services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true, ValidateOnBuild = true });
    }

    /// <summary>A generic host like the CLI's, in the given environment.</summary>
    public static HostApplicationBuilder HostBuilder(string environment, IConfiguration config)
    {
        var builder = Host.CreateApplicationBuilder(new HostApplicationBuilderSettings
        {
            EnvironmentName = environment,
            DisableDefaults = false,
            ContentRootPath = AppContext.BaseDirectory,
        });
        builder.Configuration.AddConfiguration(config);
        return builder;
    }

    /// <summary>Same mistake as the CLI's Mistakes.cs: a singleton observer that holds a scoped AuditTrail.</summary>
    public static IServiceCollection AddObserversWithCaptiveAudit(this IServiceCollection services)
    {
        services.AddScoped<AuditTrail>();
        services.AddSingleton<IRequestObserver, AuditObserver>();
        services.AddSingleton<BudgetTally>();
        services.AddSingleton<IRequestObserver, BudgetTallyObserver>();
        return services;
    }

    public static ProjectRequest Request(decimal budget, string department = "IT", string? justification = null) =>
        new("PR-2026-0999", "Test request", department, budget, "Alex Demo", justification);
}
