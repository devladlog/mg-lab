using Microsoft.AnalysisServices.Tabular;

namespace MGLab.DaxLint;

public enum Severity { Info, Warning, Error }

public sealed record Finding(string Rule, Severity Severity, string Where, string Message);

public sealed record LintResult(int Measures, int Queries, IReadOnlyList<Finding> Findings, IReadOnlyList<string> PassedRules)
{
    public int Errors => Findings.Count(f => f.Severity == Severity.Error);
    public int Warnings => Findings.Count(f => f.Severity == Severity.Warning);
}

/// <summary>DAX hygiene rules for the measures of a TMDL semantic model and for saved DAX query view files.
/// Each rule maps to a Microsoft Learn DAX best practice (see README).</summary>
public static class Linter
{
    public static readonly IReadOnlyDictionary<string, string> Rules = new Dictionary<string, string>
    {
        ["DX001"] = "every measure has a format string",
        ["DX002"] = "every measure has a description and a display folder",
        ["DX003"] = "column references are fully qualified: 'Table'[Column]",
        ["DX004"] = "measure references are never qualified: [Measure]",
        ["DX005"] = "every reference resolves to a column or a measure",
        ["DX006"] = "DIVIDE instead of '/' when the denominator isn't a constant",
        ["DX007"] = "time intelligence uses the marked date table's date column",
        ["DX008"] = "USERELATIONSHIP names an existing inactive relationship",
        ["DX009"] = "saved DAX queries only reference existing objects",
    };

    static readonly string[] DatesFirstArg =
    {
        "SAMEPERIODLASTYEAR", "DATESYTD", "DATESQTD", "DATESMTD", "DATEADD", "DATESINPERIOD",
        "DATESBETWEEN", "PARALLELPERIOD", "PREVIOUSYEAR", "PREVIOUSQUARTER", "PREVIOUSMONTH", "PREVIOUSDAY",
        "NEXTYEAR", "NEXTQUARTER", "NEXTMONTH", "NEXTDAY",
    };
    static readonly string[] DatesSecondArg = { "TOTALYTD", "TOTALQTD", "TOTALMTD" };

    public static Model Load(string tmdlFolder) => TmdlSerializer.DeserializeDatabaseFromFolder(tmdlFolder).Model;

