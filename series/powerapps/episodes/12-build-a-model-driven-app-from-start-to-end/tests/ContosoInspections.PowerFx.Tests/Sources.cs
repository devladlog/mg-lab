using System.Text.Json;
using System.Text.Json.Nodes;
using YamlDotNet.Serialization;

namespace ContosoInspections.PowerFx.Tests;

/// <summary>Everything the tests read from the episode folder: the schema, commands.yaml, the custom page (*.pa.yaml) and the seed CSVs.</summary>
public static class Episode
{
    public static readonly string Dir = FindEpisodeDir();
    public static string Src(params string[] parts) => Path.Combine([Dir, "src", .. parts]);

    public static JsonNode Schema { get; } = JsonNode.Parse(File.ReadAllText(Src("schema", "contosoinspections.schema.json")))!;

    public static IDeserializer Yaml() => new DeserializerBuilder().WithAttemptingUnquotedStringTypeDeserialization().Build();

    public static List<Dictionary<string, string>> Csv(string file)
    {
        var lines = File.ReadAllLines(Src("data", file));
        var header = Split(lines[0]);
        return lines.Skip(1).Where(l => l.Length > 0).Select(l => Split(l).Select((v, i) => (header[i], v)).ToDictionary(p => p.Item1, p => p.v)).ToList();
    }

    private static string[] Split(string line) => line.Split(','); // the seed files contain no quoted commas (a test checks that)

    private static string FindEpisodeDir()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "src", "schema", "contosoinspections.schema.json"))) dir = dir.Parent;
        return dir?.FullName ?? throw new DirectoryNotFoundException("episode folder not found");
    }
}

public sealed record Command(string Id, string Label, string[] Locations, string Visible, string OnSelect);

public static class Commands
{
    public static IReadOnlyList<Command> Load()
    {
        var doc = Episode.Yaml().Deserialize<Dictionary<object, object?>>(File.ReadAllText(Episode.Src("logic", "commands.yaml")));
        return ((List<object?>)doc["commands"]!).Cast<Dictionary<object, object?>>().Select(c => new Command(
            (string)c["id"]!, (string)c["label"]!, ((List<object?>)c["locations"]!).Select(x => x!.ToString()!).ToArray(),
            c["visible"]!.ToString()!.Trim(), c["onSelect"]!.ToString()!.Trim())).ToList();
    }

    public static Command Get(string id) => Load().Single(c => c.Id == id);
}

/// <summary>Reads the custom page's *.pa.yaml files (Power Apps source code format) and exposes controls and named formulas.</summary>
public sealed class PageSource
{
    public static readonly string SrcDir = Episode.Src("custom-page", "Src");
    public IReadOnlyDictionary<string, object?> Documents { get; }
    public IReadOnlyDictionary<string, ControlInfo> Controls { get; }
    public IReadOnlyList<string> DuplicateNames { get; }
    public IReadOnlyDictionary<string, string> AppProperties { get; }

    public sealed record ControlInfo(string Name, string Screen, string Type, IReadOnlyDictionary<string, string> Properties);

    public PageSource()
    {
        var y = Episode.Yaml();
        var docs = new Dictionary<string, object?>();
        var controls = new Dictionary<string, ControlInfo>();
        var dupes = new List<string>();
        var app = new Dictionary<string, string>();
        foreach (var file in Directory.GetFiles(SrcDir, "*.pa.yaml").OrderBy(f => f))
        {
            var doc = y.Deserialize<object?>(File.ReadAllText(file));
            docs[Path.GetFileName(file)] = doc;
            if (doc is not Dictionary<object, object?> root) continue;
            if (root.TryGetValue("App", out var a) && a is Dictionary<object, object?> am) foreach (var (k, v) in Props(am)) app[k] = v;
            if (root.TryGetValue("Screens", out var s) && s is Dictionary<object, object?> sm)
                foreach (var (name, screen) in sm) if (screen is Dictionary<object, object?> sc) Walk((string)name, sc, controls, dupes);
        }
        Documents = docs; Controls = controls; DuplicateNames = dupes; AppProperties = app;
    }

    private static IEnumerable<(string, string)> Props(Dictionary<object, object?> node) =>
        node.TryGetValue("Properties", out var p) && p is Dictionary<object, object?> map ? map.Select(kv => ((string)kv.Key, kv.Value?.ToString() ?? "")) : [];

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

    public string Formula(string control, string property)
    {
        var raw = Controls[control].Properties[property];
        return raw.StartsWith('=') ? raw[1..].Trim() : throw new InvalidOperationException($"{control}.{property} is not a formula");
    }

    /// <summary>App.Formulas split into named formulas. ';' at the end of each definition; ';' inside strings would break this, and the test file checks there is none.</summary>
    public IReadOnlyList<(string Name, string Expression)> NamedFormulas() =>
        AppProperties["Formulas"].TrimStart('=').Split(";\n", StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(d => d.TrimEnd(';')).Select(d => d.Split('=', 2)).Select(p => (p[0].Trim(), p[1].Trim())).ToList();

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
}
