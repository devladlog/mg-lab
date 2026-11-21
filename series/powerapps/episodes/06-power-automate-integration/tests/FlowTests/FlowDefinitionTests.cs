using System.Text.RegularExpressions;
using FlowTests.Wdl;
using Newtonsoft.Json.Linq;
using Xunit;

namespace FlowTests;

/// <summary>Static checks on src/flow/SendLoanReminder.clientdata.json against Learn's documented shapes and our rules.</summary>
public class FlowDefinitionTests
{
    private static readonly JObject ClientData = Files.ClientData();
    private static readonly JObject Definition = Files.Definition();

    /// <summary>All actions at any depth (inside If branches too), with the scope they live in.</summary>
    private static IEnumerable<(string Name, JObject Action, JObject Scope)> AllActions(JObject? scope = null)
    {
        scope ??= (JObject)Definition["actions"]!;
        foreach (var p in scope.Properties())
        {
            var action = (JObject)p.Value;
            yield return (p.Name, action, scope);
            foreach (var inner in new[] { action["actions"], action["else"]?["actions"] }.OfType<JObject>())
                foreach (var a in AllActions(inner)) yield return a;
        }
    }

    [Fact]
    public void Clientdata_has_the_shape_Learn_documents_for_creating_a_flow_with_code()
    {
        Assert.Equal("1.0.0.0", (string)ClientData["schemaVersion"]!);
        Assert.NotNull(ClientData["properties"]!["connectionReferences"]);
        Assert.Equal("https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#", (string)Definition["$schema"]!);
        Assert.Equal("Object", (string)Definition["parameters"]!["$connections"]!["type"]!);
        Assert.Equal("SecureObject", (string)Definition["parameters"]!["$authentication"]!["type"]!);
    }

    [Fact]
    public void The_trigger_is_Power_Apps_V2_with_one_typed_required_input()
    {
        var trigger = (JObject)Definition["triggers"]!["manual"]!;
        Assert.Equal("Request", (string)trigger["type"]!);
        Assert.Equal("PowerAppV2", (string)trigger["kind"]!);

        var schema = (JObject)trigger["inputs"]!["schema"]!;
        var input = Assert.Single(((JObject)schema["properties"]!).Properties());
        Assert.Equal("LoanId", (string)input.Value["title"]!);
        Assert.Equal("string", (string)input.Value["type"]!);
        Assert.Equal("TEXT", (string)input.Value["x-ms-content-hint"]!);
        Assert.Equal(new[] { input.Name }, schema["required"]!.Select(r => (string)r!));
    }

    [Fact]
    public void The_app_cannot_choose_who_gets_the_email()
    {
        // Learn (Power Automate pane): arguments from Power Apps can be intercepted and changed; validate them.
        // So the app sends only an id; recipient, subject and body come from Dataverse, never from triggerBody().
        var send = AllActions().Single(a => a.Name == "Send_reminder").Action;
        Assert.DoesNotContain("triggerBody", send["inputs"]!.ToString());
        Assert.Contains("body('Get_loan')?['contoso_borroweremail']", (string)send["inputs"]!["parameters"]!["emailMessage/To"]!);
        Assert.Contains("endsWith(coalesce(body('Get_loan')?['contoso_borroweremail'], ''), '@contoso.com')", (string)Definition["actions"]!["Problem"]!["inputs"]!);
    }

    [Fact]
    public void Every_connector_action_has_a_connection_reference_and_every_reference_is_used()
    {
        var refs = (JObject)ClientData["properties"]!["connectionReferences"]!;
        var used = AllActions().Where(a => (string)a.Action["type"]! == "OpenApiConnection")
            .Select(a => (string)a.Action["inputs"]!["host"]!["connectionName"]!).Distinct().ToList();

        Assert.Equal(refs.Properties().Select(p => p.Name).OrderBy(n => n), used.OrderBy(n => n));
        Assert.All(refs.Properties(), r =>
        {
            Assert.Matches("^contoso_", (string)r.Value["connection"]!["connectionReferenceLogicalName"]!); // solution-aware
            Assert.Equal(r.Name, (string)r.Value["api"]!["name"]!);
            Assert.Equal("invoker", (string)r.Value["runtimeSource"]!); // "Provided by run-only user"
        });
        Assert.All(AllActions().Where(a => (string)a.Action["type"]! == "OpenApiConnection"), a =>
            Assert.Equal("/providers/Microsoft.PowerApps/apis/" + (string)a.Action["inputs"]!["host"]!["connectionName"]!, (string)a.Action["inputs"]!["host"]!["apiId"]!));
    }

