using System.Net;
using Azure.Core;
using Contoso.Orders.Client;

namespace Contoso.Orders.Tests;

public class ClientTests
{
    private sealed class FakeCredential : TokenCredential
    {
        public List<string[]> Requests { get; } = [];

        public override AccessToken GetToken(TokenRequestContext ctx, CancellationToken ct) =>
            GetTokenAsync(ctx, ct).AsTask().Result;

        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext ctx, CancellationToken ct)
        {
            Requests.Add(ctx.Scopes);
            return ValueTask.FromResult(new AccessToken($"token-{Requests.Count}", DateTimeOffset.UtcNow.AddHours(1)));
        }
    }

    private sealed class Capture : HttpMessageHandler
    {
        public List<string?> Authorization { get; } = [];

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Authorization.Add(request.Headers.Authorization?.ToString());
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK));
        }
    }

    private const string Scope = "api://00000000-0000-0000-0000-000000000000/contoso-orders/.default";

    [Fact]
    public async Task Adds_a_bearer_token_for_the_default_scope()
    {
        var credential = new FakeCredential();
        var capture = new Capture();
        using var http = new HttpClient(new EntraTokenHandler(credential, Scope) { InnerHandler = capture });

        await http.GetAsync("https://orders.example.invalid/orders");
        await http.GetAsync("https://orders.example.invalid/orders");

        Assert.Equal(["Bearer token-1", "Bearer token-2"], capture.Authorization);
        Assert.All(credential.Requests, s => Assert.Equal([Scope], s));
    }

    [Theory]
    [InlineData("api://00000000-0000-0000-0000-000000000000/contoso-orders/Orders.ReadWrite.All")]
    [InlineData("api://00000000-0000-0000-0000-000000000000/contoso-orders")]
    public void Refuses_a_scope_without_default(string scope) =>
        Assert.Throws<ArgumentException>(() => new EntraTokenHandler(new FakeCredential(), scope));

    [Fact]
    public async Task Client_token_works_end_to_end_against_the_api()
    {
        // The real handler + a credential that returns an app-only test token -> 201 from the real API pipeline.
        using var factory = new ApiFactory();
        var credential = new StaticCredential(TestTokens.App(["Orders.ReadWrite.All"]));
        var handler = new EntraTokenHandler(credential, Scope) { InnerHandler = factory.Server.CreateHandler() };
        using var http = new HttpClient(handler) { BaseAddress = factory.Server.BaseAddress };

        var response = await http.PostAsync("/orders", JsonContent("""{"customer":"Alex Demo","sku":"ABC-123","quantity":1}"""));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
    }

    private static StringContent JsonContent(string json) => new(json, System.Text.Encoding.UTF8, "application/json");

    private sealed class StaticCredential(string token) : TokenCredential
    {
        public override AccessToken GetToken(TokenRequestContext ctx, CancellationToken ct) =>
            new(token, DateTimeOffset.UtcNow.AddHours(1));

        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext ctx, CancellationToken ct) =>
            ValueTask.FromResult(GetToken(ctx, ct));
    }
}
