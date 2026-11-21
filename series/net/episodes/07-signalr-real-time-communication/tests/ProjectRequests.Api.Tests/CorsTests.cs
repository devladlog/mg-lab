using System.Net;
using System.Net.Http.Json;

namespace ProjectRequests.Api.Tests;

/// <summary>
/// The Blazor WebAssembly client runs in the browser on another origin (http://localhost:5180), so the browser
/// sends a CORS preflight before the POST. Only configured origins get the Access-Control-Allow-Origin header.
/// </summary>
[Trait("Category", "Integration")]
public sealed class CorsTests : IDisposable
{
    private const string BlazorOrigin = "http://localhost:5180";

    private readonly RequestsApiFactory _factory = new(settings: new()
    {
        ["Cors:AllowedOrigins:0"] = BlazorOrigin,
    });

    public void Dispose()
    {
        _factory.Dispose();
        _factory.DeleteDatabase();
    }

    private static HttpRequestMessage Preflight(string origin, string method = "POST")
    {
        var request = new HttpRequestMessage(HttpMethod.Options, "/api/requests");
        request.Headers.Add("Origin", origin);
        request.Headers.Add("Access-Control-Request-Method", method);
        request.Headers.Add("Access-Control-Request-Headers", "content-type");
        return request;
    }

    [Fact]
    public async Task Preflight_from_the_Blazor_origin_is_allowed()
    {
        var response = await _factory.CreateClient().SendAsync(Preflight(BlazorOrigin), Ct);

        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);
        Assert.Equal(BlazorOrigin, Assert.Single(response.Headers.GetValues("Access-Control-Allow-Origin")));
        Assert.Contains("POST", response.Headers.GetValues("Access-Control-Allow-Methods").Single());
    }

    [Theory]
    [InlineData("http://localhost:5181")]            // another port is another origin
    [InlineData("https://localhost:5180")]           // so is another scheme
    public async Task Preflight_from_any_other_origin_gets_no_CORS_headers(string origin)
    {
        var response = await _factory.CreateClient().SendAsync(Preflight(origin), Ct);

        Assert.False(response.Headers.Contains("Access-Control-Allow-Origin"));
    }

    /// <summary>
    /// The server doesn't refuse a DELETE preflight: it answers 204 with the methods it allows, and the BROWSER
    /// compares and blocks. CORS is enforced by browsers; curl or a server-side caller ignores it.
    /// </summary>
    [Fact]
    public async Task Preflight_for_a_method_outside_the_policy_lists_only_the_allowed_methods()
    {
        var response = await _factory.CreateClient().SendAsync(Preflight(BlazorOrigin, "DELETE"), Ct);

        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);
        Assert.Equal("GET,POST,PUT", Assert.Single(response.Headers.GetValues("Access-Control-Allow-Methods")));
    }

    [Fact]
    public async Task Actual_POST_from_the_Blazor_origin_carries_the_header()
    {
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/requests")
        {
            Content = JsonContent.Create(new
            {
                title = "Laptop refresh", budget = 12_000m, requestedBy = "alex.demo@contoso.com", departmentCode = "FIN",
            }),
        };
        request.Headers.Add("Origin", BlazorOrigin);

        var response = await _factory.CreateClient().SendAsync(request, Ct);

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        Assert.Equal(BlazorOrigin, Assert.Single(response.Headers.GetValues("Access-Control-Allow-Origin")));
    }

    // ---- Episode 7: the SignalR hub has its own policy (Learn: SignalR security, CORS) ----

    private static HttpRequestMessage NegotiatePreflight(string origin, string headers = "x-requested-with,x-signalr-user-agent")
    {
        var request = new HttpRequestMessage(HttpMethod.Options, "/hubs/requests/negotiate?negotiateVersion=1");
        request.Headers.Add("Origin", origin);
        request.Headers.Add("Access-Control-Request-Method", "POST");
        request.Headers.Add("Access-Control-Request-Headers", headers);
        return request;
    }

    /// <summary>The hub allows credentials and the client's own headers; the REST policy allows neither.</summary>
    [Fact]
    public async Task Hub_negotiate_preflight_allows_credentials_and_the_SignalR_client_headers()
    {
        var response = await _factory.CreateClient().SendAsync(NegotiatePreflight(BlazorOrigin), Ct);

        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);
        Assert.Equal(BlazorOrigin, Assert.Single(response.Headers.GetValues("Access-Control-Allow-Origin")));
        Assert.Equal("true", Assert.Single(response.Headers.GetValues("Access-Control-Allow-Credentials")));
        Assert.Equal("x-requested-with,x-signalr-user-agent",
            Assert.Single(response.Headers.GetValues("Access-Control-Allow-Headers")));
        Assert.Equal("GET,POST,DELETE", Assert.Single(response.Headers.GetValues("Access-Control-Allow-Methods")));
    }

    [Fact]
    public async Task Rest_preflight_still_uses_the_stricter_default_policy()
    {
        var response = await _factory.CreateClient().SendAsync(Preflight(BlazorOrigin), Ct);

        Assert.False(response.Headers.Contains("Access-Control-Allow-Credentials"));
    }

    [Fact]
    public async Task Hub_preflight_from_another_origin_gets_no_CORS_headers()
    {
        var response = await _factory.CreateClient().SendAsync(NegotiatePreflight("http://localhost:5181"), Ct);

        Assert.False(response.Headers.Contains("Access-Control-Allow-Origin"));
    }
}
