using System.Net;
using System.Net.Http.Json;
using System.Text.Json;

namespace TenantApi.Tests;

public class IsolationTests
{
    static async Task<JsonElement> Post(HttpClient c, string title, decimal amount = 100)
    {
        var r = await c.PostAsJsonAsync("/requests", new { title, amount });
        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        return await r.Content.ReadFromJsonAsync<JsonElement>();
    }

    [Fact]
    public async Task The_tenant_comes_from_the_token_and_the_plan_from_the_catalog()
    {
        using var f = new TenantApiFactory().Start();
        var me = await f.ClientFor(TestTokens.AdventureWorks()).GetFromJsonAsync<JsonElement>("/me");
        Assert.Equal(Ids.AdventureWorks, me.GetProperty("tenantId").GetString());
        Assert.Equal("Adventure Works", me.GetProperty("tenant").GetString());
        Assert.Equal("starter", me.GetProperty("plan").GetString());
        Assert.Equal(Ids.Alex, me.GetProperty("user").GetString());
    }

    [Fact]
    public async Task Each_tenant_lists_only_its_own_rows()
    {
        using var f = new TenantApiFactory().Start();
        var nw = f.ClientFor(TestTokens.Northwind());
        var aw = f.ClientFor(TestTokens.AdventureWorks());
        await Post(nw, "Northwind laptops");
        await Post(nw, "Northwind chairs");
        await Post(aw, "Adventure Works bikes");

        var nwRows = await nw.GetFromJsonAsync<JsonElement[]>("/requests");
        var awRows = await aw.GetFromJsonAsync<JsonElement[]>("/requests");

        Assert.Equal(2, nwRows!.Length);
        Assert.All(nwRows, r => Assert.Equal(Ids.Northwind, r.GetProperty("tenantId").GetString()));
        Assert.Single(awRows!);
        Assert.Equal("Adventure Works bikes", awRows![0].GetProperty("title").GetString());
    }

    [Fact]
    public async Task Another_tenants_id_looks_exactly_like_an_id_that_does_not_exist()
    {
        using var f = new TenantApiFactory().Start();
        var created = await Post(f.ClientFor(TestTokens.Northwind()), "Secret");
        var id = created.GetProperty("id").GetString();

        var own = await f.ClientFor(TestTokens.Northwind()).GetAsync($"/requests/{id}");
        var other = await f.ClientFor(TestTokens.AdventureWorks()).GetAsync($"/requests/{id}");
        var missing = await f.ClientFor(TestTokens.AdventureWorks()).GetAsync($"/requests/{Guid.NewGuid()}");

        Assert.Equal(HttpStatusCode.OK, own.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, other.StatusCode);
        Assert.Equal(missing.StatusCode, other.StatusCode);
    }

    [Fact]
    public async Task Headers_and_body_fields_cannot_choose_the_tenant()
    {
        using var f = new TenantApiFactory().Start();
        var aw = f.ClientFor(TestTokens.AdventureWorks());
        aw.DefaultRequestHeaders.Add("X-Tenant-Id", Ids.Northwind);
        aw.DefaultRequestHeaders.Add("Tenant-Id", Ids.Northwind);

        var r = await aw.PostAsJsonAsync("/requests?tenantId=" + Ids.Northwind, new { title = "Sneaky", amount = 5, tenantId = Ids.Northwind });

        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        var counts = f.RowCounts();
        Assert.Equal(1, counts[Guid.Parse(Ids.AdventureWorks)]);
        Assert.False(counts.ContainsKey(Guid.Parse(Ids.Northwind)));
        var me = await aw.GetFromJsonAsync<JsonElement>("/me");
        Assert.Equal(Ids.AdventureWorks, me.GetProperty("tenantId").GetString());
    }

    [Fact]
    public async Task A_suspended_tenant_is_refused_with_403_even_with_a_valid_token()
    {
        using var f = new TenantApiFactory().Start();
        var r = await f.ClientFor(new TestTokens.Options { Tenant = Ids.Fabrikam }).GetAsync("/requests");
        Assert.Equal(HttpStatusCode.Forbidden, r.StatusCode);
        Assert.Equal("application/problem+json", r.Content.Headers.ContentType?.MediaType);
    }

    [Fact]
    public async Task Created_by_is_the_oid_not_a_name_or_email()
    {
        using var f = new TenantApiFactory().Start();
        var row = await Post(f.ClientFor(TestTokens.Northwind(Ids.Riley)), "Mine");
        Assert.Equal(Ids.Riley, row.GetProperty("createdBy").GetString());
    }

    [Theory]
    [InlineData("", 10)]
    [InlineData("ok", 0)]
    [InlineData("ok", -5)]
    [InlineData("ok", 2000000)]
    public async Task Bad_input_is_a_400_problem(string title, decimal amount)
    {
        using var f = new TenantApiFactory().Start();
        var r = await f.ClientFor(TestTokens.Northwind()).PostAsJsonAsync("/requests", new { title, amount });
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
        Assert.Empty(f.RowCounts());
    }
}
