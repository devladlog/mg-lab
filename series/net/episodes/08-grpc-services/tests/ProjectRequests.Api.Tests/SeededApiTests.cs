using System.Net;
using System.Net.Http.Json;

namespace ProjectRequests.Api.Tests;

/// <summary>
/// One app + one database for the whole class, seeded once. xUnit creates a new instance of the test class
/// for every test, so shared state has to live in a fixture. v3: IAsyncLifetime returns ValueTask and
/// disposal is IAsyncDisposable.
/// </summary>
public sealed class SeededApi : IAsyncLifetime
{
    private static readonly (string Department, decimal Budget)[] Seed =
        [("FIN", 12_000m), ("FIN", 80_000m), ("IT", 55_000m), ("OPS", 3_000m)];

    public RequestsApiFactory Factory { get; } = new();
    public HttpClient Client { get; private set; } = null!;

    public async ValueTask InitializeAsync()
    {
        Client = Factory.CreateClient();
        foreach (var (department, budget) in Seed)
        {
            var response = await Client.PostAsJsonAsync("/api/requests", new
            {
                title = "Seeded request", budget, requestedBy = "alex.demo@contoso.com", departmentCode = department,
            });
            response.EnsureSuccessStatusCode();
        }
    }

    public async ValueTask DisposeAsync() { await Factory.DisposeAsync(); Factory.DeleteDatabase(); }
}

/// <summary>Read-only tests: they share the seeded data, so none of them may change it.</summary>
[Trait("Category", "Integration")]
public sealed class SeededApiTests(SeededApi api) : IClassFixture<SeededApi>
{
    [Fact]
    public async Task Summary_totals_each_department()
    {
        var summary = await api.Client.GetFromJsonAsync<List<DepartmentSummary>>("/api/requests/summary", Ct);

        Assert.Equal(
            [new("FIN", 2, 92_000m, 0m), new("IT", 1, 55_000m, 0m), new("OPS", 1, 3_000m, 0m)],
            summary);
    }

    [Theory]
    [InlineData("High", 2)]
    [InlineData("Standard", 2)]
    public async Task List_filters_by_priority(string priority, int expected)
    {
        var list = await api.Client.GetFromJsonAsync<List<RequestDto>>($"/api/requests?priority={priority}", JsonDefaults, Ct);

        Assert.Equal(expected, list!.Count);
    }

    [Fact]
    public async Task Unknown_id_is_404()
    {
        var response = await api.Client.GetAsync("/api/requests/999", Ct);

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    private static readonly System.Text.Json.JsonSerializerOptions JsonDefaults = new(System.Text.Json.JsonSerializerDefaults.Web)
    {
        Converters = { new System.Text.Json.Serialization.JsonStringEnumConverter() },
    };
}
