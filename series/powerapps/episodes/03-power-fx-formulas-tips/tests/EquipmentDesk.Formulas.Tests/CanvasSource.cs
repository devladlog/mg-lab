using System.Text.Json.Nodes;
using YamlDotNet.Serialization;

namespace EquipmentDesk.Formulas.Tests;

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

    public enum DefinitionKind { NamedFormula, Function, BehaviorFunction }

    /// <summary>One definition from App.Formulas: "Holidays = [...]" or "IsWorkingDay(d: Date): Boolean = ...".</summary>
    public sealed record Definition(string Name, DefinitionKind Kind, string Text)
    {
        /// <summary>For a named formula, the expression after the first '='.</summary>
        public string Expression => Text[(Text.IndexOf('=') + 1)..].Trim();
    }

    /// <summary>App.Formulas split at top-level ';' (not inside (), [], {}, "text" or 'names').</summary>
    public IReadOnlyList<Definition> Definitions()
    {
        if (!AppProperties.TryGetValue("Formulas", out var raw)) return [];
        var text = raw.StartsWith('=') ? raw[1..] : raw;
        var parts = new List<string>();
        // A small scanner: code, "text", 'name', and $"interpolated {code} text" (holes can nest strings and records).
        // Each stack entry is a mode ('"' text, '\'' name, '$' interpolated text, 'c' code in a hole) and the bracket
        // depth at which it started, so the '}' that closes a hole isn't confused with the end of a record.
        var modes = new Stack<(char Mode, int Depth)>();
        int depth = 0, start = 0;
        for (var i = 0; i < text.Length; i++)
        {
            var c = text[i];
            var mode = modes.Count == 0 ? 'c' : modes.Peek().Mode;
            if (mode is '"' or '\'') { if (c == mode) modes.Pop(); continue; }
            if (mode == '$')
            {
                if (c == '"') modes.Pop();
                else if (c == '{') modes.Push(('c', depth));
                continue;
            }
            switch (c)
            {
                case '$' when i + 1 < text.Length && text[i + 1] == '"': modes.Push(('$', depth)); i++; break;
                case '"' or '\'': modes.Push((c, depth)); break;
                case '}' when modes.Count > 0 && modes.Peek().Mode == 'c' && modes.Peek().Depth == depth: modes.Pop(); break;
                case '(' or '[' or '{': depth++; break;
                case ')' or ']' or '}': depth--; break;
                case ';' when depth == 0 && modes.Count == 0: parts.Add(text[start..i]); start = i + 1; break;
            }
        }
        if (depth != 0 || modes.Count != 0) throw new FormatException("App.Formulas has unbalanced brackets or quotes");
        if (text[start..].Trim().Length > 0) parts.Add(text[start..]);

        return parts.Select(p => p.Trim()).Where(p => p.Length > 0).Select(p =>
        {
            var m = System.Text.RegularExpressions.Regex.Match(p, @"^([A-Za-z_][A-Za-z0-9_]*)\s*(\()?");
            var name = m.Groups[1].Value;
            var kind = !m.Groups[2].Success ? DefinitionKind.NamedFormula
                : System.Text.RegularExpressions.Regex.IsMatch(p, @"=\s*\{") ? DefinitionKind.BehaviorFunction
                : DefinitionKind.Function;
            return new Definition(name, kind, p);
        }).ToList();
    }

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
