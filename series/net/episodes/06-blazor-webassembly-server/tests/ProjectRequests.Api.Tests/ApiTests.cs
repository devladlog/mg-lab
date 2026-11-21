using System.Net;
using System.Net.Http.Json;
using System.Text.Json;

namespace ProjectRequests.Api.Tests;

/// <summary>Integration tests: HTTP in, EF Core and a real SQLite database underneath.</summary>
public sealed class ApiTests : IDisposable
{
    private readonly RequestsApiFactory _factory = new();
    private readonly HttpClient _client;

    public ApiTests() => _client = _factory.CreateClient();

    public void Dispose()
    {
        _factory.Dispose();
        _factory.DeleteDatabase();
    }

    private static object NewRequest(decimal budget = 40_000m, string department = "FIN",
        string requestedBy = "alex.demo@contoso.com", string? justification = null) => new
    {
        title = "Laptop refresh",
        budget,
        requestedBy,
        departmentCode = department,
        justification,
    };

    private static async Task<JsonElement> Json(HttpResponseMessage response) =>
        JsonDocument.Parse(await response.Content.ReadAsStringAsync()).RootElement;

    private async Task<JsonElement> Create(decimal budget = 40_000m, string department = "FIN")
    {
        var response = await _client.PostAsJsonAsync("/api/requests", NewRequest(budget, department));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        return await Json(response);
    }

    [Fact]
    public async Task Create_returns_201_with_department_priority_and_version()
    {
        var response = await _client.PostAsJsonAsync("/api/requests", NewRequest(75_000m, "it"), Ct);

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var body = await Json(response);
        Assert.Equal($"/api/requests/{body.GetProperty("id").GetInt32()}", response.Headers.Location!.OriginalString);
        Assert.Equal("IT", body.GetProperty("department").GetString());
        Assert.Equal("High", body.GetProperty("priority").GetString());
        Assert.NotEqual(Guid.Empty, body.GetProperty("version").GetGuid());

        var get = await Json(await _client.GetAsync(response.Headers.Location, Ct));
        Assert.Equal(body.GetProperty("version").GetGuid(), get.GetProperty("version").GetGuid());
        Assert.EndsWith("Z", get.GetProperty("createdAtUtc").GetString());   // read back from the database as UTC
    }

