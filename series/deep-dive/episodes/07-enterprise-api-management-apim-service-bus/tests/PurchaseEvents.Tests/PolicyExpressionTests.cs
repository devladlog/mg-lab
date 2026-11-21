using System.Collections;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using Contoso.PurchaseEvents;
using Microsoft.CodeAnalysis.CSharp.Scripting;
using Microsoft.CodeAnalysis.Scripting;
using Newtonsoft.Json.Linq;

namespace PurchaseEvents.Tests;

// ---- A stand-in for the APIM `context` object, TEST ONLY. It has the few members the policy uses, with the same
// ---- shapes Learn documents (Headers: IReadOnlyDictionary<string,string[]> with GetValueOrDefault(name, default)).
public sealed class HeaderBag : IReadOnlyDictionary<string, string[]>
{
    private readonly Dictionary<string, string[]> _d = new(StringComparer.OrdinalIgnoreCase);
    public HeaderBag Add(string name, string value) { _d[name] = [value]; return this; }
    public string GetValueOrDefault(string name, string defaultValue) => _d.TryGetValue(name, out var v) ? string.Join(",", v) : defaultValue;
    public string[] this[string key] => _d[key];
    public IEnumerable<string> Keys => _d.Keys;
    public IEnumerable<string[]> Values => _d.Values;
    public int Count => _d.Count;
    public bool ContainsKey(string key) => _d.ContainsKey(key);
    public bool TryGetValue(string key, out string[] value) => _d.TryGetValue(key, out value!);
    public IEnumerator<KeyValuePair<string, string[]>> GetEnumerator() => _d.GetEnumerator();
    IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
}

public sealed class StubBody(string json)
{
    public T As<T>(bool preserveContent = false) =>
        typeof(T) == typeof(JObject) ? (T)(object)JObject.Parse(json)
        : typeof(T) == typeof(string) ? (T)(object)json
        : throw new NotSupportedException(typeof(T).Name);
}

public sealed class StubRequest { public HeaderBag Headers { get; } = new(); public StubBody? Body { get; set; } }
public sealed class StubResponse { public int StatusCode { get; set; } }

public sealed class StubContext
{
    public StubRequest Request { get; } = new();
    public StubResponse Response { get; } = new();
    public Guid RequestId { get; set; } = Guid.Parse("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");
    public Dictionary<string, object> Variables { get; } = new();
}

public sealed class Globals { public StubContext context { get; set; } = new(); }

/// <summary>Compiles EVERY policy expression with Roslyn and runs the ones that carry the logic.</summary>
public class PolicyExpressionTests
{
    internal static readonly string PolicyPath = Path.Combine(Paths.EpisodeRoot, "apim", "policies", "purchase-events.policy.xml");

    private static readonly ScriptOptions Options = ScriptOptions.Default
        .AddReferences(typeof(JObject).Assembly, typeof(Regex).Assembly, typeof(HeaderBag).Assembly)
        .AddImports("System", "System.Linq", "System.Text.RegularExpressions", "Newtonsoft.Json", "Newtonsoft.Json.Linq");

    /// <summary>"@(expr)" or "@{ statements }" -> C# the script engine can run.</summary>
    internal static string ToCode(string raw)
    {
        raw = raw.Trim();
        return raw[1] == '(' ? raw[2..^1] : raw[2..^1];
    }

    private static IEnumerable<(string Where, string Code)> AllExpressions()
    {
        var doc = XDocument.Load(PolicyPath);
        foreach (var el in doc.Descendants())
        {
            foreach (var a in el.Attributes().Where(a => a.Value.TrimStart().StartsWith("@(") || a.Value.TrimStart().StartsWith("@{")))
                yield return ($"{el.Name.LocalName}/@{a.Name.LocalName}", ToCode(a.Value));
            if (!el.HasElements && el.Value.TrimStart().StartsWith("@{") || !el.HasElements && el.Value.TrimStart().StartsWith("@("))
                yield return ($"{el.Name.LocalName} text", ToCode(el.Value));
        }
    }

    private static string Code(string xpathLike)
    {
        var doc = XDocument.Load(PolicyPath);
        return xpathLike switch
        {
            "idempotencyKey" => ToCode(doc.Descendants("set-variable").First(e => (string?)e.Attribute("name") == "idempotencyKey").Attribute("value")!.Value),
            "label" => ToCode(doc.Descendants("set-variable").First(e => (string?)e.Attribute("name") == "label").Attribute("value")!.Value),
            "badKey" => ToCode(doc.Descendants("when").First(e => ((string?)e.Attribute("condition") ?? "").Contains("Idempotency") || ((string?)e.Attribute("condition") ?? "").Contains("idempotencyKey")).Attribute("condition")!.Value),
            "broker" => ToCode(doc.Descendants("set-header").First(e => (string?)e.Attribute("name") == "BrokerProperties").Element("value")!.Value),
            "accepted" => ToCode(doc.Descendants("outbound").Single().Descendants("when").Single().Element("set-body")!.Value),
            "isCreated" => ToCode(doc.Descendants("outbound").Single().Descendants("when").Single().Attribute("condition")!.Value),
            _ => throw new ArgumentOutOfRangeException(xpathLike),
        };
    }

