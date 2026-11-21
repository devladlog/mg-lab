using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using FlowDeploy;
using Xunit;

namespace FlowTests;

/// <summary>FlowDeploy against an in-memory Dataverse Web API (workflows and connectionreferences only).</summary>
public class DeployTests
{
    private sealed class FakeDataverse : HttpMessageHandler
    {
        public List<(HttpMethod Method, string Path, JsonObject? Body, string? Solution)> Requests { get; } = new();
        public Dictionary<string, JsonObject> Workflows { get; } = new();
        public Dictionary<string, JsonObject> References { get; } = new();
        public string? FailOn { get; set; }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage r, CancellationToken ct)
        {
            var path = Uri.UnescapeDataString(r.RequestUri!.PathAndQuery.Replace("/api/data/v9.2/", ""));
            var body = r.Content is null ? null : JsonNode.Parse(await r.Content.ReadAsStringAsync(ct)) as JsonObject;
            Requests.Add((r.Method, path, body, r.Headers.TryGetValues("MSCRM.SolutionUniqueName", out var s) ? s.Single() : null));
            Assert.Equal("Bearer", r.Headers.Authorization?.Scheme);
            Assert.Equal("4.0", r.Headers.GetValues("OData-Version").Single());
            if (r.Method == HttpMethod.Patch) Assert.Equal("*", r.Headers.GetValues("If-Match").Single());

            if (FailOn != null && path.StartsWith(FailOn))
                return Json(HttpStatusCode.Forbidden, """{"error":{"code":"0x80040220","message":"Principal user is missing prvCreateWorkflow privilege."}}""");

            if (r.Method == HttpMethod.Get && path.StartsWith("connectionreferences"))
            {
                var name = path.Split("eq '")[1].TrimEnd('\'');
                return Json(HttpStatusCode.OK, new JsonObject { ["value"] = References.TryGetValue(name, out var row) ? new JsonArray(row.DeepClone()) : new JsonArray() }.ToJsonString());
            }
            if (r.Method == HttpMethod.Post && path == "connectionreferences")
            {
                References[(string)body!["connectionreferencelogicalname"]!] = new JsonObject { ["connectionreferenceid"] = Guid.NewGuid().ToString(), ["connectionid"] = null };
                return new HttpResponseMessage(HttpStatusCode.NoContent);
            }
            if (r.Method == HttpMethod.Get && path.StartsWith("workflows"))
            {
                var name = path.Split("name eq '")[1].TrimEnd('\'');
                var match = Workflows.Where(w => (string)w.Value["name"]! == name).Select(w => (JsonNode)new JsonObject { ["workflowid"] = w.Key, ["statecode"] = (int)w.Value["statecode"]! });
                return Json(HttpStatusCode.OK, new JsonObject { ["value"] = new JsonArray(match.ToArray()) }.ToJsonString());
            }
            if (r.Method == HttpMethod.Post && path == "workflows")
            {
                var id = "00000000-0000-0000-0000-00000000f10e";
                body!["statecode"] = 0; // Learn: flows created this way are off
                Workflows[id] = body;
                var created = new HttpResponseMessage(HttpStatusCode.NoContent);
                created.Headers.Add("OData-EntityId", $"https://contoso.crm4.dynamics.com/api/data/v9.2/workflows({id})");
                return created;
            }
            if (r.Method == HttpMethod.Patch && path.StartsWith("workflows("))
            {
                var id = path[10..^1];
                foreach (var p in body!) Workflows[id][p.Key] = p.Value?.DeepClone();
                return new HttpResponseMessage(HttpStatusCode.NoContent);
            }
            return new HttpResponseMessage(HttpStatusCode.NotFound);
        }

        private static HttpResponseMessage Json(HttpStatusCode status, string json) =>
            new(status) { Content = new StringContent(json, Encoding.UTF8, "application/json") };