    [Fact]
    public async Task Unknown_department_is_a_400_validation_problem()
    {
        var response = await _client.PostAsJsonAsync("/api/requests", NewRequest(department: "HR"), Ct);

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType!.MediaType);
        Assert.True((await Json(response)).GetProperty("errors").TryGetProperty("DepartmentCode", out _));
    }

    [Fact]
    public async Task Big_budget_still_needs_a_justification()
    {
        var response = await _client.PostAsJsonAsync("/api/requests", NewRequest(300_000m), Ct);

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.True((await Json(response)).GetProperty("errors").TryGetProperty("Justification", out _));
    }

    [Fact]
    public async Task List_filters_by_department_regardless_of_case_and_by_priority()
    {
        await Create(10_000m, "FIN");
        await Create(90_000m, "FIN");
        await Create(90_000m, "OPS");

        var fin = await Json(await _client.GetAsync("/api/requests?department=fin", Ct));
        var finHigh = await Json(await _client.GetAsync("/api/requests?department=Fin&priority=High", Ct));

        Assert.Equal(2, fin.GetArrayLength());
        Assert.Equal(1, finHigh.GetArrayLength());
        Assert.Equal(90_000m, finHigh[0].GetProperty("budget").GetDecimal());
    }

    [Fact]
    public async Task Budget_update_recomputes_priority_and_issues_a_new_version()
    {
        var created = await Create(40_000m);
        var id = created.GetProperty("id").GetInt32();
        var v1 = created.GetProperty("version").GetGuid();

        var response = await _client.PutAsJsonAsync($"/api/requests/{id}/budget", new { budget = 60_000m, version = v1 }, Ct);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var updated = await Json(response);
        Assert.Equal("High", updated.GetProperty("priority").GetString());
        Assert.NotEqual(v1, updated.GetProperty("version").GetGuid());
    }

    [Fact]
    public async Task Approving_a_version_that_changed_is_a_409_and_nothing_is_approved()
    {
        var created = await Create(40_000m);
        var id = created.GetProperty("id").GetInt32();
        var seenByApprover = created.GetProperty("version").GetGuid();

        // The requester raises the budget to 400,000 after the approver opened the request.
        var raise = await _client.PutAsJsonAsync($"/api/requests/{id}/budget",
            new { budget = 400_000m, justification = "Scope grew to all sites.", version = seenByApprover }, Ct);
        Assert.Equal(HttpStatusCode.OK, raise.StatusCode);

        var approve = await _client.PostAsJsonAsync($"/api/requests/{id}/decision",
            new { approve = true, decidedBy = "sam.approver@contoso.com", version = seenByApprover }, Ct);

        Assert.Equal(HttpStatusCode.Conflict, approve.StatusCode);
        Assert.Equal("The request changed since you read it.", (await Json(approve)).GetProperty("title").GetString());
        var now = await Json(await _client.GetAsync($"/api/requests/{id}", Ct));
        Assert.Equal("Submitted", now.GetProperty("status").GetString());
        Assert.Equal(400_000m, now.GetProperty("budget").GetDecimal());
    }

    [Fact]
    public async Task Approving_the_current_version_works_once()
    {
        var created = await Create();
        var id = created.GetProperty("id").GetInt32();
        var body = new { approve = true, decidedBy = "Sam.Approver@contoso.com", version = created.GetProperty("version").GetGuid() };

        var first = await _client.PostAsJsonAsync($"/api/requests/{id}/decision", body, Ct);
        var second = await _client.PostAsJsonAsync($"/api/requests/{id}/decision", body, Ct);
        var reread = await Json(await _client.GetAsync($"/api/requests/{id}", Ct));

        Assert.Equal(HttpStatusCode.OK, first.StatusCode);
        var approved = await Json(first);
        Assert.Equal("Approved", approved.GetProperty("status").GetString());
        Assert.Equal("sam.approver@contoso.com", approved.GetProperty("decidedBy").GetString());
        Assert.EndsWith("Z", approved.GetProperty("decidedAtUtc").GetString());
        Assert.EndsWith("Z", reread.GetProperty("decidedAtUtc").GetString());   // nullable DateTime too
        Assert.Equal(HttpStatusCode.Conflict, second.StatusCode);
        Assert.Equal("Request already decided.", (await Json(second)).GetProperty("title").GetString());
    }

    [Fact]
    public async Task You_cannot_decide_your_own_request()
    {
        var created = await Create();
        var response = await _client.PostAsJsonAsync($"/api/requests/{created.GetProperty("id").GetInt32()}/decision",
            new { approve = true, decidedBy = "ALEX.DEMO@contoso.com", version = created.GetProperty("version").GetGuid() }, Ct);

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Fact]
    public async Task Decision_without_a_version_is_a_400()
    {
        var created = await Create();
        var response = await _client.PostAsJsonAsync($"/api/requests/{created.GetProperty("id").GetInt32()}/decision",
            new { approve = true, decidedBy = "sam.approver@contoso.com" }, Ct);

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.True((await Json(response)).GetProperty("errors").TryGetProperty("Version", out _));
    }

    [Fact]
    public async Task Summary_totals_are_computed_per_department()
    {
        var a = await Create(10_000m, "FIN");
        await Create(20_000.50m, "FIN");
        await Create(5_000m, "IT");
        await _client.PostAsJsonAsync($"/api/requests/{a.GetProperty("id").GetInt32()}/decision",
            new { approve = true, decidedBy = "sam.approver@contoso.com", version = a.GetProperty("version").GetGuid() }, Ct);

        var summary = await Json(await _client.GetAsync("/api/requests/summary", Ct));

        Assert.Equal(3, summary.GetArrayLength());                // FIN, IT, OPS (OPS has none)
        var fin = summary[0];
        Assert.Equal("FIN", fin.GetProperty("department").GetString());
        Assert.Equal(2, fin.GetProperty("requests").GetInt32());
        Assert.Equal(30_000.50m, fin.GetProperty("totalBudget").GetDecimal());
        Assert.Equal(10_000m, fin.GetProperty("approvedBudget").GetDecimal());
        Assert.Equal(0, summary[2].GetProperty("requests").GetInt32());
    }

    [Fact]
    public async Task Unknown_id_is_404_and_health_includes_the_database()
    {
        Assert.Equal(HttpStatusCode.NotFound, (await _client.GetAsync("/api/requests/999", Ct)).StatusCode);

        var health = await _client.GetAsync("/healthz", Ct);
        Assert.Equal(HttpStatusCode.OK, health.StatusCode);
        Assert.Equal("Healthy", await health.Content.ReadAsStringAsync(Ct));
    }

    [Fact]
    public async Task Data_survives_an_app_restart()
    {
        var id = (await Create(12_345m, "OPS")).GetProperty("id").GetInt32();
        _factory.Dispose();                                       // stop the app (episode 1 lost everything here)

        await using var restarted = RequestsApiFactory.ForExistingDatabase(_factory.DatabasePath);
        var again = await restarted.CreateClient().GetAsync($"/api/requests/{id}", Ct);

        Assert.Equal(HttpStatusCode.OK, again.StatusCode);
        Assert.Equal(12_345m, (await Json(again)).GetProperty("budget").GetDecimal());
    }
}
