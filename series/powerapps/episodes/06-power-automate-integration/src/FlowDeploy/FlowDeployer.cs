using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace FlowDeploy;

public sealed record DeployOptions(string ClientDataPath, string Name, string Solution, bool Activate, bool DryRun, string Description);

public sealed class DataverseException(string message) : Exception(message);

/// <summary>
/// Creates or updates a solution-aware cloud flow from a clientdata file with the Dataverse Web API, the way Learn's
/// "Work with cloud flows using code" describes it: a workflow row with category 5 (modern flow), type 1 (definition),
/// primaryentity "none" and clientdata = the JSON string of { properties: { connectionReferences, definition }, schemaVersion }.
/// Flows created this way are off (statecode 0). Connection references are created in the solution if missing; the
/// connection itself is picked by a person in the maker portal, so the flow is only turned on when every reference has one.
/// </summary>
public sealed class FlowDeployer(HttpClient http, TextWriter log)
{
    private static readonly JsonSerializerOptions Compact = new() { WriteIndented = false };

    public async Task<int> DeployAsync(DeployOptions o, CancellationToken ct = default)
    {
        var (clientData, references) = LoadClientData(o.ClientDataPath);

        if (o.DryRun)
        {
            log.WriteLine($"Plan for '{o.Name}' in solution {o.Solution} (dry run, nothing sent):");
            foreach (var r in references)
                log.WriteLine($"  connection reference {r.LogicalName} -> {r.ConnectorId} (create if missing)");
            log.WriteLine($"  workflow '{o.Name}': create (category 5, type 1, primaryentity none) or update clientdata ({clientData.Length} chars)");
            log.WriteLine(o.Activate ? "  then turn it on (statecode 1) if every connection reference has a connection" : "  leave it off");
            return 0;
        }

        var unbound = new List<string>();
        foreach (var r in references)
        {
            var existing = await GetSingleAsync($"connectionreferences?$select=connectionreferenceid,connectionid&$filter=connectionreferencelogicalname eq '{Escape(r.LogicalName)}'", ct);
            if (existing is null)
            {
                await SendAsync(HttpMethod.Post, "connectionreferences", new JsonObject
                {
                    ["connectionreferencelogicalname"] = r.LogicalName,
                    ["connectionreferencedisplayname"] = r.DisplayName,
                    ["connectorid"] = r.ConnectorId,
                }, o.Solution, ct);
                log.WriteLine($"Connection reference {r.LogicalName}: created, no connection yet");
                unbound.Add(r.LogicalName);
            }
            else if (string.IsNullOrEmpty((string?)existing["connectionid"]))
            {
                log.WriteLine($"Connection reference {r.LogicalName}: exists, no connection yet");
                unbound.Add(r.LogicalName);
            }
            else log.WriteLine($"Connection reference {r.LogicalName}: exists, has a connection");
        }

        var flow = await GetSingleAsync($"workflows?$select=workflowid,statecode&$filter=category eq 5 and name eq '{Escape(o.Name)}'", ct);
        string id;
        var wasOn = false;
        if (flow is null)
        {
            var response = await SendAsync(HttpMethod.Post, "workflows", new JsonObject
            {
                ["category"] = 5,
                ["name"] = o.Name,
                ["type"] = 1,
                ["primaryentity"] = "none",
                ["description"] = o.Description,
                ["clientdata"] = clientData,
            }, o.Solution, ct);
            id = IdFromEntityHeader(response);
            log.WriteLine($"Flow '{o.Name}': created ({id}), off");
        }
        else
        {
            id = (string)flow["workflowid"]!;
            wasOn = (int?)flow["statecode"] == 1;
            if (wasOn) await SendAsync(HttpMethod.Patch, $"workflows({id})", new JsonObject { ["statecode"] = 0 }, null, ct);
            await SendAsync(HttpMethod.Patch, $"workflows({id})", new JsonObject { ["clientdata"] = clientData, ["description"] = o.Description }, null, ct);
            log.WriteLine($"Flow '{o.Name}': definition updated ({id})" + (wasOn ? ", was on" : ""));
        }

        if (!o.Activate && !wasOn)
        {
            log.WriteLine("Left off. Run again with --activate once the connection references have connections.");
            return 0;
        }
        if (unbound.Count > 0)
        {
            log.WriteLine("Not turned on: pick a connection for " + string.Join(", ", unbound)
                + " (maker portal > Solutions > " + o.Solution + " > Connection references), then run again with --activate.");
            return 2;
        }
        await SendAsync(HttpMethod.Patch, $"workflows({id})", new JsonObject { ["statecode"] = 1 }, null, ct);
        log.WriteLine($"Flow '{o.Name}': on");
        return 0;
    }

