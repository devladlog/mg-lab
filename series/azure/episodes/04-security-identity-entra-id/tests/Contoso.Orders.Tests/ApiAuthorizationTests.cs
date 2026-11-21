using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;

namespace Contoso.Orders.Tests;

public class ApiAuthorizationTests(ApiFactory factory) : IClassFixture<ApiFactory>
{
    private static readonly object ValidOrder = new { customer = "Alex Demo", sku = "ABC-123", quantity = 2 };

    private HttpClient Client(string? token = null)
    {
        var c = factory.CreateClient();
        if (token is not null) c.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return c;
    }

    [Fact]
    public async Task Health_is_anonymous() =>
        Assert.Equal(HttpStatusCode.OK, (await Client().GetAsync("/healthz")).StatusCode);

    [Fact]
    public async Task No_token_is_401() =>
        Assert.Equal(HttpStatusCode.Unauthorized, (await Client().GetAsync("/orders")).StatusCode);

    [Fact]
    public async Task User_with_read_scope_can_read() =>
        Assert.Equal(HttpStatusCode.OK, (await Client(TestTokens.User()).GetAsync("/orders")).StatusCode);

    [Fact]
    public async Task User_with_read_scope_cannot_write() =>
        Assert.Equal(HttpStatusCode.Forbidden,
            (await Client(TestTokens.User()).PostAsJsonAsync("/orders", ValidOrder)).StatusCode);

    [Fact]
    public async Task User_with_another_scope_is_403() =>
        Assert.Equal(HttpStatusCode.Forbidden,
            (await Client(TestTokens.User(scp: "Orders.Export")).GetAsync("/orders")).StatusCode);

    [Fact]
    public async Task App_with_write_role_can_write_and_is_recorded()
    {
        var response = await Client(TestTokens.App(["Orders.ReadWrite.All"])).PostAsJsonAsync("/orders", ValidOrder);
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var order = await response.Content.ReadFromJsonAsync<Order>();
        Assert.Equal(TestTokens.ProcessorClientId, order!.CreatedBy);
    }

    [Fact]
    public async Task App_with_write_role_can_read() =>
        Assert.Equal(HttpStatusCode.OK,
            (await Client(TestTokens.App(["Orders.ReadWrite.All"])).GetAsync("/orders")).StatusCode);

    [Fact]
    public async Task User_token_carrying_the_app_role_still_cannot_write()
    {
        // Misconfiguration simulation: the role reached a user token. No idtyp=app, so no write.
        var token = TestTokens.User(roles: ["Orders.ReadWrite.All"]);
        Assert.Equal(HttpStatusCode.Forbidden, (await Client(token).PostAsJsonAsync("/orders", ValidOrder)).StatusCode);
    }

    [Fact]
    public async Task App_with_role_but_without_idtyp_cannot_write() =>
        Assert.Equal(HttpStatusCode.Forbidden,
            (await Client(TestTokens.App(["Orders.ReadWrite.All"], idtyp: false)).PostAsJsonAsync("/orders", ValidOrder)).StatusCode);

    [Fact]
    public async Task Token_without_scp_or_roles_is_rejected()
    {
        // An identity that isn't assigned any app role. Microsoft.Identity.Web refuses tokens with neither claim.
        var response = await Client(TestTokens.App(roles: null)).GetAsync("/orders");
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [Theory]
    [InlineData("api://00000000-0000-0000-0000-000000000000/contoso-orders")] // the App ID URI (what a v1.0 token would carry)
    [InlineData("00000000-0000-0000-0000-0000000000ff")]                      // someone else's API
    public async Task Wrong_audience_is_401(string audience)
    {
        var token = TestTokens.Create(new Dictionary<string, object> { ["scp"] = "Orders.Read" }, audience);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Client(token).GetAsync("/orders")).StatusCode);
    }

    [Fact]
    public async Task Expired_token_is_401()
    {
        var token = TestTokens.Create(new Dictionary<string, object> { ["scp"] = "Orders.Read" },
            expires: DateTime.UtcNow.AddMinutes(-10));
        Assert.Equal(HttpStatusCode.Unauthorized, (await Client(token).GetAsync("/orders")).StatusCode);
    }

    [Fact]
    public async Task Token_signed_with_another_key_is_401()
    {
        var token = TestTokens.Create(new Dictionary<string, object> { ["scp"] = "Orders.Read" }, wrongKey: true);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Client(token).GetAsync("/orders")).StatusCode);
    }

    [Fact]
    public async Task Me_tells_app_and_user_tokens_apart()
    {
        var app = await Client(TestTokens.App(["Orders.ReadWrite.All"])).GetFromJsonAsync<Dictionary<string, object>>("/me");
        var user = await Client(TestTokens.User()).GetFromJsonAsync<Dictionary<string, object>>("/me");
        Assert.Equal("app-only", app!["kind"].ToString());
        Assert.Equal("delegated", user!["kind"].ToString());
        Assert.Equal("Orders.Read", user["scopes"].ToString());
    }

    [Fact]
    public async Task Invalid_order_is_400_for_an_authorized_app() =>
        Assert.Equal(HttpStatusCode.BadRequest,
            (await Client(TestTokens.App(["Orders.ReadWrite.All"])).PostAsJsonAsync("/orders",
                new { customer = "", sku = "ABC-123", quantity = 0 })).StatusCode);
}
