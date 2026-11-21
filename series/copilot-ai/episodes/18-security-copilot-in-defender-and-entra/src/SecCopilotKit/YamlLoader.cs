using System.Text.Json.Nodes;
using YamlDotNet.Serialization;

namespace Contoso.SecCopilotKit;

/// <summary>
/// Reads a Security Copilot manifest (YAML or JSON, Learn: "a YAML or JSON formatted manifest") into a JsonNode tree.
/// All YAML scalars stay strings; the checker compares them as text, so "true" and 300 need no special handling.
/// </summary>
public static class YamlLoader
{
    public static JsonNode Parse(string text)
    {
        var raw = new DeserializerBuilder().Build().Deserialize<object?>(text);
        return Convert(raw) ?? throw new FormatException("The manifest is empty.");
    }

    public static JsonNode Load(string path) => Parse(File.ReadAllText(path));

    private static JsonNode? Convert(object? value) => value switch
    {
        null => null,
        IDictionary<object, object> d => ToObject(d),
        IList<object> l => ToArray(l),
        _ => JsonValue.Create(System.Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture)),
    };

    private static JsonObject ToObject(IDictionary<object, object> d)
    {
        var o = new JsonObject();
        foreach (var kv in d) o[System.Convert.ToString(kv.Key)!] = Convert(kv.Value);
        return o;
    }

    private static JsonArray ToArray(IList<object> l)
    {
        var a = new JsonArray();
        foreach (var x in l) a.Add(Convert(x));
        return a;
    }
}
