using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Contoso.Orders.Api;

namespace Contoso.Orders.Api.Tests;

public class ApiTests(ApiFactory factory) : IClassFixture<ApiFactory>
{
    private readonly HttpClient _client = factory.CreateClient();

    [Fact]
    public async Task Database_is_created_and_seeded_on_startup()
    {
        var page = await _client.GetFromJsonAsync<Page<Order>>("/orders?page=5");
        Assert.True(page!.Total >= 237);
        Assert.Equal(201, page.Items[0].Id);
    }

    [Fact]
    public async Task Oversized_page_size_is_clamped_and_page_zero_rejected()
    {
        Assert.Equal(100, (await _client.GetFromJsonAsync<Page<Order>>("/orders?pageSize=500"))!.Items.Count);
        Assert.Equal(HttpStatusCode.BadRequest, (await _client.GetAsync("/orders?page=0")).StatusCode);
    }

    [Fact]
    public async Task Post_creates_an_order_that_can_be_read_back()
    {
        var response = await _client.PostAsJsonAsync("/orders", new NewOrder("Alex Demo", 42.50m));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var created = await response.Content.ReadFromJsonAsync<Order>();
        Assert.Equal($"/orders/{created!.Id}", response.Headers.Location?.OriginalString);

        var read = await _client.GetFromJsonAsync<Order>(response.Headers.Location);
        Assert.Equal("Alex Demo", read!.Customer);
        Assert.Equal(42.50m, read.Total);
    }

    [Theory]
    [InlineData(null, 10, "customer")]
    [InlineData("  ", 10, "customer")]
    [InlineData("Fabrikam", 0, "total")]
    public async Task Invalid_orders_are_validation_problems(string? customer, decimal total, string field)
    {
        var response = await _client.PostAsJsonAsync("/orders", new NewOrder(customer, total));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(body.GetProperty("errors").TryGetProperty(field, out _));
    }

    [Fact]
    public async Task Healthz_reports_the_database_provider()
    {
        var body = await _client.GetFromJsonAsync<JsonElement>("/healthz");
        Assert.Equal("ok", body.GetProperty("status").GetString());
        Assert.Equal("Sqlite", body.GetProperty("database").GetString());
    }
}
