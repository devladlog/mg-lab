using System.Diagnostics;
using System.Reflection;
using System.Text.Json.Nodes;

namespace Contoso.Orders.Api.Tests;

/// <summary>
/// Guardrails on the compiled template (bicep build, no Azure needed). Each test pins a decision
/// that is easy to undo by accident and expensive to find out about in production.
/// </summary>
public class BicepTests
{
    private static readonly string Root = typeof(BicepTests).Assembly
        .GetCustomAttributes<AssemblyMetadataAttribute>().Single(a => a.Key == "EpisodeRoot").Value!;

    private static readonly Lazy<JsonObject> Template = new(() =>
    {
        var psi = new ProcessStartInfo("bicep", ["build", Path.Combine(Root, "infra", "main.bicep"), "--stdout"])
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        using var p = Process.Start(psi)!;
        var json = p.StandardOutput.ReadToEnd();
        var err = p.StandardError.ReadToEnd();
        p.WaitForExit();
        Assert.True(p.ExitCode == 0, "bicep build failed: " + err);
        return JsonNode.Parse(json)!.AsObject();
    });

    private static IEnumerable<JsonObject> Resources(string type) =>
        Template.Value["resources"]!.AsArray().Select(r => r!.AsObject())
            .Where(r => string.Equals((string?)r["type"], type, StringComparison.OrdinalIgnoreCase));

    private static JsonObject One(string type) => Assert.Single(Resources(type));

    [Fact]
    public void App_insights_is_workspace_based_and_entra_only()
    {
        var props = One("Microsoft.Insights/components")["properties"]!;
        Assert.True((bool)props["DisableLocalAuth"]!);
        Assert.Contains("Microsoft.OperationalInsights/workspaces", (string)props["WorkspaceResourceId"]!);
    }

    [Fact]
    public void Workspace_has_a_daily_cap()
    {
        var capping = One("Microsoft.OperationalInsights/workspaces")["properties"]!["workspaceCapping"]!;
        Assert.Equal("[parameters('dailyCapGb')]", (string)capping["dailyQuotaGb"]!);
        Assert.Equal(1, (int)Template.Value["parameters"]!["dailyCapGb"]!["defaultValue"]!);
    }

    [Fact]
    public void Log_alert_runs_exactly_the_query_file_the_kql_tests_check()
    {
        var rule = One("Microsoft.Insights/scheduledQueryRules")["properties"]!;
        var criterion = rule["criteria"]!["allOf"]![0]!;
        var file = File.ReadAllText(Path.Combine(Root, "queries", "alert-failure-ratio.kql"));
        // loadTextContent() inlines the file as a template variable: compare the text itself
        var reference = (string)criterion["query"]!;                      // "[variables('$fxv#0')]"
        var variable = reference["[variables('".Length..^"')]".Length];
        Assert.Equal(file, (string)Template.Value["variables"]![variable]!);
        Assert.Equal("FailurePercent", (string)criterion["metricMeasureColumn"]!);
        Assert.Equal("OperationName", (string)criterion["dimensions"]![0]!["name"]!);
        Assert.Contains("Microsoft.OperationalInsights/workspaces", rule["scopes"]![0]!.ToString());
    }

    [Fact]
    public void Availability_uses_a_standard_test_from_at_least_five_locations()
    {
        var test = One("Microsoft.Insights/webtests");
        Assert.Equal("standard", (string)test["kind"]!);
        Assert.True(Template.Value["parameters"]!["testLocations"]!["defaultValue"]!.AsArray().Count >= 5);
        var criteria = Resources("Microsoft.Insights/metricAlerts")
            .Select(a => a["properties"]!["criteria"]!)
            .Single(c => (string)c["odata.type"]! == "Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria");
        Assert.Equal("[sub(length(parameters('testLocations')), 2)]", (string)criteria["failedLocationCount"]!);
    }

    [Fact]
    public void Failed_request_alert_uses_the_standard_metric()
    {
        var metric = Resources("Microsoft.Insights/metricAlerts")
            .SelectMany(a => a["properties"]!["criteria"]!["allOf"]?.AsArray() ?? [])
            .Single();
        Assert.Equal("requests/failed", (string)metric!["metricName"]!);
        Assert.Equal("microsoft.insights/components", (string)metric["metricNamespace"]!);
    }

    [Fact]
    public void Every_alert_notifies_the_action_group()
    {
        var alerts = Resources("Microsoft.Insights/metricAlerts").Concat(Resources("Microsoft.Insights/scheduledQueryRules")).ToList();
        Assert.Equal(3, alerts.Count);
        foreach (var a in alerts)
            Assert.Contains("Microsoft.Insights/actionGroups", a["properties"]!["actions"]!.ToJsonString());
    }

    [Fact]
    public void Identity_can_publish_telemetry_and_app_knows_which_identity_to_use()
    {
        Assert.Contains(Resources("Microsoft.Authorization/roleAssignments"),
            r => r["properties"]!["roleDefinitionId"]!.ToString().Contains("monitoringMetricsPublisher")
                 && r["scope"]!.ToString().Contains("Microsoft.Insights/components"));
        Assert.Equal("3913510d-42f4-4e42-8a64-420c390055eb",
            (string)Template.Value["variables"]!["roles"]!["monitoringMetricsPublisher"]!);
        var settings = One("Microsoft.Web/sites")["properties"]!["siteConfig"]!["appSettings"]!.AsArray()
            .ToDictionary(s => (string)s!["name"]!, s => s!["value"]!.ToString());
        Assert.Contains("AZURE_CLIENT_ID", settings.Keys);
        Assert.Contains("APPLICATIONINSIGHTS_CONNECTION_STRING", settings.Keys);
        Assert.Equal("0", settings["Chaos__FailurePercent"]);
    }
}
