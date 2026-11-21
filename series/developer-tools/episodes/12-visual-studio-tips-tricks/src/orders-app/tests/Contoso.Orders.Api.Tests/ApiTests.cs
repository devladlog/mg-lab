using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Contoso.Orders.Api;
using Microsoft.AspNetCore.Hosting;

namespace Contoso.Orders.Api.Tests;

public class ApiTests(ApiFactory factory) : IClassFixture<ApiFactory>
{
    private readonly HttpClient _client = factory.CreateClient();

    [Fact, Trait("Category", "Smoke")]
    public async Task Database_is_created_and_seeded_on_startup()
    {
        var page = await _client.GetFromJsonAsync<Page<Order>>("/orders?page=5");
        Assert.True(page!.Total >= 237);
        Assert.Equal(201, page.Items[0].Id);
    }

    [Fact, Trait("Category", "Smoke")]
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
    public async Task Healthz_reports_dev_unless_a_version_is_configured()
    {
        Assert.Equal("dev", (await _client.GetFromJsonAsync<JsonElement>("/healthz")).GetProperty("version").GetString());

        // The image sets App__Version from the Dockerfile ARG; the pipeline checks it after the deploy.
        using var built = factory.WithWebHostBuilder(b => b.UseSetting("App:Version", "3f2c1e0"));
        var body = await built.CreateClient().GetFromJsonAsync<JsonElement>("/healthz");
        Assert.Equal("3f2c1e0", body.GetProperty("version").GetString());
    }

    [Fact]
    public async Task Healthz_reports_the_database_provider()
    {
        var body = await _client.GetFromJsonAsync<JsonElement>("/healthz");
        Assert.Equal("ok", body.GetProperty("status").GetString());
        Assert.Equal("Sqlite", body.GetProperty("database").GetString());
    }

    [Fact]
    public async Task OpenApi_document_lists_every_operation_with_its_responses()
    {
        var doc = await _client.GetFromJsonAsync<JsonElement>("/openapi/v1.json");
        Assert.StartsWith("3.", doc.GetProperty("openapi").GetString());
        var paths = doc.GetProperty("paths");
        Assert.True(paths.GetProperty("/orders").TryGetProperty("get", out var list));
        Assert.True(paths.GetProperty("/orders").TryGetProperty("post", out var create));
        Assert.True(paths.GetProperty("/orders/{id}").TryGetProperty("get", out var read));
        Assert.True(paths.GetProperty("/healthz").TryGetProperty("get", out _));
        Assert.Equal("ListOrders", list.GetProperty("operationId").GetString());
        Assert.True(create.GetProperty("responses").TryGetProperty("201", out _));
        Assert.True(create.GetProperty("responses").TryGetProperty("400", out _));
        Assert.True(read.GetProperty("responses").TryGetProperty("404", out _));
    }

    [Fact]
    public async Task OpenApi_can_be_switched_off()
    {
        using var closed = factory.WithWebHostBuilder(b => b.UseSetting("OpenApi:Enabled", "false"));
        Assert.Equal(HttpStatusCode.NotFound, (await closed.CreateClient().GetAsync("/openapi/v1.json")).StatusCode);
    }
}
