using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Contoso.Orders.Api;
using Microsoft.AspNetCore.Mvc.Testing;

namespace Contoso.Orders.Api.Tests;

public class ApiTests(WebApplicationFactory<Program> factory) : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly HttpClient _client = factory.CreateClient();

    [Fact]
    public async Task Orders_default_to_the_first_page_of_fifty()
    {
        var page = await _client.GetFromJsonAsync<Page<Order>>("/orders");
        Assert.NotNull(page);
        Assert.Equal(1, page.PageNumber);
        Assert.Equal(50, page.Items.Count);
        Assert.Equal(237, page.Total);
    }

    [Fact]
    public async Task Oversized_page_size_is_clamped()
    {
        var page = await _client.GetFromJsonAsync<Page<Order>>("/orders?pageSize=500");
        Assert.Equal(100, page!.Items.Count);
    }

    [Fact]
    public async Task Page_zero_is_a_validation_problem()
    {
        var response = await _client.GetAsync("/orders?page=0");
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType?.MediaType);
        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(body.GetProperty("errors").TryGetProperty("page", out _));
    }

    [Fact]
    public async Task Single_order_and_not_found()
    {
        var order = await _client.GetFromJsonAsync<Order>("/orders/7");
        Assert.Equal(7, order!.Id);
        Assert.Equal(HttpStatusCode.NotFound, (await _client.GetAsync("/orders/9999")).StatusCode);
    }

    [Fact]
    public async Task Healthz_reports_runtime_and_os()
    {
        var body = await _client.GetFromJsonAsync<JsonElement>("/healthz");
        Assert.Equal("ok", body.GetProperty("status").GetString());
        Assert.StartsWith(".NET 10", body.GetProperty("dotnet").GetString());
        Assert.False(string.IsNullOrWhiteSpace(body.GetProperty("os").GetString()));
    }

    [Fact]
    public async Task Healthz_says_when_it_runs_in_a_dotnet_container_image()
    {
        var before = Environment.GetEnvironmentVariable("DOTNET_RUNNING_IN_CONTAINER");
        try
        {
            Environment.SetEnvironmentVariable("DOTNET_RUNNING_IN_CONTAINER", "true");   // what the image sets
            var body = await _client.GetFromJsonAsync<JsonElement>("/healthz");
            Assert.True(body.GetProperty("inContainer").GetBoolean());
        }
        finally
        {
            Environment.SetEnvironmentVariable("DOTNET_RUNNING_IN_CONTAINER", before);
        }
    }
}
