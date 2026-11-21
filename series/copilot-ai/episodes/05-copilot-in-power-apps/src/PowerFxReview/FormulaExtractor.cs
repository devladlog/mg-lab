using YamlDotNet.RepresentationModel;

namespace PowerFxReview;

public sealed record FormulaItem(string File, string Screen, string Control, string Property, string Formula)
{
    public string Where => string.Join(".", new[] { Screen, Control, Property }.Where(s => s.Length > 0));
    public bool IsBehavior => Property.StartsWith("On", StringComparison.Ordinal);
}

/// <summary>
/// Reads Power Fx formulas out of canvas app source (*.pa.yaml): every string that starts with "=" under a Properties map.
/// Also returns the screen names, because Navigate() takes them as arguments.
/// </summary>
public static class FormulaExtractor
{
    public static (List<FormulaItem> Formulas, List<string> Screens) FromFiles(IEnumerable<string> files)
    {
        var all = new List<FormulaItem>();
        var screens = new List<string>();
        foreach (var f in files)
        {
            var (items, s) = FromYaml(File.ReadAllText(f), Path.GetFileName(f));
            all.AddRange(items);
            screens.AddRange(s);
        }
        return (all, screens);
    }

    public static (List<FormulaItem> Formulas, List<string> Screens) FromYaml(string yaml, string file = "")
    {
        var stream = new YamlStream();
        stream.Load(new StringReader(yaml));
        var items = new List<FormulaItem>();
        var screens = new List<string>();
        if (stream.Documents.Count == 0 || stream.Documents[0].RootNode is not YamlMappingNode root)
            return (items, screens);

        foreach (var top in root.Children)
        {
            var key = ((YamlScalarNode)top.Key).Value;
            if (key == "App" && top.Value is YamlMappingNode app)
                Properties(app, file, "", "App", items);
            else if (key == "Screens" && top.Value is YamlMappingNode scr)
                foreach (var s in scr.Children)
                {
                    var name = ((YamlScalarNode)s.Key).Value!;
                    screens.Add(name);
                    Container((YamlMappingNode)s.Value, file, name, "", items);
                }
            else if (key == "ComponentDefinitions" && top.Value is YamlMappingNode comps)
                foreach (var c in comps.Children)
                    Container((YamlMappingNode)c.Value, file, ((YamlScalarNode)c.Key).Value!, "", items);
        }
        return (items, screens);
    }

    static void Container(YamlMappingNode node, string file, string screen, string control, List<FormulaItem> items)
    {
        Properties(node, file, screen, control, items);
        if (node.Children.TryGetValue("Children", out var kids) && kids is YamlSequenceNode seq)
            foreach (var entry in seq.Children.OfType<YamlMappingNode>())
                foreach (var c in entry.Children)
                    Container((YamlMappingNode)c.Value, file, screen, ((YamlScalarNode)c.Key).Value!, items);
    }

    static void Properties(YamlMappingNode node, string file, string screen, string control, List<FormulaItem> items)
    {
        if (!node.Children.TryGetValue("Properties", out var props) || props is not YamlMappingNode map) return;
        foreach (var p in map.Children)
            if (p.Value is YamlScalarNode v && v.Value is { } text && text.StartsWith('='))
            {
                items.Add(new FormulaItem(file, screen, control, ((YamlScalarNode)p.Key).Value!, text[1..].Trim()));
            }
    }
}
