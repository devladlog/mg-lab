using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using System.Text.RegularExpressions;
using Contoso.InvoiceApproval;
using Microsoft.Azure.Functions.Worker;

namespace InvoiceApproval.Tests;

/// <summary>Code, flows, columns, host.json and Bicep must agree. Flows are hand-written references until exported.</summary>
public partial class ContractTests
{
    static string Root()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !Directory.Exists(Path.Combine(dir.FullName, "contract"))) dir = dir.Parent;
        return dir!.FullName;
    }

    static JsonElement Load(params string[] path) =>
        JsonDocument.Parse(File.ReadAllText(Path.Combine([Root(), .. path]))).RootElement.Clone();

    static readonly JsonElement Columns = Load("contract", "approval-columns.json");
    static readonly JsonElement Relay = Load("flow", "approval-relay.definition.json");
    static readonly JsonElement Ready = Load("flow", "invoice-ready-to-queue.definition.json");

    static IEnumerable<string> ContractColumns() =>
        Columns.GetProperty("columns").EnumerateArray().Select(c => c.GetProperty("internalName").GetString()!);

    [Fact]
    public void Status_choices_in_sharepoint_are_exactly_the_status_values_in_code()
    {
        var choices = Columns.GetProperty("columns").EnumerateArray()
            .Single(c => c.GetProperty("internalName").GetString() == "InvApprovalStatus")
            .GetProperty("choices").EnumerateArray().Select(c => c.GetString());
        Assert.Equal(ApprovalStatus.All, choices);
    }

    [GeneratedRegex(@"item/(Inv\w+)")]
    private static partial Regex WrittenColumn();

    [Fact]
    public void Relay_flow_writes_only_columns_from_the_contract()
    {
        var written = WrittenColumn().Matches(Relay.GetRawText()).Select(m => m.Groups[1].Value).Distinct().ToList();
        Assert.NotEmpty(written);
        Assert.All(written, c => Assert.Contains(c, ContractColumns()));
        Assert.Contains("item/InvApprovalStatus/Value", Relay.GetRawText());   // choice columns are written through /Value
    }

    [Fact]
    public void Relay_trigger_schema_accepts_every_field_the_functions_send()
    {
        var schema = Relay.GetProperty("triggers").GetProperty("manual").GetProperty("inputs").GetProperty("schema");
        var allowed = schema.GetProperty("properties").EnumerateObject().Select(p => p.Name).ToHashSet();
        var required = schema.GetProperty("required").EnumerateArray().Select(r => r.GetString()!).ToList();

        var sent = typeof(FlowMessage).GetProperties()
            .Select(p => JsonNamingPolicy.CamelCase.ConvertName(p.Name)).ToList();
        Assert.Equal(allowed.OrderBy(x => x), sent.OrderBy(x => x));
        var requiredInCode = typeof(FlowMessage).GetProperties()
            .Where(p => p.GetCustomAttribute<System.Runtime.CompilerServices.RequiredMemberAttribute>() is not null)
            .Select(p => JsonNamingPolicy.CamelCase.ConvertName(p.Name));
        Assert.Equal(requiredInCode.OrderBy(x => x), required.OrderBy(x => x));
    }

    [Fact]
    public void Relay_switch_handles_exactly_the_two_kinds_and_posts_back_to_the_signed_callback()
    {
        var sw = Relay.GetProperty("actions").GetProperty("Switch_on_kind");
        var cases = sw.GetProperty("cases").EnumerateObject().Select(c => c.Value.GetProperty("case").GetString());
        Assert.Equal([FlowMessage.ApprovalRequestKind, FlowMessage.OutcomeKind], cases);

        var send = sw.GetProperty("cases").GetProperty("Approval_request").GetProperty("actions").GetProperty("Send_decision");
        Assert.Equal("@triggerBody()?['callbackUrl']", send.GetProperty("inputs").GetProperty("uri").GetString());
        var bodyKeys = send.GetProperty("inputs").GetProperty("body").EnumerateObject().Select(p => p.Name);
        var decisionKeys = typeof(DecisionBody).GetProperties().Select(p => JsonNamingPolicy.CamelCase.ConvertName(p.Name));
        Assert.Equal(decisionKeys.OrderBy(x => x), bodyKeys.OrderBy(x => x));
        // The callback URL carries the signature: keep it out of run history.
        Assert.Contains("inputs", send.GetProperty("runtimeConfiguration").GetProperty("secureData").GetProperty("properties")
            .EnumerateArray().Select(p => p.GetString()));
    }

    [Fact]
    public void Ready_flow_message_matches_what_the_intake_parses()
    {
        var compose = Ready.GetProperty("actions").GetProperty("Compose_message").GetProperty("inputs");
        var keys = compose.EnumerateObject().Select(p => p.Name);
        var parsed = typeof(InvoiceReady).GetProperties().Select(p => JsonNamingPolicy.CamelCase.ConvertName(p.Name));
        Assert.Equal(parsed.OrderBy(x => x), keys.OrderBy(x => x));

        var send = Ready.GetProperty("actions").GetProperty("Send_message").GetProperty("inputs").GetProperty("parameters");
        Assert.Equal("invoice-approvals", send.GetProperty("entityName").GetString());
    }

    [Fact]
    public void Ready_flow_only_fires_for_ready_invoices_without_an_approval_yet()
    {
        var trigger = Ready.GetProperty("triggers").EnumerateObject().Single().Value;
        var condition = trigger.GetProperty("conditions")[0].GetProperty("expression").GetString()!;
        Assert.Contains("'Ready'", condition);
        Assert.Contains("InvApprovalStatus", condition);
        Assert.Contains($"'{ApprovalStatus.NotStarted}'", condition);
    }

    [Fact]
    public void Activity_names_in_code_match_the_function_names()
    {
        var functions = typeof(ApprovalActivities).GetMethods()
            .Select(m => m.GetCustomAttribute<FunctionAttribute>()?.Name).Where(n => n is not null).ToList();
        Assert.Equal([ApprovalActivities.SendApprovalRequest, ApprovalActivities.RecordOutcome], functions);
        Assert.Equal(InvoiceApprovalOrchestrator.Name,
            typeof(InvoiceApprovalFunctions).GetMethod("Run")!.GetCustomAttribute<FunctionAttribute>()!.Name);
    }

    [Fact]
    public void Host_json_polls_the_task_hub_at_most_every_ten_seconds()
    {
        var durable = Load("src", "InvoiceApproval", "host.json").GetProperty("extensions").GetProperty("durableTask");
        Assert.Equal("InvoiceApprovals", durable.GetProperty("hubName").GetString());
        var interval = TimeSpan.Parse(durable.GetProperty("storageProvider").GetProperty("maxQueuePollingInterval").GetString()!);
        Assert.True(interval <= TimeSpan.FromSeconds(10));
    }

    // ---- Bicep -------------------------------------------------------------------------------------------

    static JsonElement? _arm;
    static JsonElement Arm()
    {
        if (_arm is { } cached) return cached;
        var psi = new ProcessStartInfo("bicep", ["build", Path.Combine(Root(), "infra", "main.bicep"), "--stdout"])
        { RedirectStandardOutput = true, RedirectStandardError = true };
        using var p = Process.Start(psi)!;
        var json = p.StandardOutput.ReadToEnd();
        p.WaitForExit();
        Assert.True(p.ExitCode == 0, p.StandardError.ReadToEnd());
        _arm = JsonDocument.Parse(json).RootElement.Clone();
        return _arm.Value;
    }

    static IEnumerable<JsonElement> Resources(string type)
    {
        // Bicep emits an array, or an object keyed by symbolic name (languageVersion 2.0) for some templates.
        var resources = Arm().GetProperty("resources");
        var all = resources.ValueKind == JsonValueKind.Array
            ? resources.EnumerateArray().ToList()
            : resources.EnumerateObject().Select(p => p.Value).ToList();
        return all.Where(r => r.GetProperty("type").GetString() == type);
    }

    [Fact]
    public void Service_bus_is_basic_and_the_flow_policy_can_only_send_to_one_queue()
    {
        Assert.Equal("Basic", Resources("Microsoft.ServiceBus/namespaces").Single().GetProperty("sku").GetProperty("name").GetString());
        var queue = Resources("Microsoft.ServiceBus/namespaces/queues").Single();
        Assert.Equal(5, queue.GetProperty("properties").GetProperty("maxDeliveryCount").GetInt32());
        var rule = Resources("Microsoft.ServiceBus/namespaces/queues/authorizationRules").Single();
        Assert.Equal(["Send"], rule.GetProperty("properties").GetProperty("rights").EnumerateArray().Select(r => r.GetString()));
        Assert.Empty(Resources("Microsoft.ServiceBus/namespaces/authorizationRules"));   // no namespace-wide keys added
    }

    [Fact]
    public void Function_identity_gets_receiver_on_the_queue_not_owner_on_the_namespace()
    {
        var roles = Arm().GetProperty("variables").GetProperty("roles");
        Assert.Equal("4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0", roles.GetProperty("serviceBusDataReceiver").GetString());
        Assert.DoesNotContain("090c5cfd-751d-490a-894a-3ce6f1109419",   // Azure Service Bus Data Owner
            roles.EnumerateObject().Select(r => r.Value.GetString()));

        var receiver = Resources("Microsoft.Authorization/roleAssignments").Single(a =>
            a.GetProperty("properties").GetProperty("roleDefinitionId").GetString()!.Contains("serviceBusDataReceiver"));
        Assert.Contains("Microsoft.ServiceBus/namespaces/queues", receiver.GetProperty("scope").GetString());
    }

    [Fact]
    public void Function_app_is_flex_dotnet10_keyless_storage_and_secrets_from_key_vault()
    {
        var site = Resources("Microsoft.Web/sites").Single();
        var runtime = site.GetProperty("properties").GetProperty("functionAppConfig").GetProperty("runtime");
        Assert.Equal(("dotnet-isolated", "10.0"), (runtime.GetProperty("name").GetString(), runtime.GetProperty("version").GetString()));
        Assert.False(Resources("Microsoft.Storage/storageAccounts").Single().GetProperty("properties").GetProperty("allowSharedKeyAccess").GetBoolean());

        var settings = Resources("Microsoft.Web/sites/config").Single().GetProperty("properties");
        Assert.Contains("@Microsoft.KeyVault(VaultName=", settings.GetProperty("Callback__SigningKey").GetString());
        Assert.Contains("SecretName=callback-signing-key", settings.GetProperty("Callback__SigningKey").GetString());
        Assert.Contains("@Microsoft.KeyVault(VaultName=", settings.GetProperty("Flow__Url").GetString());
        Assert.Equal("managedidentity", settings.GetProperty("ServiceBus__credential").GetString());
        Assert.Equal("[variables('queueName')]", settings.GetProperty("InvoiceQueueName").GetString());
        Assert.Equal("invoice-approvals", Arm().GetProperty("variables").GetProperty("queueName").GetString());
        foreach (var key in new[] { "Approval__ManagerEmail", "Approval__FinanceEmail", "Approval__EscalationEmail", "Approval__FinanceThreshold", "Approval__StageTimeoutMinutes", "Callback__BaseUrl", "Flow__Audience" })
            Assert.True(settings.TryGetProperty(key, out _), $"missing app setting {key}");
        Assert.True(Resources("Microsoft.KeyVault/vaults").Single().GetProperty("properties").GetProperty("enableRbacAuthorization").GetBoolean());
    }
}