    public static LintResult Lint(Model model, string? queriesFolder = null)
    {
        var findings = new List<Finding>();
        var measures = model.Tables.SelectMany(t => t.Measures).ToList();
        var measureNames = measures.Select(m => m.Name).ToHashSet(StringComparer.OrdinalIgnoreCase);

        var dateTable = model.Tables.FirstOrDefault(t => string.Equals(t.DataCategory, "Time", StringComparison.OrdinalIgnoreCase));
        var dateKey = dateTable?.Columns.FirstOrDefault(c => c.IsKey);

        foreach (var m in measures)
        {
            string where = $"[{m.Name}]";
            if (string.IsNullOrWhiteSpace(m.FormatString) && m.FormatStringDefinition is null)
                findings.Add(new("DX001", Severity.Warning, where, "no format string"));
            if (string.IsNullOrWhiteSpace(m.Description) || string.IsNullOrWhiteSpace(m.DisplayFolder))
                findings.Add(new("DX002", Severity.Info, where, "missing description or display folder"));

            var text = DaxText.StripStringsAndComments(m.Expression);
            findings.AddRange(CheckReferences(model, measureNames, text, where, extraNames: null, rule5: "DX005"));

            if (DaxText.NonConstantDivisions(text).Any())
                findings.Add(new("DX006", Severity.Warning, where, "uses '/' with a non-constant denominator; use DIVIDE()"));

            foreach (var (fn, argIndex) in DatesFirstArg.Select(f => (f, 0)).Concat(DatesSecondArg.Select(f => (f, 1))))
                foreach (var args in DaxText.CallArguments(text, fn))
                {
                    if (args.Count <= argIndex) continue;
                    var r = DaxText.References(args[argIndex]).FirstOrDefault();
                    bool ok = r is not null && dateKey is not null &&
                              string.Equals(r.Table, dateTable!.Name, StringComparison.OrdinalIgnoreCase) &&
                              string.Equals(r.Name, dateKey.Name, StringComparison.OrdinalIgnoreCase);
                    if (!ok)
                        findings.Add(new("DX007", Severity.Error, where,
                            $"{fn} gets '{args[argIndex]}'; pass the marked date column '{dateTable?.Name ?? "Date"}'[{dateKey?.Name ?? "Date"}]"));
                }

            foreach (var args in DaxText.CallArguments(text, "USERELATIONSHIP"))
            {
                var cols = args.Select(a => DaxText.References(a).FirstOrDefault()).ToList();
                var rel = cols.Count == 2 && cols.All(c => c?.Table is not null) ? FindRelationship(model, cols[0]!, cols[1]!) : null;
                if (rel is null)
                    findings.Add(new("DX008", Severity.Error, where, $"USERELATIONSHIP({string.Join(", ", args)}) matches no relationship"));
                else if (rel.IsActive)
                    findings.Add(new("DX008", Severity.Warning, where, "USERELATIONSHIP on a relationship that is already active"));
            }
        }

        int queryCount = 0;
        if (queriesFolder is not null && Directory.Exists(queriesFolder))
        {
            foreach (var file in Directory.EnumerateFiles(queriesFolder, "*.dax").OrderBy(f => f))
            {
                queryCount++;
                var strings = new List<string>();
                var text = DaxText.StripStringsAndComments(File.ReadAllText(file), strings);
                // names the query itself defines: DEFINE MEASURE Table[Name] and "result column" names
                var defined = System.Text.RegularExpressions.Regex.Matches(text, @"MEASURE\s+(?:'[^']+'|\w+)\[(?<n>[^\]]+)\]",
                        System.Text.RegularExpressions.RegexOptions.IgnoreCase)
                    .Select(x => x.Groups["n"].Value).Concat(strings).ToHashSet(StringComparer.OrdinalIgnoreCase);
                var all = measureNames.Concat(defined).ToHashSet(StringComparer.OrdinalIgnoreCase);
                findings.AddRange(CheckReferences(model, all, text, Path.GetFileName(file), defined, rule5: "DX009")
                    .Where(f => f.Rule == "DX009"));
            }
        }

        var failed = findings.Where(f => f.Severity != Severity.Info).Select(f => f.Rule).ToHashSet();
        var ran = Rules.Keys.Where(k => k != "DX009" || queriesFolder is not null);
        return new LintResult(measures.Count, queryCount, findings, ran.Where(k => !failed.Contains(k) && !findings.Any(f => f.Rule == k)).ToList());
    }

    static IEnumerable<Finding> CheckReferences(Model model, ISet<string> measureNames, string text, string where,
                                                ISet<string>? extraNames, string rule5)
    {
        foreach (var r in DaxText.References(text))
        {
            if (r.Table is not null)
            {
                var table = model.Tables.Find(r.Table);
                if (table is not null && table.Columns.Contains(r.Name)) continue;
                if (measureNames.Contains(r.Name))
                {
                    // DEFINE MEASURE Sales[Name] = ... is how a query declares a measure: allowed there
                    if (extraNames is not null && extraNames.Contains(r.Name)) continue;
                    yield return new("DX004", Severity.Warning, where, $"{r.Table}[{r.Name}] qualifies a measure; write [{r.Name}]");
                    continue;
                }
                yield return new(rule5, Severity.Error, where, $"{r.Table}[{r.Name}] doesn't exist");
            }
            else
            {
                if (measureNames.Contains(r.Name)) continue;
                var owner = model.Tables.FirstOrDefault(t => t.Columns.Contains(r.Name));
                if (owner is not null)
                {
                    yield return new("DX003", Severity.Warning, where, $"[{r.Name}] is a column; write '{owner.Name}'[{r.Name}]");
                    continue;
                }
                yield return new(rule5, Severity.Error, where, $"[{r.Name}] doesn't exist");
            }
        }
    }

    static SingleColumnRelationship? FindRelationship(Model model, DaxRef a, DaxRef b) =>
        model.Relationships.OfType<SingleColumnRelationship>().FirstOrDefault(r =>
            (Same(r.FromColumn, a) && Same(r.ToColumn, b)) || (Same(r.FromColumn, b) && Same(r.ToColumn, a)));

    static bool Same(Column c, DaxRef r) =>
        string.Equals(c.Table.Name, r.Table, StringComparison.OrdinalIgnoreCase) &&
        string.Equals(c.Name, r.Name, StringComparison.OrdinalIgnoreCase);

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
