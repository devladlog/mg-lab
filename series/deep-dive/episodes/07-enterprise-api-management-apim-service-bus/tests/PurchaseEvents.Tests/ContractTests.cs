using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using Contoso.PurchaseEvents;

namespace PurchaseEvents.Tests;

/// <summary>Policy, OpenAPI, Bicep and the worker have to agree. Each file is read from disk; Bicep is compiled with the real CLI.</summary>
public class ContractTests
{
    private static readonly string Root = Paths.EpisodeRoot;
    private static XDocument Policy() => XDocument.Load(Path.Combine(Root, "apim", "policies", "purchase-events.policy.xml"));
    private static JsonDocument OpenApi() => JsonDocument.Parse(File.ReadAllText(Path.Combine(Root, "apim", "openapi", "purchase-events.openapi.json")));

    private static JsonElement Template()
    {
        var psi = new ProcessStartInfo("bicep", ["build", Path.Combine(Root, "infra", "main.bicep"), "--stdout"])
        { RedirectStandardOutput = true, RedirectStandardError = true };
        using var p = Process.Start(psi)!;
        var json = p.StandardOutput.ReadToEnd();
        var err = p.StandardError.ReadToEnd();
        p.WaitForExit();
        Assert.True(p.ExitCode == 0, "bicep build failed: " + err);
        return JsonDocument.Parse(json).RootElement.Clone();
    }

    private static JsonElement[] Resources()
    {
        var res = Template().GetProperty("resources");
        return res.ValueKind == JsonValueKind.Array
            ? res.EnumerateArray().ToArray()
            : res.EnumerateObject().Select(o => o.Value).ToArray();
    }

    private static JsonElement One(JsonElement[] res, string type) =>
        res.Single(r => r.GetProperty("type").GetString() == type);

    // ---- policy shape ------------------------------------------------------------------------------------------

    [Fact]
    public void The_policy_fits_the_consumption_tier_document_limit()
    {
        // Learn, API Management gateway runtime limits: policy document size 16 KiB on the Consumption tier.
        var bytes = Encoding.UTF8.GetByteCount(File.ReadAllText(Path.Combine(Root, "apim", "policies", "purchase-events.policy.xml")));
        Assert.True(bytes < 16 * 1024, $"policy is {bytes} bytes");
    }

    [Fact]
    public void The_policy_uses_no_policy_the_consumption_tier_lacks()
    {
        var names = Policy().Descendants().Select(e => e.Name.LocalName).ToHashSet();
        Assert.DoesNotContain("rate-limit-by-key", names);        // not available on Consumption
        Assert.DoesNotContain("quota-by-key", names);             // not available on Consumption
        Assert.DoesNotContain("send-service-bus-message", names); // classic tiers only (preview)
        Assert.Contains("rate-limit", names);                     // per subscription key works everywhere
    }

    [Fact]
    public void Authentication_comes_before_throttling_before_body_validation_before_the_call_to_service_bus()
    {
        var inbound = Policy().Descendants("inbound").Single().Elements().Select(e => e.Name.LocalName).ToList();
        int At(string n) => inbound.IndexOf(n);
        Assert.True(At("base") < At("validate-jwt"));
        Assert.True(At("validate-jwt") < At("rate-limit"));
        Assert.True(At("rate-limit") < At("validate-content"));
        Assert.True(At("validate-content") < At("authentication-managed-identity"));
        Assert.True(At("authentication-managed-identity") < At("set-backend-service"));
    }

    [Fact]
    public void The_gateway_authenticates_to_service_bus_with_its_managed_identity_and_holds_no_secret()
    {
        var xml = File.ReadAllText(Path.Combine(Root, "apim", "policies", "purchase-events.policy.xml"));
        var mi = Policy().Descendants("authentication-managed-identity").Single();
        Assert.Equal("https://servicebus.azure.net/", (string?)mi.Attribute("resource"));
        Assert.Null(mi.Attribute("client-id")); // system-assigned identity
        Assert.DoesNotContain("SharedAccessSignature", xml);
        Assert.DoesNotContain("sig=", xml);
        Assert.DoesNotContain("Endpoint=sb://", xml);
    }

