using Azure;
using Azure.Security.KeyVault.Secrets;
using Azure.Storage.Blobs;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using System.Net;
using System.Text.Json;

namespace ReadinessProbe.Tests;

public class HealthEndpointTests
{
    private static HttpClient Client(BlobContainerClient? container = null, SecretClient? secrets = null,
        bool configured = true) =>
        new WebApplicationFactory<Program>().WithWebHostBuilder(web =>
        {
            if (configured)
            {
                web.UseSetting("Probe:BlobContainerUri", "https://stexample.blob.core.windows.net/probe");
                web.UseSetting("Probe:KeyVaultUri", "https://kv-example.vault.azure.net/");
            }
            web.UseSetting("Probe:Timeout", "00:00:00.200");
            web.ConfigureTestServices(services =>
            {
                if (container is not null) services.AddSingleton(container);
                if (secrets is not null) services.AddSingleton(secrets);
            });
        }).CreateClient();

    private static async Task<(HttpStatusCode code, JsonElement body, string raw)> GetHealth(HttpClient client)
    {
        var res = await client.GetAsync("/healthz");
        var raw = await res.Content.ReadAsStringAsync();
        return (res.StatusCode, JsonDocument.Parse(raw).RootElement, raw);
    }

    private static string CheckStatus(JsonElement body, string name) =>
        body.GetProperty("checks").EnumerateArray().Single(c => c.GetProperty("name").GetString() == name)
            .GetProperty("status").GetString()!;

    private static string CheckDetail(JsonElement body, string name) =>
        body.GetProperty("checks").EnumerateArray().Single(c => c.GetProperty("name").GetString() == name)
            .GetProperty("detail").GetString()!;

    [Fact]
    public async Task Root_answers_without_touching_dependencies()
    {
        var res = await Client(new FakeContainer(Behaviours.Hang), new FakeSecrets(Behaviours.Hang)).GetAsync("/");
        Assert.Equal(HttpStatusCode.OK, res.StatusCode);
    }

    [Fact]
    public async Task Both_dependencies_reachable_is_200_Healthy()
    {
        var (code, body, _) = await GetHealth(Client(new FakeContainer(), new FakeSecrets()));
        Assert.Equal(HttpStatusCode.OK, code);
        Assert.Equal("Healthy", body.GetProperty("status").GetString());
        Assert.Equal("Healthy", CheckStatus(body, "storage"));
        Assert.Equal("Healthy", CheckStatus(body, "keyvault"));
    }

    [Fact]
    public async Task Storage_403_is_503_and_names_the_dependency()
    {
        var denied = new RequestFailedException(403, "This request is not authorized.", "AuthorizationFailure", null);
        var (code, body, _) = await GetHealth(Client(new FakeContainer(Behaviours.Throw(denied)), new FakeSecrets()));

        Assert.Equal(HttpStatusCode.ServiceUnavailable, code);
        Assert.Equal("Unhealthy", CheckStatus(body, "storage"));
        Assert.Equal("HTTP 403 AuthorizationFailure", CheckDetail(body, "storage"));
        Assert.Equal("Healthy", CheckStatus(body, "keyvault"));
    }

    [Fact]
    public async Task A_hanging_dependency_times_out_instead_of_hanging_the_probe()
    {
        var started = DateTime.UtcNow;
        var (code, body, _) = await GetHealth(Client(new FakeContainer(), new FakeSecrets(Behaviours.Hang)));

        Assert.Equal(HttpStatusCode.ServiceUnavailable, code);
        Assert.Equal("timed out", CheckDetail(body, "keyvault"));
        Assert.True(DateTime.UtcNow - started < TimeSpan.FromSeconds(10));
    }

    [Fact]
    public async Task Network_failure_reports_the_exception_type_only()
    {
        var (code, body, _) = await GetHealth(Client(
            new FakeContainer(Behaviours.Throw(new HttpRequestException("Name or service not known (st...)"))),
            new FakeSecrets()));

        Assert.Equal(HttpStatusCode.ServiceUnavailable, code);
        Assert.Equal("HttpRequestException", CheckDetail(body, "storage"));
    }

    [Fact]
    public async Task The_secret_value_never_appears_in_the_response()
    {
        var (_, _, raw) = await GetHealth(Client(new FakeContainer(), new FakeSecrets()));
        Assert.DoesNotContain(FakeSecrets.Value, raw);
        Assert.Contains("probe-secret", raw);
    }

    [Fact]
    public void Missing_configuration_fails_at_startup()
    {
        // First draft threw inside the health check factory: a 500 with a stack trace on /healthz.
        var ex = Assert.Throws<OptionsValidationException>(() => Client(configured: false));
        Assert.Contains("Probe:BlobContainerUri is required.", ex.Failures);
        Assert.Contains("Probe:KeyVaultUri is required.", ex.Failures);
    }
}
