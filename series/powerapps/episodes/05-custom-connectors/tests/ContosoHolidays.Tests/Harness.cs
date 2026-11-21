using System.Collections.Concurrent;
using System.Net;
using System.Net.Http;
using System.Text;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.OpenApi.Models;
using Microsoft.OpenApi.Readers;
using Microsoft.PowerFx.Connectors;
using Newtonsoft.Json.Linq;

namespace ContosoHolidays.Tests;

/// <summary>Paths to the connector files and the recorded responses of the real holiday source.</summary>
public static class Files
{
    public static string Connector(string name) => Path.Combine(AppContext.BaseDirectory, "Connector", name);
    public static string Fixture(string name) => Path.Combine(AppContext.BaseDirectory, "fixtures", name);
    public static string App(string name) => Path.Combine(AppContext.BaseDirectory, "App", name);

    public static JObject Swagger() => JObject.Parse(File.ReadAllText(Connector("apiDefinition.swagger.json")));
    public static JObject ApiProperties() => JObject.Parse(File.ReadAllText(Connector("apiProperties.json")));

    public static OpenApiDocument OpenApi(out OpenApiDiagnostic diagnostic)
    {
        using var stream = File.OpenRead(Connector("apiDefinition.swagger.json"));
        return new OpenApiStreamReader().Read(stream, out diagnostic);
    }
}

/// <summary>
/// Stands in for date.nager.at in tests: answers /api/v3/PublicHolidays/{year}/{cc} and /api/v3/AvailableCountries with
/// responses recorded from the real API (fixtures/*.json, Nov 2026), 404 like the real API for unknown countries, and
/// records every request. Tests can also plug in their own answers.
/// </summary>
public sealed class FakeHolidaySource
{
    public List<HttpRequestMessage> Requests { get; } = new();
    public Func<HttpRequestMessage, HttpResponseMessage?>? Override { get; set; }

    public Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        Requests.Add(request);
        if (Override?.Invoke(request) is { } custom) return Task.FromResult(custom);

        var segments = request.RequestUri!.AbsolutePath.Trim('/').Split('/');
        if (segments is [.., "PublicHolidays", var year, var cc])
        {
            var file = Files.Fixture($"PublicHolidays-{year}-{cc.ToUpperInvariant()}.json");
            if (File.Exists(file)) return Task.FromResult(Json(HttpStatusCode.OK, File.ReadAllText(file)));
            return Task.FromResult(Json(HttpStatusCode.NotFound,
                "{\"title\":\"Unknown country code\",\"status\":404,\"detail\":\"The country code provided is invalid or not recognized.\"}"));
        }
        if (segments is [.., "AvailableCountries"])
            return Task.FromResult(Json(HttpStatusCode.OK, File.ReadAllText(Files.Fixture("AvailableCountries.json"))));
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));
    }

    public static HttpResponseMessage Json(HttpStatusCode status, string body) =>
        new(status) { Content = new StringContent(body, Encoding.UTF8, "application/json") };

    public static IEnumerable<JObject> Holidays(string fixture) =>
        JArray.Parse(File.ReadAllText(Files.Fixture(fixture))).OfType<JObject>();
}

/// <summary>IScriptContext for tests: the platform's request, operation id and SendAsync.</summary>
public sealed class TestScriptContext : IScriptContext
{
    private readonly Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send;

    public TestScriptContext(string operationId, HttpRequestMessage request, Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send)
    {
        OperationId = operationId;
        Request = request;
        this.send = send;
    }

    public string CorrelationId { get; } = Guid.Empty.ToString();
    public string OperationId { get; }
    public HttpRequestMessage Request { get; }
    public ILogger Logger { get; } = NullLogger.Instance;
    public Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => send(request, cancellationToken);
}

public static class ScriptRunner
{
    /// <summary>Runs script.csx the way the platform does: new Script, context set, ExecuteAsync.</summary>
    public static async Task<(HttpResponseMessage Response, JObject? Body)> RunAsync(
        string operationId, string url, Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> backend)
    {
        var script = new Script();
        script.Initialize(new TestScriptContext(operationId, new HttpRequestMessage(HttpMethod.Get, url), backend), CancellationToken.None);
        var response = await script.ExecuteAsync();
        var text = response.Content is null ? "" : await response.Content.ReadAsStringAsync();
        return (response, text.StartsWith('{') ? JObject.Parse(text) : null);
    }

    public static Task<(HttpResponseMessage Response, JObject? Body)> DaysOff(FakeHolidaySource source, string query, string country = "PT") =>
        RunAsync("GetDaysOff", $"https://date.nager.at/api/v3/DaysOff/{country}?{query}", source.SendAsync);
}

/// <summary>
/// What the connector platform does between Power Fx and the API, as far as this connector needs it: turn the
/// relative request from the Power Fx connector library into host + basePath + path, find the operation by path,
/// run script.csx for the operations in apiProperties.json "scriptOperations", otherwise call the backend directly.
/// </summary>
public sealed class PlatformHandler : HttpMessageHandler
{
    private readonly Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> backend;
    private readonly HashSet<string> scriptOperations;
    private readonly List<(string OperationId, System.Text.RegularExpressions.Regex Path)> operations = new();
    public ConcurrentQueue<string> Calls { get; } = new();

    public PlatformHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> backend)
    {
        this.backend = backend;
        var swagger = Files.Swagger();
        scriptOperations = Files.ApiProperties()["properties"]!["scriptOperations"]!.Select(t => (string)t!).ToHashSet();
        var basePath = (string)swagger["basePath"]!;
        foreach (var path in ((JObject)swagger["paths"]!).Properties())
        foreach (var op in ((JObject)path.Value).Properties())
        {
            var pattern = "^" + System.Text.RegularExpressions.Regex.Replace(basePath + path.Name, @"\{[^}]+\}", "[^/]+") + "$";
            operations.Add(((string)op.Value["operationId"]!, new(pattern, System.Text.RegularExpressions.RegexOptions.IgnoreCase)));
        }
    }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        var absolute = new Uri(new Uri("https://" + (string)Files.Swagger()["host"]!), request.RequestUri!.OriginalString);
        var operationId = operations.First(o => o.Path.IsMatch(absolute.AbsolutePath)).OperationId;
        Calls.Enqueue($"{operationId} {absolute.PathAndQuery}");
        var forwarded = new HttpRequestMessage(request.Method, absolute);
        if (!scriptOperations.Contains(operationId)) return await backend(forwarded, ct);

        var script = new Script();
        script.Initialize(new TestScriptContext(operationId, forwarded, backend), ct);
        return await script.ExecuteAsync();
    }
}

/// <summary>Runtime context for the Power Fx connector library: every connector call goes through the PlatformHandler.</summary>
public sealed class PlatformRuntimeContext(PlatformHandler handler) : BaseRuntimeConnectorContext
{
    public override TimeZoneInfo TimeZoneInfo => TimeZoneInfo.Utc;
    public override HttpMessageInvoker GetInvoker(string @namespace) => new(handler, disposeHandler: false);
}