    [Fact]
    public void The_token_check_requires_the_audience_and_the_app_role_from_named_values()
    {
        var jwt = Policy().Descendants("validate-jwt").Single();
        Assert.Equal("Bearer", (string?)jwt.Attribute("require-scheme"));
        Assert.Contains("{{tenant-id}}", (string?)jwt.Element("openid-config")!.Attribute("url"));
        Assert.Equal("{{api-client-id}}", jwt.Descendants("audience").Single().Value);
        var claim = jwt.Descendants("claim").Single();
        Assert.Equal("roles", (string?)claim.Attribute("name"));
        Assert.Equal("Purchase.Submit", claim.Element("value")!.Value);
    }

    [Fact]
    public void The_threshold_in_the_policy_is_the_threshold_in_the_consumer()
    {
        var label = Policy().Descendants("set-variable").Single(e => (string?)e.Attribute("name") == "label").Attribute("value")!.Value;
        var m = Regex.Match(label, @">=\s*(\d+)m");
        Assert.True(m.Success, label);
        Assert.Equal(PurchaseRouting.HighValueThreshold, decimal.Parse(m.Groups[1].Value));
        Assert.Contains($"\"{PurchaseRouting.HighLabel}\"", label);
        Assert.Contains($"\"{PurchaseRouting.StandardLabel}\"", label);
    }

    [Fact]
    public void The_validate_content_body_limit_is_inside_the_documented_100_KiB_and_matches_the_schema_intent()
    {
        var vc = Policy().Descendants("validate-content").Single();
        Assert.True(int.Parse((string)vc.Attribute("max-size")!) <= 100 * 1024);
        Assert.Equal("prevent", (string?)vc.Attribute("size-exceeded-action"));
        Assert.Equal("prevent", (string?)vc.Attribute("unspecified-content-type-action"));
        Assert.Equal("false", (string?)vc.Element("content")!.Attribute("allow-additional-properties"));
    }

    [Fact]
    public void Every_named_value_the_policy_uses_is_defined_in_bicep()
    {
        var used = Regex.Matches(File.ReadAllText(Path.Combine(Root, "apim", "policies", "purchase-events.policy.xml")), @"\{\{([a-z0-9-]+)\}\}")
            .Select(m => m.Groups[1].Value).ToHashSet();
        var defined = Resources().Where(r => r.GetProperty("type").GetString() == "Microsoft.ApiManagement/service/namedValues")
            .Select(r => r.GetProperty("properties").GetProperty("displayName").GetString()!).ToHashSet();
        Assert.NotEmpty(used);
        Assert.Empty(used.Except(defined));
    }

    // ---- OpenAPI <-> worker -------------------------------------------------------------------------------------

    [Fact]
    public async Task Every_value_the_openapi_schema_allows_is_accepted_by_the_worker_and_the_edges_are_rejected()
    {
        using var doc = OpenApi();
        var props = doc.RootElement.GetProperty("components").GetProperty("schemas").GetProperty("PurchaseEvent").GetProperty("properties");
        string[] types = props.GetProperty("eventType").GetProperty("enum").EnumerateArray().Select(e => e.GetString()!).ToArray();
        string[] currencies = props.GetProperty("currency").GetProperty("enum").EnumerateArray().Select(e => e.GetString()!).ToArray();
        var min = props.GetProperty("total").GetProperty("minimum").GetDecimal();
        var max = props.GetProperty("total").GetProperty("maximum").GetDecimal();
        var pattern = props.GetProperty("purchaseRequestId").GetProperty("pattern").GetString()!;
        Assert.Equal("^PR-[0-9]{4,8}$", pattern);

        var handler = new PurchaseEventHandler(new InMemoryProcessedStore(), new RecordingSink());
        async Task<Disposition> Send(string type, string id, decimal total, string cur) =>
            (await handler.HandleAsync(HandlerTests.Msg(new { eventType = type, purchaseRequestId = id, requestedBy = "alex.demo@contoso.com", total, currency = cur }), CancellationToken.None)).Disposition;

        foreach (var t in types) Assert.Equal(Disposition.Complete, await Send(t, "PR-1001", 10m, "EUR"));
        foreach (var c in currencies) Assert.Equal(Disposition.Complete, await Send("submitted", "PR-1001", 10m, c));
        Assert.Equal(Disposition.Complete, await Send("submitted", "PR-1001", min, "EUR"));
        Assert.Equal(Disposition.Complete, await Send("submitted", "PR-12345678", max, "EUR"));
        Assert.Equal(Disposition.DeadLetter, await Send("submitted", "PR-123", 10m, "EUR"));
        Assert.Equal(Disposition.DeadLetter, await Send("submitted", "PR-123456789", 10m, "EUR"));
    }

