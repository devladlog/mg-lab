using System.Net;
using System.Net.Http.Json;
using TenantApi.Tenancy;

namespace TenantApi.Tests;

public class PlanTests
{
    [Fact]
    public async Task The_plan_limit_stops_one_tenant_and_only_that_tenant()
    {
        using var f = new TenantApiFactory { StarterMaxRequests = 2 }.Start();
        var aw = f.ClientFor(TestTokens.AdventureWorks());
        for (var i = 0; i < 2; i++) Assert.Equal(HttpStatusCode.Created, (await aw.PostAsJsonAsync("/requests", new { title = $"r{i}", amount = 1 })).StatusCode);

        var third = await aw.PostAsJsonAsync("/requests", new { title = "one too many", amount = 1 });
        Assert.Equal(HttpStatusCode.Conflict, third.StatusCode);
        Assert.Contains("starter", await third.Content.ReadAsStringAsync());

        var nw = f.ClientFor(TestTokens.Northwind());
        Assert.Equal(HttpStatusCode.Created, (await nw.PostAsJsonAsync("/requests", new { title = "fine", amount = 1 })).StatusCode);
    }

    [Fact]
    public async Task The_rate_limit_is_per_tenant_shared_by_its_users_and_does_not_touch_other_tenants()
    {
        using var f = new TenantApiFactory { StarterPerMinute = 3 }.Start();
        var alex = f.ClientFor(TestTokens.AdventureWorks(Ids.Alex));
        var riley = f.ClientFor(TestTokens.AdventureWorks(Ids.Riley));

        Assert.Equal(HttpStatusCode.OK, (await alex.GetAsync("/me")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await riley.GetAsync("/me")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await alex.GetAsync("/me")).StatusCode);
        // Three calls from two different users used up Adventure Works' minute.
        Assert.Equal(HttpStatusCode.TooManyRequests, (await riley.GetAsync("/me")).StatusCode);

        // Northwind (business plan) is untouched.
        Assert.Equal(HttpStatusCode.OK, (await f.ClientFor(TestTokens.Northwind()).GetAsync("/me")).StatusCode);
    }

    [Fact]
    public void An_unknown_plan_name_gets_the_smallest_plan_never_unlimited()
    {
        var plans = new PlanCatalog();
        Assert.Equal(plans.Plans["starter"].MaxRequests, plans.For("platinum").MaxRequests);
        Assert.False(plans.IsKnown("platinum"));
        Assert.True(plans.IsKnown("BUSINESS"));
    }
}
