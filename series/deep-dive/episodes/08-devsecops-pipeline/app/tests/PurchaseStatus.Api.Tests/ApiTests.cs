using System.Net;
using System.Net.Http.Json;
using Contoso.PurchaseStatus;
using Microsoft.AspNetCore.Mvc.Testing;

namespace PurchaseStatus.Api.Tests;

public class ApiTests(WebApplicationFactory<Program> factory) : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly HttpClient _client = factory.CreateClient();

    [Fact]
    public async Task Healthz_is_ok()
    {
        var response = await _client.GetAsync("/healthz");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task A_known_request_returns_its_status_and_is_not_cacheable()
    {
        var response = await _client.GetAsync("/api/status/PR-1002");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("no-store", response.Headers.CacheControl?.ToString());
        Assert.Contains("nosniff", response.Headers.GetValues("X-Content-Type-Options"));
        var body = await response.Content.ReadFromJsonAsync<Contoso.PurchaseStatus.PurchaseStatus>();
        Assert.Equal("WaitingForFinance", body!.State);
        Assert.Equal(7380m, body.Total);
    }

    [Fact]
    public async Task An_unknown_request_is_404()
    {
        Assert.Equal(HttpStatusCode.NotFound, (await _client.GetAsync("/api/status/PR-9999")).StatusCode);
    }

    [Theory]
    [InlineData("PR-1")]
    [InlineData("1001")]
    [InlineData("PR-1001'%20OR%201=1")]
    public async Task A_malformed_id_is_400(string id)
    {
        Assert.Equal(HttpStatusCode.BadRequest, (await _client.GetAsync($"/api/status/{id}")).StatusCode);
    }

    [Fact]
    public async Task The_server_header_is_not_sent()
    {
        var response = await _client.GetAsync("/healthz");
        Assert.False(response.Headers.Contains("Server"));
    }
}
