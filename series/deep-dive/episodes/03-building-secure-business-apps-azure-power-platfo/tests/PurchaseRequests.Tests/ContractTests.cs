using System.Diagnostics;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;

namespace PurchaseRequests.Tests;

/// <summary>The connector file and the Bicep template must agree with the code.</summary>
public partial class ContractTests
{
    static string EpisodeRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !Directory.Exists(Path.Combine(dir.FullName, "connector"))) dir = dir.Parent;
        return dir!.FullName;
    }

    [GeneratedRegex(@"\{(\w+)(:[^}]*)?\}")]
    private static partial Regex RouteParam();

    [Fact]
    public void Every_connector_operation_exists_in_the_api_with_the_same_name_route_and_method()
    {
        using var api = new ApiFactory().Start();
        var endpoints = api.Services.GetRequiredService<EndpointDataSource>().Endpoints.OfType<RouteEndpoint>()
            .Select(e => (
                Name: e.Metadata.GetMetadata<IEndpointNameMetadata>()?.EndpointName,
                Route: "/" + RouteParam().Replace(e.RoutePattern.RawText!.TrimStart('/'), "{$1}").TrimEnd('/'),
                Methods: e.Metadata.GetMetadata<HttpMethodMetadata>()?.HttpMethods ?? []))
            .Where(e => e.Name is not null).ToList();

        using var doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(EpisodeRoot(), "connector", "apiDefinition.swagger.json")));
        Assert.Equal("2.0", doc.RootElement.GetProperty("swagger").GetString());   // custom connectors take OpenAPI 2.0
        var operations = 0;
        foreach (var path in doc.RootElement.GetProperty("paths").EnumerateObject())
        foreach (var verb in path.Value.EnumerateObject())
        {
            operations++;
            var opId = verb.Value.GetProperty("operationId").GetString();
            var match = endpoints.SingleOrDefault(e => e.Name == opId);
            Assert.True(match.Name is not null, $"{opId} is in the connector but not in the API");
            Assert.Equal(path.Name, match.Route);
            Assert.Contains(verb.Name.ToUpperInvariant(), match.Methods);
            Assert.True(verb.Value.GetProperty("responses").TryGetProperty("401", out _), $"{opId} should document 401");
            Assert.True(verb.Value.GetProperty("responses").TryGetProperty("403", out _), $"{opId} should document 403");
        }
        Assert.Equal(endpoints.Count, operations);   // and nothing in the API is missing from the connector
    }

    static JsonElement? _arm;
    static JsonElement Arm()
    {
        if (_arm is { } cached) return cached;
        var psi = new ProcessStartInfo("bicep", ["build", Path.Combine(EpisodeRoot(), "infra", "main.bicep"), "--stdout"])
        { RedirectStandardOutput = true, RedirectStandardError = true };
        using var p = Process.Start(psi)!;
        var json = p.StandardOutput.ReadToEnd();
        p.WaitForExit();
        Assert.True(p.ExitCode == 0, p.StandardError.ReadToEnd());
        _arm = JsonDocument.Parse(json).RootElement.Clone();
        return _arm.Value;
    }

    static JsonElement Resource(string type) => Arm().GetProperty("resources").EnumerateArray()
        .Single(r => r.GetProperty("type").GetString() == type);

    [Fact]
    public void Sql_server_is_entra_only_with_no_password_parameter()
    {
        var admins = Resource("Microsoft.Sql/servers").GetProperty("properties").GetProperty("administrators");
        Assert.True(admins.GetProperty("azureADOnlyAuthentication").GetBoolean());
        Assert.Equal("ActiveDirectory", admins.GetProperty("administratorType").GetString());
        var parameters = Arm().GetProperty("parameters").EnumerateObject().Select(p => p.Name.ToLowerInvariant()).ToList();
        Assert.DoesNotContain(parameters, p => p.Contains("password"));
    }

    [Fact]
    public void Database_uses_the_free_offer_and_pauses_instead_of_billing()
    {
        var db = Resource("Microsoft.Sql/servers/databases");
        Assert.Equal("GP_S_Gen5_2", db.GetProperty("sku").GetProperty("name").GetString());
        Assert.True(db.GetProperty("properties").GetProperty("useFreeLimit").GetBoolean());
        Assert.Equal("AutoPause", db.GetProperty("properties").GetProperty("freeLimitExhaustionBehavior").GetString());
    }

    [Fact]
    public void Web_app_is_free_tier_https_only_with_managed_identity_and_no_basic_auth()
    {
        Assert.Equal("F1", Resource("Microsoft.Web/serverfarms").GetProperty("sku").GetProperty("name").GetString());
        var site = Resource("Microsoft.Web/sites");
        Assert.Equal("SystemAssigned", site.GetProperty("identity").GetProperty("type").GetString());
        var props = site.GetProperty("properties");
        Assert.True(props.GetProperty("httpsOnly").GetBoolean());
        var cfg = props.GetProperty("siteConfig");
        Assert.Equal("Disabled", cfg.GetProperty("ftpsState").GetString());
        Assert.Equal("DOTNETCORE|10.0", cfg.GetProperty("linuxFxVersion").GetString());
        var cs = cfg.GetProperty("connectionStrings")[0].GetProperty("connectionString").GetString()!;
        Assert.Contains("Authentication=Active Directory Default", cs);
        Assert.DoesNotContain("Password", cs, StringComparison.OrdinalIgnoreCase);

        var basicAuth = Arm().GetProperty("resources").EnumerateArray()
            .Where(r => r.GetProperty("type").GetString() == "Microsoft.Web/sites/basicPublishingCredentialsPolicies").ToList();
        Assert.Equal(2, basicAuth.Count);
        Assert.All(basicAuth, r => Assert.False(r.GetProperty("properties").GetProperty("allow").GetBoolean()));
    }

    [Fact]
    public void App_settings_match_the_configuration_keys_the_code_reads()
    {
        var names = Resource("Microsoft.Web/sites").GetProperty("properties").GetProperty("siteConfig")
            .GetProperty("appSettings").EnumerateArray().Select(s => s.GetProperty("name").GetString()).ToList();
        Assert.Contains("Entra__TenantId", names);
        Assert.Contains("Entra__ClientId", names);
        Assert.Contains("Approval__FinanceThreshold", names);
    }
}
