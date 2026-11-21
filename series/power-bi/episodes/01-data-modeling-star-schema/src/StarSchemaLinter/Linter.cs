using System.Text.RegularExpressions;
using Microsoft.AnalysisServices.Tabular;

namespace MGLab.StarSchemaLinter;

public enum Severity { Info, Warning, Error }

public sealed record Finding(string Rule, Severity Severity, string Message);

public sealed record LintResult(
    IReadOnlyList<string> FactTables,
    IReadOnlyList<string> DimensionTables,
    int ActiveRelationships,
    int InactiveRelationships,
    IReadOnlyList<Finding> Findings,
    IReadOnlyList<string> PassedRules)
{
    public int Errors => Findings.Count(f => f.Severity == Severity.Error);
    public int Warnings => Findings.Count(f => f.Severity == Severity.Warning);
}

/// <summary>
/// Star schema rules for a Power BI semantic model, read from a TMDL folder with the
/// Tabular Object Model. Each rule maps to Microsoft's star schema / relationship guidance.
/// </summary>
public static class Linter
{
    public static readonly IReadOnlyDictionary<string, string> Rules = new Dictionary<string, string>
    {
        ["SS001"] = "every relationship is many-to-one (fact to dimension)",
        ["SS002"] = "relationships filter in a single direction",
        ["SS003"] = "no snowflake chains (a dimension never filters through another dimension)",
        ["SS004"] = "foreign keys on the many side are hidden",
        ["SS005"] = "key columns don't summarize (summarizeBy: none)",
        ["SS006"] = "a marked date table exists (dataCategory Time + date key column)",
        ["SS007"] = "every measure has a format string",
        ["SS008"] = "implicit measures are discouraged at model level",
        ["SS009"] = "every sourceColumn exists in the CSV the partition reads",
    };

    public static Model Load(string tmdlFolder) =>
        TmdlSerializer.DeserializeDatabaseFromFolder(tmdlFolder).Model;

    public static LintResult Lint(Model model, string? dataFolder = null)
    {
        var findings = new List<Finding>();
        var rels = model.Relationships.OfType<SingleColumnRelationship>().ToList();

        // A table's role comes from relationships: the "one" side is a dimension, the "many" side a fact.
        var manySide = rels.Select(r => r.FromTable.Name).ToHashSet();
        var oneSide = rels.Select(r => r.ToTable.Name).ToHashSet();

        foreach (var r in rels)
        {
            var name = $"{r.FromTable.Name}[{r.FromColumn.Name}] -> {r.ToTable.Name}[{r.ToColumn.Name}]";

            if (!(r.FromCardinality == RelationshipEndCardinality.Many && r.ToCardinality == RelationshipEndCardinality.One))
                findings.Add(new("SS001", Severity.Error,
                    $"{name} is {r.FromCardinality}-to-{r.ToCardinality}; use many-to-one from the fact to the dimension"));

            if (r.CrossFilteringBehavior == CrossFilteringBehavior.BothDirections)
                findings.Add(new("SS002", Severity.Warning,
                    $"{name} filters in both directions; prefer single direction and CROSSFILTER in a measure when needed"));

            if (!r.FromColumn.IsHidden)
                findings.Add(new("SS004", Severity.Warning, $"{r.FromTable.Name}[{r.FromColumn.Name}] is a foreign key and should be hidden"));

            foreach (var c in new[] { r.FromColumn, r.ToColumn })
                if (IsNumeric(c.DataType) && c.SummarizeBy != AggregateFunction.None)
                    findings.Add(new("SS005", Severity.Warning, $"{c.Table.Name}[{c.Name}] is a key; set summarizeBy: none"));
        }

        foreach (var r in rels.Where(r => r.IsActive && oneSide.Contains(r.FromTable.Name)))
            findings.Add(new("SS003", Severity.Warning,
                $"snowflake: dimension {r.FromTable.Name} filters through {r.ToTable.Name}; flatten {r.ToTable.Name} into {r.FromTable.Name}"));

        var dateTables = model.Tables.Where(t =>
            string.Equals(t.DataCategory, "Time", StringComparison.OrdinalIgnoreCase) &&
            t.Columns.Any(c => c.IsKey && c.DataType == DataType.DateTime)).ToList();
        if (dateTables.Count == 0)
            findings.Add(new("SS006", Severity.Error,
                "no marked date table: set dataCategory: Time on the date table and isKey on its date column"));

        foreach (var m in model.Tables.SelectMany(t => t.Measures))
            if (string.IsNullOrWhiteSpace(m.FormatString) && m.FormatStringDefinition is null)
                findings.Add(new("SS007", Severity.Warning, $"measure [{m.Name}] has no format string"));

        if (!model.DiscourageImplicitMeasures)
            findings.Add(new("SS008", Severity.Info, "discourageImplicitMeasures is off: report authors can drag raw columns as implicit measures"));

        if (dataFolder is not null)
            findings.AddRange(CheckSourceColumns(model, dataFolder));

        var failed = findings.Select(f => f.Rule).ToHashSet();
        var ran = Rules.Keys.Where(k => k != "SS009" || dataFolder is not null);
        var passed = ran.Where(k => !failed.Contains(k)).ToList();

        var facts = model.Tables.Where(t => manySide.Contains(t.Name) && !oneSide.Contains(t.Name)).Select(t => t.Name).OrderBy(n => n).ToList();
        var dims = model.Tables.Where(t => oneSide.Contains(t.Name)).Select(t => t.Name).OrderBy(n => n).ToList();

        return new LintResult(facts, dims, rels.Count(r => r.IsActive), rels.Count(r => !r.IsActive), findings, passed);
    }

