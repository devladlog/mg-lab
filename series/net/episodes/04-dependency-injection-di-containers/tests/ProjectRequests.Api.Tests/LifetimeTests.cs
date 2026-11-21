using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using ProjectRequests.Api.Data;
using ProjectRequests.Api.Diagnostics;

namespace ProjectRequests.Api.Tests;

/// <summary>
/// The anti-pattern, on purpose: a singleton that takes the scoped DbContext in its constructor.
/// It lives only in the tests.
/// </summary>
public sealed class CaptiveRequestReader(RequestsDbContext db)
{
    public Guid DbContextId => db.ContextId.InstanceId;
    public Task<ProjectRequest?> FindAsync(int id) => db.Requests.FindAsync(id).AsTask();
}

public sealed class LifetimeTests
{
    private static async Task<JsonElement> Json(HttpResponseMessage response) =>
        JsonDocument.Parse(await response.Content.ReadAsStringAsync()).RootElement;

    [Fact]
    public async Task Transient_scoped_singleton_and_the_DbContext_behave_as_registered()
    {
        await using var factory = new RequestsApiFactory();
        var client = factory.CreateClient();
        try
        {
            var first = await Json(await client.GetAsync("/diagnostics/lifetimes"));
            var second = await Json(await client.GetAsync("/diagnostics/lifetimes"));
            string Id(JsonElement report, string who, string what) => report.GetProperty(who).GetProperty(what).GetString()!;

            // Same request: transient differs between endpoint and consumer; scoped and DbContext are shared.
            Assert.NotEqual(Id(first, "endpoint", "transient"), Id(first, "consumer", "transient"));
            Assert.Equal(Id(first, "endpoint", "scoped"), Id(first, "consumer", "scoped"));
            Assert.Equal(Id(first, "endpoint", "dbContext"), Id(first, "consumer", "dbContext"));

            // Next request: new scope, new scoped instance, new DbContext. Singleton: same forever.
            Assert.NotEqual(Id(first, "endpoint", "scoped"), Id(second, "endpoint", "scoped"));
            Assert.NotEqual(Id(first, "endpoint", "dbContext"), Id(second, "endpoint", "dbContext"));
            Assert.Equal(Id(first, "endpoint", "singleton"), Id(second, "consumer", "singleton"));
        }
        finally { factory.DeleteDatabase(); }
    }

    [Fact]
    public void Scope_validation_rejects_a_singleton_that_captures_the_DbContext()
    {
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["Database:Provider"] = "Sqlite", ["ConnectionStrings:Requests"] = "Data Source=:memory:",
        }).Build();
        var services = new ServiceCollection().AddRequestsDatabase(config);
        services.AddSingleton<CaptiveRequestReader>();

        var ex = Assert.Throws<AggregateException>(() => services.BuildServiceProvider(
            new ServiceProviderOptions { ValidateScopes = true, ValidateOnBuild = true }));

        Assert.Contains("Cannot consume scoped service 'ProjectRequests.Api.Data.RequestsDbContext' from singleton " +
                        "'ProjectRequests.Api.Tests.CaptiveRequestReader'", ex.InnerExceptions.Single().Message);
    }

    [Fact]
    public void Development_host_refuses_to_start_with_a_captive_dependency()
    {
        using var factory = new RequestsApiFactory("Development",
            services: s => s.AddSingleton<CaptiveRequestReader>());

        var ex = Assert.ThrowsAny<Exception>(() => factory.CreateClient());   // ValidateOnBuild in Development

        Assert.Contains("Cannot consume scoped service", ex.ToString());
        factory.DeleteDatabase();
    }

    [Fact]
    public async Task Production_host_starts_anyway_and_the_captive_DbContext_serves_stale_data()
    {
        await using var factory = new RequestsApiFactory("Production",
            services: s => s.AddSingleton<CaptiveRequestReader>());
        var client = factory.CreateClient();                              // no validation outside Development
        try
        {
            var created = await Json(await client.PostAsJsonAsync("/api/requests", new
            {
                title = "Laptop refresh", budget = 40_000m, requestedBy = "alex.demo@contoso.com", departmentCode = "FIN",
            }));
            var id = created.GetProperty("id").GetInt32();

            var captive = factory.Services.GetRequiredService<CaptiveRequestReader>();
            Assert.Equal(RequestStatus.Submitted, (await captive.FindAsync(id))!.Status);

            var approve = await client.PostAsJsonAsync($"/api/requests/{id}/decision", new
            {
                approve = true, decidedBy = "sam.approver@contoso.com", version = created.GetProperty("version").GetGuid(),
            });
            Assert.Equal(HttpStatusCode.OK, approve.StatusCode);

            // The API (a fresh DbContext per request) sees Approved. The captive one still says Submitted:
            // it's the same DbContext as before, and its change tracker hands back the instance it already has.
            var viaApi = await Json(await client.GetAsync($"/api/requests/{id}"));
            Assert.Equal("Approved", viaApi.GetProperty("status").GetString());
            Assert.Equal(RequestStatus.Submitted, (await captive.FindAsync(id))!.Status);
            Assert.Equal(captive.DbContextId, factory.Services.GetRequiredService<CaptiveRequestReader>().DbContextId);
        }
        finally { factory.DeleteDatabase(); }
    }

    [Fact]
    public void AddDbContext_registers_the_context_as_scoped()
    {
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["Database:Provider"] = "SqlServer", ["ConnectionStrings:Requests"] = "Server=unused;Database=unused",
        }).Build();
        var services = new ServiceCollection().AddRequestsDatabase(config);

        Assert.Equal(ServiceLifetime.Scoped, services.Single(d => d.ServiceType == typeof(RequestsDbContext)).Lifetime);
    }
}