    private static Task<T> Run<T>(string code, StubContext ctx) =>
        CSharpScript.EvaluateAsync<T>(code, Options, new Globals { context = ctx }, typeof(Globals));

    [Fact]
    public void Every_expression_in_the_policy_compiles()
    {
        var all = AllExpressions().ToList();
        Assert.True(all.Count >= 7, $"expected the policy to contain at least 7 expressions, found {all.Count}");
        foreach (var (where, code) in all)
        {
            var errors = CSharpScript.Create<object>(code, Options, typeof(Globals)).Compile()
                .Where(d => d.Severity == Microsoft.CodeAnalysis.DiagnosticSeverity.Error).ToList();
            Assert.True(errors.Count == 0, $"{where}: {string.Join("; ", errors)}\n{code}");
        }
    }

    [Theory]
    [InlineData("  3F2504E0-4F89-11D3-9A0C-0305E82C3301 ", "3f2504e0-4f89-11d3-9a0c-0305e82c3301")]
    [InlineData(null, "")]
    public async Task The_idempotency_key_is_trimmed_and_lower_cased(string? header, string expected)
    {
        var ctx = new StubContext();
        if (header is not null) ctx.Request.Headers.Add("Idempotency-Key", header);
        Assert.Equal(expected, await Run<string>(Code("idempotencyKey"), ctx));
    }

    [Theory]
    [InlineData("3f2504e0-4f89-11d3-9a0c-0305e82c3301", false)]
    [InlineData("", true)]
    [InlineData("123", true)]
    [InlineData("3f2504e0-4f89-11d3-9a0c-0305e82c330", true)]
    [InlineData("3f2504e0-4f89-11d3-9a0c-0305e82c3301-extra", true)]
    public async Task Only_a_guid_passes_the_idempotency_check(string key, bool rejected)
    {
        var ctx = new StubContext();
        ctx.Variables["idempotencyKey"] = key;
        Assert.Equal(rejected, await Run<bool>(Code("badKey"), ctx));
    }

    [Theory]
    [InlineData("1476.00", "purchase.standard")]
    [InlineData("4999.99", "purchase.standard")]
    [InlineData("5000", "purchase.high")]
    [InlineData("7380.00", "purchase.high")]
    public async Task The_label_follows_the_threshold_and_agrees_with_the_consumer(string total, string expected)
    {
        var ctx = new StubContext();
        ctx.Request.Body = new StubBody($"{{\"total\": {total}}}");
        var label = await Run<string>(Code("label"), ctx);
        Assert.Equal(expected, label);
        Assert.Equal(PurchaseRouting.LabelFor(decimal.Parse(total, System.Globalization.CultureInfo.InvariantCulture)), label);
    }

    [Fact]
    public async Task BrokerProperties_carries_message_id_label_and_correlation_id_as_json()
    {
        var ctx = new StubContext();
        ctx.Variables["idempotencyKey"] = "3f2504e0-4f89-11d3-9a0c-0305e82c3301";
        ctx.Variables["label"] = "purchase.high";
        var json = JObject.Parse(await Run<string>(Code("broker"), ctx));
        Assert.Equal("3f2504e0-4f89-11d3-9a0c-0305e82c3301", (string?)json["MessageId"]);
        Assert.Equal("purchase.high", (string?)json["Label"]);
        Assert.Equal("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", (string?)json["CorrelationId"]);
        Assert.Equal(3, json.Count);
    }

    [Fact]
    public async Task Only_201_from_service_bus_becomes_202_and_the_body_echoes_the_key()
    {
        var ctx = new StubContext();
        ctx.Variables["idempotencyKey"] = "3f2504e0-4f89-11d3-9a0c-0305e82c3301";

        ctx.Response.StatusCode = 201;
        Assert.True(await Run<bool>(Code("isCreated"), ctx));
        ctx.Response.StatusCode = 401;
        Assert.False(await Run<bool>(Code("isCreated"), ctx));

        var body = JObject.Parse(await Run<string>(Code("accepted"), ctx));
        Assert.Equal("accepted", (string?)body["status"]);
        Assert.Equal("3f2504e0-4f89-11d3-9a0c-0305e82c3301", (string?)body["id"]);
    }
}
