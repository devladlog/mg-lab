using System.Net;

namespace TenantApi.Tests;

public class AuthenticationTests
{
    static async Task<HttpStatusCode> Status(TenantApiFactory f, TestTokens.Options? who) =>
        (await f.ClientFor(who).GetAsync("/me")).StatusCode;

    [Fact]
    public async Task No_token_is_401()
    {
        using var f = new TenantApiFactory().Start();
        Assert.Equal(HttpStatusCode.Unauthorized, await Status(f, null));
    }

    [Fact]
    public async Task A_tenant_that_is_not_onboarded_is_401_even_with_a_perfectly_signed_token()
    {
        using var f = new TenantApiFactory().Start();
        Assert.Equal(HttpStatusCode.Unauthorized, await Status(f, new TestTokens.Options { Tenant = Ids.NotOnboarded }));
    }

    [Fact]
    public async Task The_issuer_must_belong_to_the_tenant_in_the_tid_claim()
    {
        using var f = new TenantApiFactory().Start();
        // tid says Northwind, issuer says Adventure Works: the shape of an attempt to borrow another tenant's identity.
        var forged = new TestTokens.Options { Tenant = Ids.Northwind, Issuer = $"https://login.microsoftonline.com/{Ids.AdventureWorks}/v2.0" };
        Assert.Equal(HttpStatusCode.Unauthorized, await Status(f, forged));
    }

    [Fact]
    public async Task An_issuer_on_another_host_is_refused_even_for_an_onboarded_tenant()
    {
        using var f = new TenantApiFactory().Start();
        var other = new TestTokens.Options { Issuer = $"https://login.example.invalid/{Ids.Northwind}/v2.0" };
        Assert.Equal(HttpStatusCode.Unauthorized, await Status(f, other));
    }

    [Fact]
    public async Task Version_1_tokens_are_refused()
    {
        using var f = new TenantApiFactory().Start();
        Assert.Equal(HttpStatusCode.Unauthorized, await Status(f, new TestTokens.Options { Version = 1 }));
    }

    [Fact]
    public async Task A_token_for_another_api_is_refused()
    {
        using var f = new TenantApiFactory().Start();
        Assert.Equal(HttpStatusCode.Unauthorized, await Status(f, new TestTokens.Options { Audience = "00000000-0000-0000-0000-0000000000ee" }));
    }

    [Fact]
    public async Task A_token_signed_by_another_key_is_refused()
    {
        using var f = new TenantApiFactory().Start();
        Assert.Equal(HttpStatusCode.Unauthorized, await Status(f, new TestTokens.Options { WrongKey = true }));
    }

    [Fact]
    public async Task Without_the_delegated_scope_the_answer_is_403()
    {
        using var f = new TenantApiFactory().Start();
        Assert.Equal(HttpStatusCode.Forbidden, await Status(f, new TestTokens.Options { Scope = null }));
        Assert.Equal(HttpStatusCode.Forbidden, await Status(f, new TestTokens.Options { Scope = "Other.Scope" }));
    }

    [Fact]
    public async Task Health_is_open()
    {
        using var f = new TenantApiFactory().Start();
        Assert.Equal(HttpStatusCode.OK, (await f.ClientFor(null).GetAsync("/healthz")).StatusCode);
    }
}