    [Fact]
    public void Every_runAfter_points_at_an_action_in_the_same_scope_with_valid_statuses()
    {
        var statuses = new[] { "Succeeded", "Failed", "Skipped", "TimedOut" };
        Assert.All(AllActions(), a =>
        {
            foreach (var dep in ((JObject)a.Action["runAfter"]!).Properties())
            {
                Assert.True(a.Scope.ContainsKey(dep.Name), $"{a.Name} runs after {dep.Name}, which isn't in its scope");
                Assert.All(dep.Value, s => Assert.Contains((string)s!, statuses));
            }
        });
    }

    [Fact]
    public void Every_expression_parses_uses_known_functions_and_names_real_actions()
    {
        var names = AllActions().Select(a => a.Name).ToHashSet();
        var expressions = Expressions.ExpressionsIn(Definition["actions"]!).ToList();
        Assert.True(expressions.Count >= 10);

        foreach (var text in expressions)
        {
            var node = Expressions.Parse(text); // throws on syntax errors
            foreach (var call in node.Descendants().Prepend(node).OfType<Expressions.Call>())
            {
                Assert.Contains(call.Name, Expressions.Functions);
                if (call.Name is "body" or "outputs")
                    Assert.Contains((string)((Expressions.Literal)call.Args[0]).Value!, names);
            }
        }
    }

    [Fact]
    public void Every_response_is_PowerApp_and_declares_the_same_outputs()
    {
        // Learn (troubleshooting): Power Apps stores the flow's outputs in the app; removing an output breaks the call and a
        // missing one reads as blank. So every Respond action declares the same two outputs, and fills both.
        var responses = AllActions().Where(a => (string)a.Action["type"]! == "Response").ToList();
        Assert.Equal(4, responses.Count);
        var first = responses[0].Action["inputs"]!["schema"]!;
        Assert.All(responses, r =>
        {
            Assert.Equal("PowerApp", (string)r.Action["kind"]!);
            Assert.Equal(200, (int)r.Action["inputs"]!["statusCode"]!);
            Assert.True(JToken.DeepEquals(first, r.Action["inputs"]!["schema"]), r.Name + " has different outputs");
            var body = (JObject)r.Action["inputs"]!["body"]!;
            Assert.Equal(new[] { "message", "sent" }, body.Properties().Select(p => p.Name).OrderBy(n => n));
            Assert.Equal(JTokenType.Boolean, body["sent"]!.Type);
        });
        Assert.Equal("boolean", (string)first["properties"]!["sent"]!["type"]!);
        Assert.Equal("string", (string)first["properties"]!["message"]!["type"]!);
    }

    [Fact]
    public void Output_names_are_lower_case_identifiers()
    {
        var props = (JObject)AllActions().First(a => (string)a.Action["type"]! == "Response").Action["inputs"]!["schema"]!["properties"]!;
        Assert.All(props.Properties(), p =>
        {
            Assert.Matches(new Regex("^[a-z][a-zA-Z0-9]*$"), p.Name);
            Assert.Equal(p.Name, (string)p.Value["title"]!);
        });
    }

    [Fact]
    public void It_uses_only_documented_connector_operations()
    {
        // Learn connector reference: Dataverse "Get a row by ID" = GetItem, Office 365 Outlook "Send an email (V2)" = SendEmailV2.
        var ops = AllActions().Where(a => (string)a.Action["type"]! == "OpenApiConnection")
            .Select(a => $"{(string)a.Action["inputs"]!["host"]!["connectionName"]!}/{(string)a.Action["inputs"]!["host"]!["operationId"]!}");
        Assert.Equal(new[] { "shared_commondataserviceforapps/GetItem", "shared_office365/SendEmailV2" }, ops.OrderBy(o => o));
    }
}
