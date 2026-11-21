using System.Text.Json.Nodes;
using YamlDotNet.Serialization;

namespace EquipmentDesk.Canvas.Tests;

/// <summary>Reads the app's *.pa.yaml files (Power Apps source code format) and exposes controls and formulas.</summary>
public sealed class CanvasSource
{
    public static readonly string RepoDir = FindEpisodeDir();
    public static readonly string SrcDir = Path.Combine(RepoDir, "src", "app", "Src");

    public IReadOnlyDictionary<string, object?> Documents { get; }
    /// <summary>Every control in the app: name -> (screen, control type, properties).</summary>
    public IReadOnlyDictionary<string, ControlInfo> Controls { get; }
    public IReadOnlyList<string> DuplicateNames { get; }
    public IReadOnlyDictionary<string, string> AppProperties { get; }

    public sealed record ControlInfo(string Name, string Screen, string Type, IReadOnlyDictionary<string, string> Properties);

    public CanvasSource(string? srcDir = null)
    {
        var dir = srcDir ?? SrcDir;
        var deserializer = YamlReader();
        var docs = new Dictionary<string, object?>();
        var controls = new Dictionary<string, ControlInfo>();
        var dupes = new List<string>();
        var appProps = new Dictionary<string, string>();

        foreach (var file in Directory.GetFiles(dir, "*.pa.yaml").OrderBy(f => f))
        {
            var doc = deserializer.Deserialize<object?>(File.ReadAllText(file));
            docs[Path.GetFileName(file)] = doc;
            if (doc is not Dictionary<object, object?> root) continue;

            if (root.TryGetValue("App", out var app) && app is Dictionary<object, object?> appMap)
                foreach (var (k, v) in Props(appMap)) appProps[k] = v;

            if (root.TryGetValue("Screens", out var screens) && screens is Dictionary<object, object?> screenMap)
                foreach (var (screenName, screen) in screenMap)
                    if (screen is Dictionary<object, object?> s) Walk((string)screenName, s, controls, dupes);
        }
        Documents = docs;
        Controls = controls;
        DuplicateNames = dupes;
        AppProperties = appProps;
    }

    private static IEnumerable<(string, string)> Props(Dictionary<object, object?> node) =>
        node.TryGetValue("Properties", out var p) && p is Dictionary<object, object?> map
            ? map.Select(kv => ((string)kv.Key, kv.Value?.ToString() ?? ""))
            : [];

    private static void Walk(string screen, Dictionary<object, object?> node, Dictionary<string, ControlInfo> controls, List<string> dupes)
    {
        if (!node.TryGetValue("Children", out var children) || children is not List<object?> list) return;
        foreach (var item in list.OfType<Dictionary<object, object?>>())
            foreach (var (nameObj, valueObj) in item)
            {
                var name = (string)nameObj;
                var control = (Dictionary<object, object?>)valueObj!;
                var info = new ControlInfo(name, screen, control["Control"]?.ToString() ?? "", Props(control).ToDictionary(p => p.Item1, p => p.Item2));
                if (!controls.TryAdd(name, info)) dupes.Add(name);
                Walk(screen, control, controls, dupes);
            }
    }

    /// <summary>The formula of a control property without the leading '='.</summary>
    public string Formula(string control, string property)
    {
        var raw = Controls[control].Properties[property];
        return raw.StartsWith('=') ? raw[1..] : throw new InvalidOperationException($"{control}.{property} is not a formula");
    }

    /// <summary>App.Formulas split into named formulas: "MaxLoanDays = 90;" -> (MaxLoanDays, 90).</summary>
    public IReadOnlyList<(string Name, string Expression)> NamedFormulas() =>
        AppProperties.TryGetValue("Formulas", out var f)
            ? f.TrimStart('=').Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .Select(d => d.Split('=', 2)).Select(p => (p[0].Trim(), p[1].Trim())).ToList()
            : [];

    /// <summary>Unquoted true/false/numbers become typed values (the schema itself needs that); formulas stay strings.</summary>
    public static IDeserializer YamlReader() => new DeserializerBuilder().WithAttemptingUnquotedStringTypeDeserialization().Build();

    /// <summary>YAML object graph -> JsonNode, for JSON Schema validation.</summary>
    public static JsonNode? ToJson(object? yaml) => yaml switch
    {
        null => null,
        Dictionary<object, object?> map => new JsonObject(map.Select(kv => KeyValuePair.Create((string)kv.Key, ToJson(kv.Value)))),
        List<object?> list => new JsonArray(list.Select(ToJson).ToArray()),
        bool b => JsonValue.Create(b),
        int i => JsonValue.Create(i),
        long l => JsonValue.Create(l),
        double d => JsonValue.Create(d),
        decimal m => JsonValue.Create(m),
        IConvertible c when c.GetTypeCode() is >= TypeCode.SByte and <= TypeCode.Decimal => JsonValue.Create(Convert.ToDecimal(c)),
        _ => JsonValue.Create(yaml.ToString()),
    };

    private static string FindEpisodeDir()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null && !Directory.Exists(Path.Combine(dir.FullName, "src", "app", "Src"))) dir = dir.Parent;
        return dir?.FullName ?? throw new DirectoryNotFoundException("episode folder with src/app/Src not found");
    }
}
