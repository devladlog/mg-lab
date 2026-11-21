using Contoso.Approvals.Patterns.Events;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Options;

namespace Contoso.Approvals.Patterns.Tests;

public class LifetimeAndOptionsTests
{
    [Fact]
    public void The_real_composition_root_passes_scope_and_build_validation()
    {
        using var sp = TestHost.Provider(); // ValidateScopes + ValidateOnBuild: throws if anything is miswired
        using var scope = sp.CreateScope();

        Assert.NotNull(scope.ServiceProvider.GetRequiredService<ApprovalService>());
    }

    [Fact]
    public async Task Gotcha_captive_dependency_in_Production_runs_and_loses_the_audit()
    {
        var builder = TestHost.HostBuilder(Environments.Production, TestHost.Config());
        builder.Services.AddApprovalCore(builder.Configuration).AddObserversWithCaptiveAudit();
        using var host = builder.Build(); // no validation in Production: no exception

        using var scope = host.Services.CreateScope();
        await scope.ServiceProvider.GetRequiredService<ApprovalService>().SubmitAsync(TestHost.Request(1_000m));

        Assert.Empty(scope.ServiceProvider.GetRequiredService<AuditTrail>().Entries); // the entry went to the root scope's trail
    }

    [Fact]
    public void Gotcha_captive_dependency_in_Development_fails_at_build()
    {
        var builder = TestHost.HostBuilder(Environments.Development, TestHost.Config());
        builder.Services.AddApprovalCore(builder.Configuration).AddObserversWithCaptiveAudit();

        var ex = Assert.Throws<AggregateException>(() => builder.Build());
        Assert.Contains(
            "Cannot consume scoped service 'Contoso.Approvals.Patterns.Events.AuditTrail' from singleton 'Contoso.Approvals.Patterns.Events.IRequestObserver'",
            ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task ValidateOnStart_stops_the_host_on_an_impossible_policy()
    {
        var builder = TestHost.HostBuilder(Environments.Production, TestHost.Config(("Policy:BoardThreshold", "10000")));
        builder.Services.AddApprovals(builder.Configuration);
        using var host = builder.Build();

        var ex = await Assert.ThrowsAsync<OptionsValidationException>(() => host.StartAsync());
        Assert.Equal("Policy:BoardThreshold must be greater than Policy:HighThreshold.", ex.Message);
    }

    [Fact]
    public async Task Data_annotations_are_checked_at_start_too()
    {
        var builder = TestHost.HostBuilder(Environments.Production, TestHost.Config(("Policy:BoardDueDays", "0")));
        builder.Services.AddApprovals(builder.Configuration);
        using var host = builder.Build();

        var ex = await Assert.ThrowsAsync<OptionsValidationException>(() => host.StartAsync());
        Assert.Contains("'BoardDueDays' with the error: 'The field BoardDueDays must be between 1 and 90.'", ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Without_a_host_start_bad_options_only_fail_on_first_use()
    {
        using var sp = TestHost.Provider(TestHost.Config(("Policy:BoardThreshold", "10000"))); // builds fine

        var options = sp.GetRequiredService<IOptions<ApprovalPolicyOptions>>();
        Assert.Throws<OptionsValidationException>(() => options.Value);
    }
}