    [Fact]
    public void The_api_requires_a_subscription_key_and_documents_the_status_codes_the_policy_returns()
    {
        using var doc = OpenApi();
        var responses = doc.RootElement.GetProperty("paths").GetProperty("/purchase-events").GetProperty("post").GetProperty("responses");
        foreach (var code in new[] { "202", "400", "401", "429", "502" }) Assert.True(responses.TryGetProperty(code, out _), code);

        var api = One(Resources(), "Microsoft.ApiManagement/service/apis").GetProperty("properties");
        Assert.True(api.GetProperty("subscriptionRequired").GetBoolean());
        Assert.Equal("openapi+json", api.GetProperty("format").GetString());
    }

    // ---- Bicep --------------------------------------------------------------------------------------------------

    [Fact]
    public void Apim_is_consumption_with_a_system_assigned_identity()
    {
        var apim = One(Resources(), "Microsoft.ApiManagement/service");
        Assert.Equal("Consumption", apim.GetProperty("sku").GetProperty("name").GetString());
        Assert.Equal(0, apim.GetProperty("sku").GetProperty("capacity").GetInt32());
        Assert.Equal("SystemAssigned", apim.GetProperty("identity").GetProperty("type").GetString());
    }

    [Fact]
    public void Service_bus_is_standard_entra_only_with_duplicate_detection_on_the_topic()
    {
        var res = Resources();
        var ns = One(res, "Microsoft.ServiceBus/namespaces");
        Assert.Equal("Standard", ns.GetProperty("sku").GetProperty("name").GetString()); // Basic: queues only, no duplicate detection
        Assert.True(ns.GetProperty("properties").GetProperty("disableLocalAuth").GetBoolean());
        var topic = One(res, "Microsoft.ServiceBus/namespaces/topics").GetProperty("properties");
        Assert.True(topic.GetProperty("requiresDuplicateDetection").GetBoolean());
        // The property is a parameter reference; the parameter's default is Learn's default window.
        Assert.Contains("duplicateDetectionWindow", topic.GetProperty("duplicateDetectionHistoryTimeWindow").GetString());
        Assert.Equal("PT10M", Template().GetProperty("parameters").GetProperty("duplicateDetectionWindow").GetProperty("defaultValue").GetString());
    }

    [Fact]
    public void The_finance_subscription_filters_on_the_label_the_policy_sets()
    {
        var rule = One(Resources(), "Microsoft.ServiceBus/namespaces/topics/subscriptions/rules");
        Assert.Contains("$Default", rule.GetProperty("name").GetString());
        var p = rule.GetProperty("properties");
        Assert.Equal("CorrelationFilter", p.GetProperty("filterType").GetString());
        Assert.Equal(PurchaseRouting.HighLabel, p.GetProperty("correlationFilter").GetProperty("label").GetString());
    }

    [Fact]
    public void The_gateway_can_only_send_and_only_on_the_topic()
    {
        var assignments = Resources().Where(r => r.GetProperty("type").GetString() == "Microsoft.Authorization/roleAssignments").ToList();
        var roles = Template().GetProperty("variables").GetProperty("roles");
        Assert.Equal("69a216fc-b8fb-44d8-bc22-1f3c2cd27a39", roles.GetProperty("serviceBusDataSender").GetString()); // Azure Service Bus Data Sender
        var sender = assignments.Single(a => a.GetProperty("properties").GetProperty("roleDefinitionId").GetRawText().Contains("serviceBusDataSender"));
        // Scope is the topic: bicep emits a resource id expression ending in the topic name.
        var scope = sender.GetProperty("scope").GetString()!;
        Assert.Contains("Microsoft.ServiceBus/namespaces/topics", scope);
        Assert.Contains("identity.principalId", sender.GetProperty("properties").GetProperty("principalId").GetString()!.Replace("'", ""), StringComparison.OrdinalIgnoreCase);
        // No role on the namespace or resource group for the gateway, and nobody gets Data Owner.
        Assert.DoesNotContain("090c5cfd-751d-490a-894a-3ce6f1109419", JsonSerializer.Serialize(roles)); // Azure Service Bus Data Owner is not even defined
    }
}
