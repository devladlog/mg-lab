using Contoso.Approvals.Patterns.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;

namespace Contoso.Approvals.Patterns.Tests;

public class RoutingTests
{
    [Theory]
    [InlineData("49999.99", RouteKeys.Standard)]
    [InlineData("50000", RouteKeys.High)]
    [InlineData("249999.99", RouteKeys.High)]
    [InlineData("250000", RouteKeys.Board)]
    public void Route_key_follows_the_policy_boundaries(string budget, string expected) =>
        Assert.Equal(expected, RouteKeys.For(decimal.Parse(budget, System.Globalization.CultureInfo.InvariantCulture), new ApprovalPolicyOptions()));

    [Fact]
    public void Thresholds_come_from_configuration()
    {
        using var sp = TestHost.Provider(TestHost.Config(("Policy:HighThreshold", "10000"), ("Policy:BoardThreshold", "100000")));
        var catalog = sp.GetRequiredService<RouteCatalog>();

        Assert.Equal(RouteKeys.High, catalog.For(TestHost.Request(20_000m)).Key);
        Assert.Equal(RouteKeys.Board, catalog.For(TestHost.Request(100_000m)).Key);
    }

    [Fact]
    public void Each_strategy_has_its_own_roles_and_due_days()
    {
        var policy = Options.Create(new ApprovalPolicyOptions());

        var high = new HighValueRoute(policy).Plan(TestHost.Request(60_000m));
        var board = new BoardRoute(policy).Plan(TestHost.Request(300_000m, justification: "Needed"));

        Assert.Equal([ApproverRole.Manager, ApproverRole.Finance], high.Roles);
        Assert.Equal(10, high.DueInDays);
        Assert.Equal([ApproverRole.Finance, ApproverRole.Board], board.Roles);
        Assert.Equal(20, board.DueInDays);
        Assert.Empty(board.Warnings);
    }

    [Fact]
    public void Board_route_warns_when_the_justification_is_missing()
    {
        var plan = new BoardRoute(Options.Create(new ApprovalPolicyOptions())).Plan(TestHost.Request(300_000m, justification: " "));

        Assert.Equal(["justification required for board requests"], plan.Warnings);
    }

    [Fact]
    public void A_new_strategy_is_one_class_and_one_registration()
    {
        using var sp = TestHost.Provider(extra: s => s.AddSingleton<IApprovalRoute, FastTrackRoute>());

        Assert.Equal(["board", "fast-track", "high", "standard"], sp.GetRequiredService<RouteCatalog>().Keys);
    }

    [Fact]
    public void Two_routes_with_the_same_key_fail_with_both_names()
    {
        using var sp = TestHost.Provider(extra: s => s.AddSingleton<IApprovalRoute, SecondStandardRoute>());

        var ex = Assert.Throws<InvalidOperationException>(() => sp.GetRequiredService<RouteCatalog>());
        Assert.Contains("StandardRoute and SecondStandardRoute", ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void A_missing_route_is_a_clear_error_not_a_null()
    {
        var catalog = new RouteCatalog([new StandardRoute(Options.Create(new ApprovalPolicyOptions()))],
            Options.Create(new ApprovalPolicyOptions()));

        var ex = Assert.Throws<InvalidOperationException>(() => catalog.For(TestHost.Request(300_000m)));
        Assert.Equal("No approval route registered for 'board'. Registered: standard.", ex.Message);
    }

    private sealed class FastTrackRoute : IApprovalRoute
    {
        public string Key => "fast-track";

        public RoutePlan Plan(ProjectRequest request) => new(Key, [ApproverRole.Manager], 1, []);
    }

    private sealed class SecondStandardRoute : IApprovalRoute
    {
        public string Key => RouteKeys.Standard;

        public RoutePlan Plan(ProjectRequest request) => new(Key, [ApproverRole.Manager], 1, []);
    }
}