        public void BindConnections()
        {
            foreach (var r in References.Values) r["connectionid"] = "shared-connection-" + Guid.Empty.ToString("N");
        }
    }

    private static readonly Func<string, string?> Env = name => name switch
    {
        "DATAVERSE_URL" => "https://contoso.crm4.dynamics.com",
        "DATAVERSE_TOKEN" => "test-token",
        _ => null,
    };

    private static async Task<(int Code, string Out, string Err)> Run(FakeDataverse dv, params string[] extra)
    {
        var output = new StringWriter();
        var error = new StringWriter();
        var code = await Cli.RunAsync(new[] { Files.ClientDataPath }.Concat(extra).ToArray(), output, error, Env, dv);
        return (code, output.ToString(), error.ToString());
    }

    [Fact]
    public async Task Dry_run_prints_the_plan_and_sends_nothing()
    {
        var dv = new FakeDataverse();
        var output = new StringWriter();
        var code = await Cli.RunAsync(new[] { Files.ClientDataPath, "--dry-run", "--activate" }, output, new StringWriter(), _ => null, dv);

        Assert.Equal(0, code);
        Assert.Empty(dv.Requests);
        Assert.Contains("connection reference contoso_EquipmentDeskDataverse -> /providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps", output.ToString());
        Assert.Contains("connection reference contoso_EquipmentDeskOutlook -> /providers/Microsoft.PowerApps/apis/shared_office365", output.ToString());
    }

    [Fact]
    public async Task First_deploy_creates_references_and_the_flow_in_the_solution_and_leaves_it_off()
    {
        var dv = new FakeDataverse();
        var (code, output, _) = await Run(dv);

        Assert.Equal(0, code);
        Assert.Equal(2, dv.References.Count);
        Assert.All(dv.Requests.Where(r => r.Method == HttpMethod.Post), r => Assert.Equal("EquipmentDesk", r.Solution));
        var flow = dv.Workflows.Single().Value;
        Assert.Equal(5, (int)flow["category"]!);         // modern flow
        Assert.Equal(1, (int)flow["type"]!);             // definition
        Assert.Equal("none", (string)flow["primaryentity"]!);
        Assert.Equal("SendLoanReminder", (string)flow["name"]!);
        Assert.Equal(0, (int)flow["statecode"]!);
        Assert.Contains("Left off", output);
    }

    [Fact]
    public async Task Clientdata_is_sent_as_a_JSON_string_with_the_same_content_as_the_file()
    {
        var dv = new FakeDataverse();
        await Run(dv);

        var sent = dv.Workflows.Single().Value["clientdata"]!;
        Assert.Equal(System.Text.Json.JsonValueKind.String, sent.GetValueKind()); // a string column, not a nested object
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(File.ReadAllText(Files.ClientDataPath)), JsonNode.Parse((string)sent!)));
    }

    [Fact]
    public async Task Activate_refuses_while_a_connection_reference_has_no_connection()
    {
        var dv = new FakeDataverse();
        var (code, output, _) = await Run(dv, "--activate");

        Assert.Equal(2, code);
        Assert.Contains("Not turned on: pick a connection for contoso_EquipmentDeskDataverse, contoso_EquipmentDeskOutlook", output);
        Assert.Equal(0, (int)dv.Workflows.Single().Value["statecode"]!);
    }

    [Fact]
    public async Task Activate_turns_the_flow_on_once_connections_are_picked()
    {
        var dv = new FakeDataverse();
        await Run(dv);
        dv.BindConnections();
        var (code, output, _) = await Run(dv, "--activate");

        Assert.Equal(0, code);
        Assert.Equal(1, (int)dv.Workflows.Single().Value["statecode"]!);
        Assert.Contains("Flow 'SendLoanReminder': on", output);
        Assert.Equal(1, dv.Workflows.Count); // updated, not created twice
    }

    [Fact]
    public async Task Redeploying_a_flow_that_is_on_turns_it_off_updates_it_and_turns_it_back_on()
    {
        var dv = new FakeDataverse();
        await Run(dv);
        dv.BindConnections();
        await Run(dv, "--activate");
        dv.Requests.Clear();

        var (code, _, _) = await Run(dv);   // no --activate: it was on, so it goes back on
        var patches = dv.Requests.Where(r => r.Method == HttpMethod.Patch).Select(r => r.Body!.ToJsonString()).ToList();

        Assert.Equal(0, code);
        Assert.Equal("""{"statecode":0}""", patches[0]);
        Assert.Contains("clientdata", patches[1]);
        Assert.Equal("""{"statecode":1}""", patches[2]);
        Assert.DoesNotContain(dv.Requests, r => r.Method == HttpMethod.Post);
    }

    [Fact]
    public async Task A_Dataverse_error_is_reported_with_its_message()
    {
        var dv = new FakeDataverse { FailOn = "workflows" };
        var (code, _, error) = await Run(dv);

        Assert.Equal(1, code);
        Assert.Contains("403", error);
        Assert.Contains("Principal user is missing prvCreateWorkflow privilege.", error);
    }

    [Fact]
    public void A_clientdata_file_without_connection_reference_names_is_rejected()
    {
        var path = Path.GetTempFileName();
        File.WriteAllText(path, """{"properties":{"connectionReferences":{"shared_office365":{"runtimeSource":"embedded","connection":{},"api":{"name":"shared_office365"}}},"definition":{}},"schemaVersion":"1.0.0.0"}""");
        var ex = Assert.Throws<InvalidDataException>(() => FlowDeployer.LoadClientData(path));
        Assert.Contains("connectionReferenceLogicalName", ex.Message);
        File.Delete(path);
    }
}
