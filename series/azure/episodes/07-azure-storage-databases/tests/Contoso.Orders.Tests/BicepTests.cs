using System.Diagnostics;
using System.Reflection;
using System.Text.Json.Nodes;

namespace Contoso.Orders.Tests;

/// <summary>Guardrails on the compiled template (bicep build, no Azure needed).</summary>
public class BicepTests
{
    private static readonly string Root = typeof(BicepTests).Assembly
        .GetCustomAttributes<AssemblyMetadataAttribute>().Single(a => a.Key == "EpisodeRoot").Value!;

    private static readonly Lazy<JsonObject> Template = new(() =>
    {
        var psi = new ProcessStartInfo("bicep", ["build", Path.Combine(Root, "infra", "main.bicep"), "--stdout"])
        {
            RedirectStandardOutput = true, RedirectStandardError = true,
        };
        using var p = Process.Start(psi)!;
        var json = p.StandardOutput.ReadToEnd();
        var err = p.StandardError.ReadToEnd();
        p.WaitForExit();
        Assert.True(p.ExitCode == 0, "bicep build failed: " + err);
        return JsonNode.Parse(json)!.AsObject();
    });

    private static JsonObject One(string type) => Assert.Single(Template.Value["resources"]!.AsArray()
        .Select(r => r!.AsObject()), r => string.Equals((string?)r["type"], type, StringComparison.OrdinalIgnoreCase));

    [Fact]
    public void Storage_has_no_shared_keys_and_no_public_blobs()
    {
        var p = One("Microsoft.Storage/storageAccounts")["properties"]!;
        Assert.False((bool)p["allowSharedKeyAccess"]!);
        Assert.False((bool)p["allowBlobPublicAccess"]!);
        Assert.True((bool)p["defaultToOAuthAuthentication"]!);
        Assert.Equal("TLS1_2", (string)p["minimumTlsVersion"]!);
    }

    [Fact]
    public void Lifecycle_moves_invoices_hot_to_cool_to_cold_then_deletes()
    {
        var rule = One("Microsoft.Storage/storageAccounts/managementPolicies")["properties"]!["policy"]!["rules"]![0]!;
        Assert.Equal("invoices/", (string)rule["definition"]!["filters"]!["prefixMatch"]![0]!);
        var a = rule["definition"]!["actions"]!["baseBlob"]!;
        Assert.Equal("[parameters('coolAfterDays')]", (string)a["tierToCool"]!["daysAfterCreationGreaterThan"]!);
        Assert.Equal("[parameters('coldAfterDays')]", (string)a["tierToCold"]!["daysAfterCreationGreaterThan"]!);
        Assert.Equal("[parameters('deleteAfterDays')]", (string)a["delete"]!["daysAfterCreationGreaterThan"]!);

        int Default(string name) => (int)Template.Value["parameters"]![name]!["defaultValue"]!;
        // Cool must stay at least 30 days and Cold 90 days, or each move is an early-deletion charge
        Assert.True(Default("coldAfterDays") - Default("coolAfterDays") >= 30);
        Assert.True(Default("deleteAfterDays") - Default("coldAfterDays") >= 90);
    }

    [Fact]
    public void Blob_soft_delete_is_on()
    {
        var p = One("Microsoft.Storage/storageAccounts/blobServices")["properties"]!;
        Assert.True((bool)p["deleteRetentionPolicy"]!["enabled"]!);
        Assert.True((bool)p["containerDeleteRetentionPolicy"]!["enabled"]!);
    }

    [Fact]
    public void Sql_server_is_entra_only_with_no_sql_login()
    {
        var p = One("Microsoft.Sql/servers")["properties"]!.AsObject();
        Assert.False(p.ContainsKey("administratorLogin"));
        Assert.False(p.ContainsKey("administratorLoginPassword"));
        var admin = p["administrators"]!;
        Assert.True((bool)admin["azureADOnlyAuthentication"]!);
        Assert.Equal("ActiveDirectory", (string)admin["administratorType"]!);
        Assert.Equal("1.2", (string)p["minimalTlsVersion"]!);
    }

    [Fact]
    public void Database_is_the_free_tier_and_pauses_at_the_limit()
    {
        var db = One("Microsoft.Sql/servers/databases");
        Assert.Equal("GP_S_Gen5", (string)db["sku"]!["name"]!);
        var p = db["properties"]!;
        Assert.True((bool)p["useFreeLimit"]!);
        Assert.Equal("AutoPause", (string)p["freeLimitExhaustionBehavior"]!);
        Assert.Equal(32L * 1024 * 1024 * 1024, (long)p["maxSizeBytes"]!);
    }

    [Fact]
    public void Firewall_opens_one_address_not_a_range()
    {
        var p = One("Microsoft.Sql/servers/firewallRules")["properties"]!;
        Assert.Equal("[parameters('clientIp')]", (string)p["startIpAddress"]!);
        Assert.Equal("[parameters('clientIp')]", (string)p["endIpAddress"]!);
    }

    [Fact]
    public void Admin_gets_blob_data_contributor_on_the_account_only()
    {
        var ra = One("Microsoft.Authorization/roleAssignments");
        Assert.Contains("variables('blobDataContributor')", (string)ra["properties"]!["roleDefinitionId"]!);
        // Storage Blob Data Contributor: can read/write blobs and get a user delegation key
        Assert.Equal("ba92f5b4-2d11-453d-a403-e96b0029c9fe", (string)Template.Value["variables"]!["blobDataContributor"]!);
        Assert.Contains("Microsoft.Storage/storageAccounts", (string)ra["scope"]!);
    }

    [Fact]
    public void No_parameter_or_output_carries_a_secret()
    {
        var parameters = Template.Value["parameters"]!.AsObject();
        Assert.DoesNotContain(parameters, p => ((string)p.Value!["type"]!).StartsWith("secure", StringComparison.OrdinalIgnoreCase));
        var outputs = Template.Value["outputs"]!.AsObject().Select(o => o.Key).ToList();
        Assert.Equal(["sqlServerFqdn", "databaseName", "blobServiceUri", "storageAccountName"], outputs);
    }
}