    internal sealed record Reference(string ApiName, string LogicalName, string DisplayName, string ConnectorId);

    /// <summary>Reads the file, checks the shape Learn documents, returns clientdata as a compact JSON string.</summary>
    internal static (string ClientData, IReadOnlyList<Reference> References) LoadClientData(string path)
    {
        var node = JsonNode.Parse(File.ReadAllText(path)) as JsonObject ?? throw new InvalidDataException("clientdata must be a JSON object");
        var properties = node["properties"] as JsonObject ?? throw new InvalidDataException("missing properties");
        if (properties["definition"] is not JsonObject) throw new InvalidDataException("missing properties.definition");
        if (node["schemaVersion"] is null) throw new InvalidDataException("missing schemaVersion");
        var refs = (properties["connectionReferences"] as JsonObject ?? new JsonObject()).Select(kv =>
        {
            var logical = (string?)kv.Value?["connection"]?["connectionReferenceLogicalName"]
                ?? throw new InvalidDataException($"connection reference {kv.Key} has no connectionReferenceLogicalName (solution flows need one)");
            var api = (string?)kv.Value?["api"]?["name"] ?? kv.Key;
            return new Reference(api, logical, "Equipment Desk - " + api.Replace("shared_", ""), "/providers/Microsoft.PowerApps/apis/" + api);
        }).ToList();
        return (node.ToJsonString(Compact), refs);
    }

    private static string Escape(string value) => value.Replace("'", "''");

    private static string IdFromEntityHeader(HttpResponseMessage response)
    {
        // Learn: 204 No Content with OData-EntityId: [Organization URI]/api/data/v9.2/workflows(<workflowid>)
        var header = response.Headers.TryGetValues("OData-EntityId", out var values) ? values.First() : throw new DataverseException("no OData-EntityId header");
        var open = header.LastIndexOf('(');
        return header[(open + 1)..header.LastIndexOf(')')];
    }

    private async Task<JsonObject?> GetSingleAsync(string path, CancellationToken ct)
    {
        using var request = NewRequest(HttpMethod.Get, path, null, null);
        using var response = await http.SendAsync(request, ct);
        await EnsureSuccess(response, ct);
        var json = JsonNode.Parse(await response.Content.ReadAsStringAsync(ct));
        return json?["value"]?.AsArray().FirstOrDefault() as JsonObject;
    }

    private async Task<HttpResponseMessage> SendAsync(HttpMethod method, string path, JsonObject body, string? solution, CancellationToken ct)
    {
        using var request = NewRequest(method, path, body, solution);
        var response = await http.SendAsync(request, ct);
        await EnsureSuccess(response, ct);
        return response;
    }

    private static HttpRequestMessage NewRequest(HttpMethod method, string path, JsonObject? body, string? solution)
    {
        var request = new HttpRequestMessage(method, path);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Headers.Add("OData-MaxVersion", "4.0");
        request.Headers.Add("OData-Version", "4.0");
        if (method == HttpMethod.Patch) request.Headers.Add("If-Match", "*"); // update only, never create by accident
        if (solution != null) request.Headers.Add("MSCRM.SolutionUniqueName", solution);
        if (body != null) request.Content = new StringContent(body.ToJsonString(Compact), Encoding.UTF8, "application/json");
        return request;
    }

    private static async Task EnsureSuccess(HttpResponseMessage response, CancellationToken ct)
    {
        if (response.IsSuccessStatusCode) return;
        var text = response.Content is null ? "" : await response.Content.ReadAsStringAsync(ct);
        string? message = null;
        try { message = (string?)JsonNode.Parse(text)?["error"]?["message"]; } catch (JsonException) { }
        throw new DataverseException($"{(int)response.StatusCode} {response.RequestMessage?.Method} {response.RequestMessage?.RequestUri}: {message ?? text}");
    }
}
