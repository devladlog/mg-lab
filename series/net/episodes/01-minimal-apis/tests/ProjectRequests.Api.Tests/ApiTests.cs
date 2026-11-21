using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;

namespace ProjectRequests.Api.Tests;

/// <summary>
/// Integration tests: the real pipeline (routing, validation, filters, problem details, OpenAPI) in memory.
/// No "public partial class Program" needed: .NET 10 generates it.
/// </summary>
public class ApiTests(WebApplicationFactory<Program> factory) : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly HttpClient _client = factory.CreateClient();

    private static object NewRequest(decimal budget = 75_000m, string? justification = null) => new
    {
        title = "CRM rollout " + Guid.NewGuid().ToString("N")[..6],
        budget,
        requestedBy = "alex.demo@contoso.com",
        justification,
    };

    private static async Task<JsonElement> Json(HttpResponseMessage response) =>
        JsonDocument.Parse(await response.Content.ReadAsStringAsync()).RootElement;

    [Fact]
    public async Task Post_valid_request_returns_201_with_location_and_high_priority()
    {
        var response = await _client.PostAsJsonAsync("/api/requests", NewRequest(75_000m));

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var body = await Json(response);
        Assert.Equal($"/api/requests/{body.GetProperty("id").GetInt32()}", response.Headers.Location!.OriginalString);
        Assert.Equal("High", body.GetProperty("priority").GetString());   // enums serialised as strings

        var get = await _client.GetAsync(response.Headers.Location);
        Assert.Equal(HttpStatusCode.OK, get.StatusCode);
    }

    [Fact]
    public async Task Post_invalid_request_returns_400_validation_problem()
    {
        var response = await _client.PostAsJsonAsync("/api/requests",
            new { title = "x", budget = 0, requestedBy = "not-an-email" });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType!.MediaType);
        var errors = (await Json(response)).GetProperty("errors");
        Assert.True(errors.TryGetProperty("Title", out _));
        Assert.True(errors.TryGetProperty("Budget", out _));
        Assert.True(errors.TryGetProperty("RequestedBy", out _));
    }

    [Fact]
    public async Task Big_budget_without_justification_fails_the_cross_field_rule()
    {
        var response = await _client.PostAsJsonAsync("/api/requests", NewRequest(300_000m));

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        var errors = (await Json(response)).GetProperty("errors");
        Assert.Equal("A justification is required for budgets of 250,000 or more.",
            errors.GetProperty("Justification")[0].GetString());

        var ok = await _client.PostAsJsonAsync("/api/requests", NewRequest(300_000m, "Replaces three legacy systems."));
        Assert.Equal(HttpStatusCode.Created, ok.StatusCode);
    }

    [Fact]
    public async Task Cross_field_rule_only_runs_after_the_attributes_pass()
    {
        // Gotcha we hit: IValidatableObject.Validate is skipped while any attribute fails,
        // so the client sees the Justification error only on the next attempt.
        var response = await _client.PostAsJsonAsync("/api/requests",
            new { title = "x", budget = 300_000, requestedBy = "alex.demo@contoso.com" });

        var errors = (await Json(response)).GetProperty("errors");
        Assert.True(errors.TryGetProperty("Title", out _));
        Assert.False(errors.TryGetProperty("Justification", out _));
    }

    [Fact]
    public async Task Unknown_id_returns_404_problem_details()
    {
        var response = await _client.GetAsync("/api/requests/987654");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType!.MediaType);
    }

    [Fact]
    public async Task Decision_flow_approves_then_returns_409()
    {
        var created = await Json(await _client.PostAsJsonAsync("/api/requests", NewRequest()));
        var url = $"/api/requests/{created.GetProperty("id").GetInt32()}/decision";
        var decision = new { approve = true, decidedBy = "sam.approver@contoso.com" };

        var first = await _client.PostAsJsonAsync(url, decision);
        Assert.Equal(HttpStatusCode.OK, first.StatusCode);
        Assert.Equal("Approved", (await Json(first)).GetProperty("status").GetString());

        var second = await _client.PostAsJsonAsync(url, decision);
        Assert.Equal(HttpStatusCode.Conflict, second.StatusCode);
        Assert.Equal("Request already decided.", (await Json(second)).GetProperty("title").GetString());
    }

    [Fact]
    public async Task Decision_without_approve_flag_is_a_validation_error()
    {
        var created = await Json(await _client.PostAsJsonAsync("/api/requests", NewRequest()));
        var response = await _client.PostAsJsonAsync(
            $"/api/requests/{created.GetProperty("id").GetInt32()}/decision",
            new { decidedBy = "sam.approver@contoso.com" });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.True((await Json(response)).GetProperty("errors").TryGetProperty("Approve", out _));
    }

    [Fact]
    public async Task List_can_filter_by_priority_string()
    {
        await _client.PostAsJsonAsync("/api/requests", NewRequest(1_000m));
        var high = await Json(await _client.GetAsync("/api/requests?priority=High"));

        Assert.NotEqual(0, high.GetArrayLength());
        Assert.All(high.EnumerateArray(), r => Assert.Equal("High", r.GetProperty("priority").GetString()));
    }

    [Fact]
    public async Task Read_only_mode_blocks_writes_with_503_but_reads_still_work()
    {
        using var readOnly = factory.WithWebHostBuilder(b => b.UseSetting("Api:ReadOnly", "true"));
        var client = readOnly.CreateClient();

        var post = await client.PostAsJsonAsync("/api/requests", NewRequest());
        Assert.Equal(HttpStatusCode.ServiceUnavailable, post.StatusCode);
        Assert.Equal("120", post.Headers.GetValues("Retry-After").Single());
        Assert.Equal("The API is in read-only mode.", (await Json(post)).GetProperty("title").GetString());

        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/api/requests")).StatusCode);
    }

    [Fact]
    public async Task OpenApi_document_describes_every_status_code_in_development()
    {
        var doc = await Json(await _client.GetAsync("/openapi/v1.json"));   // the factory runs as Development

        Assert.StartsWith("3.1", doc.GetProperty("openapi").GetString());
        var paths = doc.GetProperty("paths");
        var get = paths.GetProperty("/api/requests/{id}").GetProperty("get").GetProperty("responses");
        Assert.True(get.TryGetProperty("200", out _));
        Assert.True(get.TryGetProperty("404", out _));             // from Results<Ok<T>, NotFound>

        var post = paths.GetProperty("/api/requests").GetProperty("post").GetProperty("responses");
        Assert.True(post.TryGetProperty("201", out _));
        Assert.True(post.TryGetProperty("400", out _));            // ProducesValidationProblem on the group
        Assert.True(post.TryGetProperty("503", out _));            // ProducesProblem(503) on the group

        var decide = paths.GetProperty("/api/requests/{id}/decision").GetProperty("post").GetProperty("responses");
        Assert.True(decide.TryGetProperty("409", out _));          // ProblemHttpResult needs ProducesProblem(409)
    }

    [Fact]
    public async Task OpenApi_document_is_not_exposed_in_production()
    {
        using var prod = factory.WithWebHostBuilder(b => b.UseEnvironment("Production"));
        var response = await prod.CreateClient().GetAsync("/openapi/v1.json");
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Health_endpoint_reports_healthy()
    {
        Assert.Equal("Healthy", await _client.GetStringAsync("/healthz"));
    }
}
