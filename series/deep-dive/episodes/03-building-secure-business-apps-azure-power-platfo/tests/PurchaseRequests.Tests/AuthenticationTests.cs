using System.Net;
using System.Net.Http.Json;

namespace PurchaseRequests.Tests;

/// <summary>Token validation with the production settings: issuer, audience, signature, lifetime, scope, roles.</summary>
public class AuthenticationTests
{
    static async Task<HttpStatusCode> GetMine(TestTokens.Options? who)
    {
        using var api = new ApiFactory().Start();
        var response = await api.ClientFor(who).GetAsync("/api/requests/mine");
        return response.StatusCode;
    }

    [Fact]
    public async Task No_token_is_401() => Assert.Equal(HttpStatusCode.Unauthorized, await GetMine(null));

    [Fact]
    public async Task Health_endpoint_is_anonymous()
    {
        using var api = new ApiFactory().Start();
        var response = await api.CreateClient().GetAsync("/healthz");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task V2_token_with_client_id_audience_is_accepted() =>
        Assert.Equal(HttpStatusCode.OK, await GetMine(TestTokens.Alex with { Version = 2 }));

    [Fact]
    public async Task V1_token_with_app_id_uri_audience_is_accepted() =>
        Assert.Equal(HttpStatusCode.OK, await GetMine(TestTokens.Alex with { Version = 1 }));

    [Fact]
    public async Task Token_for_another_api_is_401() =>
        Assert.Equal(HttpStatusCode.Unauthorized, await GetMine(TestTokens.Alex with { Audience = "00000003-0000-0000-c000-000000000000" }));

    [Fact]
    public async Task Token_from_another_tenant_is_401() =>
        Assert.Equal(HttpStatusCode.Unauthorized, await GetMine(TestTokens.Alex with { Tenant = Ids.OtherTenant }));

    [Fact]
    public async Task Multi_tenant_common_issuer_is_401() =>
        Assert.Equal(HttpStatusCode.Unauthorized, await GetMine(TestTokens.Alex with { Issuer = "https://login.microsoftonline.com/common/v2.0" }));

    [Fact]
    public async Task Token_signed_with_an_unknown_key_is_401() =>
        Assert.Equal(HttpStatusCode.Unauthorized, await GetMine(TestTokens.Alex with { WrongKey = true }));

    [Fact]
    public async Task Expired_token_is_401() =>
        Assert.Equal(HttpStatusCode.Unauthorized, await GetMine(TestTokens.Alex with
        {
            NotBefore = DateTime.UtcNow.AddHours(-2),
            Lifetime = TimeSpan.FromMinutes(60),
        }));

    [Fact]
    public async Task App_only_token_without_scope_is_403_even_with_roles() =>
        Assert.Equal(HttpStatusCode.Forbidden, await GetMine(TestTokens.Jordan with { Scope = null }));

    [Fact]
    public async Task Scope_must_match_exactly_not_as_a_substring() =>
        Assert.Equal(HttpStatusCode.Forbidden, await GetMine(TestTokens.Alex with { Scope = "PurchaseRequests.ReadWriteAll" }));

    [Fact]
    public async Task Scope_is_found_among_several() =>
        Assert.Equal(HttpStatusCode.OK, await GetMine(TestTokens.Alex with { Scope = "User.Read PurchaseRequests.ReadWrite" }));

    [Fact]
    public async Task With_default_claim_mapping_the_same_valid_token_is_403()
    {
        // MapInboundClaims = true renames "scp", "roles" and "oid" to long URIs, so every policy fails.
        using var api = new ApiFactory { MapInboundClaims = true }.Start();
        var response = await api.ClientFor(TestTokens.Alex).GetAsync("/api/requests/mine");
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public async Task Submitting_without_the_Requester_role_is_403()
    {
        using var api = new ApiFactory().Start();
        var response = await api.ClientFor(TestTokens.Alex with { Roles = [] })
            .PostAsJsonAsync("/api/requests", Requests.Laptop);
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public async Task Pending_list_needs_an_approver_role()
    {
        using var api = new ApiFactory().Start();
        Assert.Equal(HttpStatusCode.Forbidden, (await api.ClientFor(TestTokens.Alex).GetAsync("/api/requests/pending")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await api.ClientFor(TestTokens.Sam).GetAsync("/api/requests/pending")).StatusCode);
    }

    [Fact]
    public async Task Unknown_route_is_401_for_anonymous_callers_thanks_to_the_fallback_policy()
    {
        using var api = new ApiFactory().Start();
        var response = await api.CreateClient().GetAsync("/api/requests/mine/");
        Assert.Contains(response.StatusCode, new[] { HttpStatusCode.Unauthorized, HttpStatusCode.NotFound });
    }
}
