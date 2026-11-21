using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using ProjectRequests.Perf.Api.Json;
using ProjectRequests.Perf.Api.Requests;

namespace ProjectRequests.Perf.Tests;

public class ApiTests
{
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    private static Task<List<RequestDto>?> GetSlow(HttpClient c, string query) =>
        c.GetFromJsonAsync($"/api/slow/requests{query}", AppJsonContext.Default.ListRequestDto, Ct);

    private static Task<PagedResult<RequestDto>?> GetList(HttpClient c, string query) =>
        c.GetFromJsonAsync($"/api/requests{query}", AppJsonContext.Default.PagedResultRequestDto, Ct);

    [Fact]
    public async Task Slow_listing_needs_one_query_plus_two_per_row()
    {
        await using var app = new PerfFactory(enableSlow: true);
        var client = app.CreateClient();

        app.Commands.Reset();
        var rows = await GetSlow(client, "?take=25");

        Assert.Equal(25, rows!.Count);
        Assert.Equal(1 + 2 * 25, app.Commands.Count);     // the N+1 (twice): 51 round trips for 25 rows
    }

    [Fact]
    public async Task Projected_listing_needs_two_queries_whatever_the_page_size()
    {
        await using var app = new PerfFactory();
        var client = app.CreateClient();

        app.Commands.Reset();
        var page = await GetList(client, "?pageSize=100");

        Assert.Equal(100, page!.Items.Count);
        Assert.Equal(300, page.Total);
        Assert.Equal(2, app.Commands.Count);              // COUNT + one SELECT with the JOINs
    }

    [Fact]
    public async Task Slow_and_projected_listings_return_the_same_rows()
    {
        await using var app = new PerfFactory(enableSlow: true);
        var client = app.CreateClient();

        var slow = await GetSlow(client, "?take=40&department=fin");
        var fast = await GetList(client, "?pageSize=40&department=fin");

        Assert.Equal(40, slow!.Count);
        Assert.Equal(slow, fast!.Items);                  // record equality, element by element
    }

    [Fact]
    public async Task Slow_endpoint_is_not_mapped_unless_enabled()
    {
        await using var app = new PerfFactory(enableSlow: false);
        var response = await app.CreateClient().GetAsync("/api/slow/requests", Ct);
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Theory]
    [InlineData("?pageSize=101", "pageSize")]
    [InlineData("?pageSize=0", "pageSize")]
    [InlineData("?page=0", "page")]
    public async Task Unbounded_or_invalid_paging_is_refused(string query, string field)
    {
        await using var app = new PerfFactory();
        var response = await app.CreateClient().GetAsync($"/api/requests{query}", Ct);

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        var problem = await response.Content.ReadFromJsonAsync(AppJsonContext.Default.HttpValidationProblemDetails, Ct);
        Assert.Contains(field, problem!.Errors.Keys);
    }

    [Fact]
    public async Task Json_is_camelCase_with_string_enums_from_the_source_generated_context()
    {
        await using var app = new PerfFactory();
        var json = await app.CreateClient().GetStringAsync("/api/requests?pageSize=1", Ct);

        using var doc = JsonDocument.Parse(json);
        var first = doc.RootElement.GetProperty("items")[0];
        Assert.Equal(JsonValueKind.String, first.GetProperty("priority").ValueKind);
        Assert.Equal(JsonValueKind.String, first.GetProperty("status").ValueKind);
        Assert.True(first.TryGetProperty("createdAtUtc", out _));
        Assert.True(doc.RootElement.TryGetProperty("total", out _));
    }

    private sealed record NotInTheContext(int Id);

    [Fact]
    public async Task A_type_missing_from_the_context_fails_loudly_instead_of_using_reflection()
    {
        await using var app = new PerfFactory();
        var options = app.Services
            .GetRequiredService<Microsoft.Extensions.Options.IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>()
            .Value.SerializerOptions;

        Assert.False(JsonSerializer.IsReflectionEnabledByDefault);
        Assert.Throws<NotSupportedException>(() => { JsonSerializer.Serialize(new NotInTheContext(1), options); });
    }
}
