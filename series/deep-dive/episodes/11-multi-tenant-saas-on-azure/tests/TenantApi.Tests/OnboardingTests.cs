using System.Net;
using System.Net.Http.Json;
using System.Text.Json;

namespace TenantApi.Tests;

public class OnboardingTests
{
    [Fact]
    public async Task A_platform_admin_in_the_home_tenant_can_onboard_and_the_tenant_works_at_once()
    {
        using var f = new TenantApiFactory().Start();
        var newTenant = new TestTokens.Options { Tenant = Ids.NotOnboarded };
        Assert.Equal(HttpStatusCode.Unauthorized, (await f.ClientFor(newTenant).GetAsync("/me")).StatusCode);   // also primes the "unknown" cache entry

        var put = await f.ClientFor(TestTokens.Admin).PutAsJsonAsync($"/admin/tenants/{Ids.NotOnboarded}", new { name = "Wide World Importers", plan = "business" });
        Assert.Equal(HttpStatusCode.Created, put.StatusCode);

        var me = await f.ClientFor(newTenant).GetFromJsonAsync<JsonElement>("/me");
        Assert.Equal("Wide World Importers", me.GetProperty("tenant").GetString());
        Assert.Equal("business", me.GetProperty("plan").GetString());
    }

    [Fact]
    public async Task Suspending_a_tenant_takes_effect_on_the_next_call()
    {
        using var f = new TenantApiFactory().Start();
        var nw = f.ClientFor(TestTokens.Northwind());
        Assert.Equal(HttpStatusCode.OK, (await nw.GetAsync("/me")).StatusCode);

        var put = await f.ClientFor(TestTokens.Admin).PutAsJsonAsync($"/admin/tenants/{Ids.Northwind}", new { name = "Northwind Traders", plan = "business", status = "suspended" });
        Assert.Equal(HttpStatusCode.OK, put.StatusCode);

        Assert.Equal(HttpStatusCode.Forbidden, (await nw.GetAsync("/me")).StatusCode);
    }

    [Fact]
    public async Task Platform_Admin_in_a_CUSTOMER_tenant_proves_nothing()
    {
        using var f = new TenantApiFactory().Start();
        // A customer's admin can assign any app role of ours to their own users. The role is only trusted from the home tenant.
        var customerAdmin = new TestTokens.Options { Tenant = Ids.Northwind, Roles = ["Platform.Admin"] };
        var r = await f.ClientFor(customerAdmin).GetAsync("/admin/tenants");
        Assert.Equal(HttpStatusCode.Forbidden, r.StatusCode);
    }

    [Fact]
    public async Task Home_tenant_users_without_the_role_are_refused()
    {
        using var f = new TenantApiFactory().Start();
        var r = await f.ClientFor(new TestTokens.Options { Tenant = Ids.Home }).GetAsync("/admin/tenants");
        Assert.Equal(HttpStatusCode.Forbidden, r.StatusCode);
    }

    [Fact]
    public async Task The_home_tenant_signs_in_but_is_not_a_customer()
    {
        using var f = new TenantApiFactory().Start();
        var staff = f.ClientFor(new TestTokens.Options { Tenant = Ids.Home });
        Assert.Equal(HttpStatusCode.Forbidden, (await staff.GetAsync("/me")).StatusCode);   // token valid, no tenant data for it
        Assert.Equal(HttpStatusCode.Forbidden, (await staff.GetAsync("/requests")).StatusCode);
    }

    [Theory]
    [InlineData("", "starter", "active")]
    [InlineData("X", "platinum", "active")]
    [InlineData("X", "starter", "deleted")]
    public async Task Onboarding_input_is_validated(string name, string plan, string status)
    {
        using var f = new TenantApiFactory().Start();
        var r = await f.ClientFor(TestTokens.Admin).PutAsJsonAsync($"/admin/tenants/{Ids.NotOnboarded}", new { name, plan, status });
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
    }

    [Fact]
    public async Task Customer_tenants_never_see_the_catalog_through_the_tenant_api()
    {
        using var f = new TenantApiFactory().Start();
        var rows = await f.ClientFor(TestTokens.Northwind()).GetFromJsonAsync<JsonElement[]>("/requests");
        Assert.Empty(rows!);
        Assert.Equal(HttpStatusCode.NotFound, (await f.ClientFor(TestTokens.Northwind()).GetAsync("/tenants")).StatusCode);
    }
}
