using System.Net;
using System.Net.Http.Json;
using System.Text.Json;

namespace ProjectRequests.Api.Tests;

/// <summary>
/// The real app in memory. One app + database per fixture ([OneTimeSetUp]), a fresh HttpClient per test
/// ([SetUp]). Tests share the database, so each one creates its own request and only looks at that.
/// </summary>
[Category("Integration")]
public sealed class ApiTests
{
    private RequestsApiFactory _factory = null!;        // ONE instance of ApiTests for all its tests
    private HttpClient _client = null!;

    private static CancellationToken Ct => TestContext.CurrentContext.CancellationToken;

    [OneTimeSetUp] public void StartApp() => _factory = new RequestsApiFactory();
    [SetUp]        public void NewClient() => _client = _factory.CreateClient();
    [TearDown]     public void DisposeClient() => _client.Dispose();
    [OneTimeTearDown] public async Task StopApp() { await _factory.DisposeAsync(); _factory.DeleteDatabase(); }

    private async Task<JsonElement> CreateAsync(decimal budget, string department = "FIN")
    {
        var response = await _client.PostAsJsonAsync("/api/requests", new
        {
            title = "Laptop refresh", budget, requestedBy = "alex.demo@contoso.com", departmentCode = department,
        }, Ct);
        Assert.That(response.StatusCode, Is.EqualTo(HttpStatusCode.Created));
        return await response.Content.ReadFromJsonAsync<JsonElement>(Ct);
    }

    [Test]
    public async Task Create_returns_department_priority_and_version()
    {
        var body = await CreateAsync(75_000m, "it");

        using (Assert.EnterMultipleScope())
        {
            Assert.That(body.GetProperty("department").GetString(), Is.EqualTo("IT"));
            Assert.That(body.GetProperty("priority").GetString(), Is.EqualTo("High"));
            Assert.That(body.GetProperty("status").GetString(), Is.EqualTo("Submitted"));
            Assert.That(body.GetProperty("version").GetGuid(), Is.Not.EqualTo(Guid.Empty));
        }
    }

    [Test]
    public async Task Decision_with_a_stale_version_is_409_and_changes_nothing()
    {
        var created = await CreateAsync(40_000m);
        var id = created.GetProperty("id").GetInt32();
        var seen = created.GetProperty("version").GetGuid();

        var raise = await _client.PutAsJsonAsync($"/api/requests/{id}/budget", new { budget = 60_000m, version = seen }, Ct);
        var approve = await _client.PostAsJsonAsync($"/api/requests/{id}/decision",
            new { approve = true, decidedBy = "sam.approver@contoso.com", version = seen }, Ct);
        var now = await _client.GetFromJsonAsync<JsonElement>($"/api/requests/{id}", Ct);

        using (Assert.EnterMultipleScope())
        {
            Assert.That(raise.StatusCode, Is.EqualTo(HttpStatusCode.OK));
            Assert.That(approve.StatusCode, Is.EqualTo(HttpStatusCode.Conflict));
            Assert.That(now.GetProperty("status").GetString(), Is.EqualTo("Submitted"));
            Assert.That(now.GetProperty("budget").GetDecimal(), Is.EqualTo(60_000m));
        }
    }

    [TestCase("alex.demo@contoso.com", HttpStatusCode.Conflict)]       // own request
    [TestCase("ALEX.DEMO@contoso.com", HttpStatusCode.Conflict)]       // still own request
    [TestCase("sam.approver@contoso.com", HttpStatusCode.OK)]
    public async Task Requesters_cannot_decide_their_own_request(string decidedBy, HttpStatusCode expected)
    {
        var created = await CreateAsync(10_000m);

        var response = await _client.PostAsJsonAsync($"/api/requests/{created.GetProperty("id").GetInt32()}/decision",
            new { approve = true, decidedBy, version = created.GetProperty("version").GetGuid() }, Ct);

        Assert.That(response.StatusCode, Is.EqualTo(expected));
    }
}