    static readonly Regex CsvFile = new(@"""(?<file>[^""]+\.csv)""", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    /// <summary>Compares each table's sourceColumn values with the header row of the CSV its M partition reads.</summary>
    public static IEnumerable<Finding> CheckSourceColumns(Model model, string dataFolder)
    {
        foreach (var t in model.Tables)
        {
            var m = t.Partitions.Select(p => p.Source).OfType<MPartitionSource>().FirstOrDefault();
            if (m is null) continue;
            var match = CsvFile.Match(m.Expression);
            if (!match.Success) continue;

            // The M path may be a full Windows path or DataFolder & "file.csv": keep only the file name.
            var file = match.Groups["file"].Value.Split('\\', '/').Last();
            var path = Path.Combine(dataFolder, file);
            if (!File.Exists(path))
            {
                yield return new("SS009", Severity.Error, $"table {t.Name} reads {file}, which isn't in {dataFolder}");
                continue;
            }
            var header = File.ReadLines(path).First().Split(',').Select(h => h.Trim('"')).ToHashSet();
            foreach (var c in t.Columns.OfType<DataColumn>())
                if (!header.Contains(c.SourceColumn))
                    yield return new("SS009", Severity.Error,
                        $"{t.Name}[{c.Name}] has sourceColumn '{c.SourceColumn}', not found in {file}");
        }
    }

    /// <summary>A TMDL createOrReplace script with every table, relationship and expression, for TMDL view.</summary>
    public static string CreateOrReplaceScript(Model model)
    {
        var parts = new List<string>();
        parts.AddRange(model.Expressions.Select(e => TmdlSerializer.SerializeObject(e, qualifyObject: false)));
        parts.AddRange(model.Tables.Select(t => TmdlSerializer.SerializeObject(t, qualifyObject: false)));
        parts.AddRange(model.Relationships.Select(r => TmdlSerializer.SerializeObject(r, qualifyObject: false)));

        var body = string.Join("\n", parts)
            .Replace("\r\n", "\n")
            .Split('\n')
            .Select(line => line.Length == 0 ? line : "\t" + line);
        return "createOrReplace\n\n" + string.Join("\n", body).TrimEnd() + "\n";
    }

    static bool IsNumeric(DataType t) => t is DataType.Int64 or DataType.Double or DataType.Decimal;
}
