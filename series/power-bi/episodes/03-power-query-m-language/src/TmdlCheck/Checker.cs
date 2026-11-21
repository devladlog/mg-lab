using Microsoft.AnalysisServices.Tabular;

namespace MGLab.TmdlCheck;

public sealed record Finding(string Severity, string Message);

/// <summary>
/// Loads the TMDL folder with the Tabular Object Model and checks that the Power Query side of the model
/// is what the queries folder says: every .pq file is either a shared expression or an M partition with
/// exactly the same text, parameters are parameters, functions aren't loaded, every table has one M partition.
/// </summary>
public static class Checker
{
    public static Model Load(string tmdlFolder) => TmdlSerializer.DeserializeDatabaseFromFolder(tmdlFolder).Model;

    public static IReadOnlyDictionary<string, string> ReadQueries(string queriesFolder) =>
        Directory.GetFiles(queriesFolder, "*.pq")
            .ToDictionary(f => Path.GetFileNameWithoutExtension(f), f => Normalize(File.ReadAllText(f)));

    public static string Normalize(string m) => m.Replace("\r\n", "\n").Trim('\n', ' ', '\t');

    public static List<Finding> Check(Model model, IReadOnlyDictionary<string, string> queries)
    {
        var findings = new List<Finding>();
        var inModel = new Dictionary<string, string>();

        foreach (var e in model.Expressions)
        {
            inModel[e.Name] = Normalize(e.Expression);
            bool isParameter = e.Expression.Contains("IsParameterQuery = true") || e.Expression.Contains("IsParameterQuery=true");
            bool isFunction = e.Expression.Contains("=>") && Normalize(StripComments(e.Expression)).StartsWith("(");
            string kind = isParameter ? "parameter" : isFunction ? "function" : "staging query (not loaded)";
            findings.Add(new("INFO", $"expression {e.Name}: {kind}"));
        }

        foreach (var t in model.Tables)
        {
            var parts = t.Partitions.ToList();
            if (parts.Count != 1 || parts[0].Source is not MPartitionSource m)
            {
                findings.Add(new("ERROR", $"table {t.Name}: expected exactly one M partition"));
                continue;
            }
            if (parts[0].Mode != ModeType.Import)
                findings.Add(new("ERROR", $"table {t.Name}: partition is {parts[0].Mode}, expected Import"));
            inModel[t.Name] = Normalize(m.Expression);
            findings.Add(new("INFO", $"table {t.Name}: M partition, {t.Columns.Count(c => c.Type == ColumnType.Data)} columns"));

            foreach (var c in t.Columns.OfType<DataColumn>())
                if (string.IsNullOrEmpty(c.SourceColumn))
                    findings.Add(new("ERROR", $"{t.Name}[{c.Name}]: data column without sourceColumn"));
        }

        foreach (var (name, text) in queries)
        {
            if (!inModel.TryGetValue(name, out var modelText))
                findings.Add(new("ERROR", $"{name}.pq is not in the model (run tools/sync_tmdl.py)"));
            else if (modelText != text)
                findings.Add(new("ERROR", $"{name}: the model's M differs from {name}.pq (run tools/sync_tmdl.py)"));
        }
        foreach (var name in inModel.Keys.Where(n => !queries.ContainsKey(n)))
            findings.Add(new("ERROR", $"{name} is in the model but has no .pq file"));

        return findings;
    }

    static string StripComments(string m) =>
        string.Join("\n", m.Replace("\r\n", "\n").Split('\n').Where(l => !l.TrimStart().StartsWith("//")));

    /// <summary>A TMDL createOrReplace script with every expression, table and relationship, for TMDL view.</summary>
    public static string CreateOrReplaceScript(Model model)
    {
        var parts = new List<string>();
        parts.AddRange(model.Expressions.Select(e => TmdlSerializer.SerializeObject(e, qualifyObject: false)));
        parts.AddRange(model.Tables.Select(t => TmdlSerializer.SerializeObject(t, qualifyObject: false)));
        parts.AddRange(model.Relationships.Select(r => TmdlSerializer.SerializeObject(r, qualifyObject: false)));
        var body = string.Join("\n", parts).Replace("\r\n", "\n").Split('\n')
            .Select(line => line.Length == 0 ? line : "\t" + line);
        return "createOrReplace\n\n" + string.Join("\n", body).TrimEnd() + "\n";
    }
}
