// composite-lint <SemanticModel/definition folder> [--explain]
// Loads a TMDL folder with the Tabular Object Model and checks a composite model against what Microsoft Learn documents about
// storage modes, regular/limited relationships and user-defined aggregations (rules CM001-CM006). Nothing is evaluated: the
// engine, the service and SQL Server are the final judges (the recording shows them).
// --explain adds a prediction, from the same Learn rules, of which measures and which dimension attributes an aggregation can answer.
using System.Text.RegularExpressions;
using Microsoft.AnalysisServices.Tabular;

var folder = args.FirstOrDefault(a => !a.StartsWith("--"));
if (folder is null || !Directory.Exists(folder))
{
    Console.Error.WriteLine("usage: composite-lint <SemanticModel/definition folder> [--explain]");
    return 2;
}

Model model;
try
{
    model = TmdlSerializer.DeserializeDatabaseFromFolder(folder).Model;
}
catch (Exception e)
{
    Console.WriteLine($"  ERROR   TMDL   {e.GetType().Name}: {e.Message}");
    return 1;
}

var findings = new List<(string Rule, string Severity, string Message)>();
void Add(string rule, string severity, string message) => findings.Add((rule, severity, message));

// ---- storage mode and source of every table -------------------------------------------------
string ModeOf(Table t)
{
    var modes = t.Partitions.Select(p => p.Mode == ModeType.Default ? "Import" : p.Mode.ToString()).Distinct().ToList();
    return modes.Count == 1 ? modes[0] : "Hybrid";
}

string? ParamValue(string name)
{
    var e = model.Expressions.FirstOrDefault(x => x.Name == name);
    if (e is null) return null;
    var m = Regex.Match(e.Expression, "^\\s*\"([^\"]*)\"");
    return m.Success ? m.Groups[1].Value : null;
}

string SourceOf(Table t)
{
    // "server|database" of the first Sql.Database(...) in the partition, parameters resolved; Import tables are one group
    if (ModeOf(t) == "Import") return "import";
    var src = t.Partitions.Select(p => (p.Source as MPartitionSource)?.Expression).FirstOrDefault(x => x is not null) ?? "";
    var m = Regex.Match(src, @"Sql\.Database\(\s*([^,\)]+?)\s*,\s*([^,\)]+?)\s*[,\)]");
    if (!m.Success) return "unknown:" + t.Name;
    string Arg(string a) => a.StartsWith('"') ? a.Trim('"') : (ParamValue(a) ?? a);
    return (Arg(m.Groups[1].Value) + "|" + Arg(m.Groups[2].Value)).ToLowerInvariant();
}

var mode = model.Tables.ToDictionary(t => t.Name, ModeOf);
var source = model.Tables.ToDictionary(t => t.Name, SourceOf);

// Learn (Aggregations, "Regular vs. limited relationships"): regular when many/one are Dual/Dual, Import/Import, Import/Dual, DirectQuery/DirectQuery
// or DirectQuery/Dual, from a single source. Many-to-many is always limited.
bool IsRegular(SingleColumnRelationship r)
{
    var manyEnd = r.FromCardinality == RelationshipEndCardinality.Many ? r.FromColumn.Table : r.ToColumn.Table;
    var oneEnd = manyEnd == r.FromColumn.Table ? r.ToColumn.Table : r.FromColumn.Table;
    if (r.FromCardinality == RelationshipEndCardinality.Many && r.ToCardinality == RelationshipEndCardinality.Many) return false;
    string mm = mode[manyEnd.Name], om = mode[oneEnd.Name];
    return (mm, om) switch
    {
        ("Import", "Import") => true,
        ("Import", "Dual") => true,                      // a Dual table acts as Import here
        ("Dual", "Dual") or ("DirectQuery", "DirectQuery") or ("DirectQuery", "Dual") => source[manyEnd.Name] == source[oneEnd.Name],
        _ => false,
    };
}

var rels = model.Relationships.OfType<SingleColumnRelationship>().ToList();

Console.WriteLine("storage modes");
foreach (var t in model.Tables)
{
    var agg = t.Columns.Any(c => c.AlternateOf is not null) ? "  (aggregation)" : "";
    var src = mode[t.Name] == "Import" ? "" : $"  source {source[t.Name]}";
    Console.WriteLine($"  {t.Name,-12} {mode[t.Name],-12}{(t.IsHidden ? " hidden" : "       ")}{src}{agg}");
}
Console.WriteLine("relationships");
foreach (var r in rels)
{
    var kind = IsRegular(r) ? "regular" : "limited";
    Console.WriteLine($"  {r.FromColumn.Table.Name}[{r.FromColumn.Name}] -> {r.ToColumn.Table.Name}[{r.ToColumn.Name}]  {kind}");
}

// ---- CM001 limited relationships --------------------------------------------------------------
foreach (var r in rels.Where(r => !IsRegular(r)))
{
    var many = r.FromCardinality == RelationshipEndCardinality.Many ? r.FromColumn.Table : r.ToColumn.Table;
    var one = many == r.FromColumn.Table ? r.ToColumn.Table : r.FromColumn.Table;
    string why;
    if (r.FromCardinality == RelationshipEndCardinality.Many && r.ToCardinality == RelationshipEndCardinality.Many) why = "many-to-many is always limited";
    else if (mode[many.Name] == "DirectQuery" && mode[one.Name] == "Import") why = $"{one.Name} is Import and {many.Name} is DirectQuery: set {one.Name} to Dual";
    else if (source[many.Name] != source[one.Name]) why = "the tables come from different source groups";
    else why = $"{mode[many.Name]} (many side) to {mode[one.Name]} (one side) is not a regular combination";
    Add("CM001", "warning", $"{r.FromColumn.Table.Name}[{r.FromColumn.Name}] -> {r.ToColumn.Table.Name}[{r.ToColumn.Name}] is a limited relationship: {why}");
}

// ---- aggregations ---------------------------------------------------------------------------------
var aggTables = model.Tables.Where(t => t.Columns.Any(c => c.AlternateOf is not null)).ToList();
foreach (var a in aggTables)
{
    // CM003 aggregation tables are hidden (the Manage aggregations dialog hides them)
    if (!a.IsHidden) Add("CM003", "warning", $"aggregation table {a.Name} is not hidden: reports and queries should only see the detail table");

    var seen = new HashSet<string>();
    foreach (var c in a.Columns.Where(c => c.AlternateOf is not null))
    {
        var alt = c.AlternateOf;
        var detail = alt.BaseColumn?.Table ?? alt.BaseTable;
        var label = $"{a.Name}[{c.Name}]";
        if (detail is null) { Add("CM002", "error", $"{label}: alternateOf has neither baseColumn nor baseTable"); continue; }
        if (mode[detail.Name] != "DirectQuery")
            Add("CM002", "error", $"{label}: the detail table {detail.Name} is {mode[detail.Name]}, it must be DirectQuery");
        if (detail.Columns.Any(x => x.AlternateOf is not null))
            Add("CM002", "error", $"{label}: chained aggregation, {detail.Name} has aggregations of its own");
        if (alt.BaseTable is not null && alt.Summarization != SummarizationType.Count)
            Add("CM002", "error", $"{label}: a baseTable mapping is 'Count table rows', its summarization must be count");
        if (alt.BaseColumn is not null && alt.Summarization != SummarizationType.Count && alt.BaseColumn.DataType != c.DataType)
            Add("CM002", "error", $"{label}: data type {c.DataType} differs from {detail.Name}[{alt.BaseColumn.Name}] ({alt.BaseColumn.DataType}); only Count may differ");
        if (alt.Summarization == SummarizationType.Count && c.DataType != DataType.Int64)
            Add("CM002", "error", $"{label}: Count and Count table rows need an integer aggregation column");
        var key = $"{alt.Summarization}|{detail.Name}|{alt.BaseColumn?.Name}";
        if (!seen.Add(key)) Add("CM002", "error", $"{label}: duplicate aggregation, {alt.Summarization} of {detail.Name}[{alt.BaseColumn?.Name}] is mapped twice");
    }

    // CM004 relationship based hits need regular relationships, from the aggregation and from the detail table
    var details = a.Columns.Where(c => c.AlternateOf is not null)
        .Select(c => c.AlternateOf.BaseColumn?.Table ?? c.AlternateOf.BaseTable).Where(t => t is not null).Distinct().ToList();
    foreach (var r in rels.Where(r => r.FromColumn.Table == a || r.ToColumn.Table == a))
    {
        var other = r.FromColumn.Table == a ? r.ToColumn.Table : r.FromColumn.Table;
        if (!IsRegular(r))
            Add("CM004", "error", $"{a.Name} -> {other.Name} is limited: aggregation hits through this relationship won't work");
        foreach (var d in details)
        {
            var dRel = rels.Where(x => (x.FromColumn.Table == d && x.ToColumn.Table == other) || (x.ToColumn.Table == d && x.FromColumn.Table == other)).ToList();
            if (dRel.Count == 0)
                Add("CM004", "warning", $"{other.Name} filters {a.Name} but not {d.Name}: a query by {other.Name} attributes can't be answered the same way from both");
        }
    }
}

// ---- CM005 calculated columns on DirectQuery / Dual tables ---------------------------------------------
foreach (var t in model.Tables.Where(t => mode[t.Name] is "DirectQuery" or "Dual"))
    foreach (var c in t.Columns.OfType<CalculatedColumn>())
    {
        var others = model.Tables.Where(o => o != t).Any(o => Regex.IsMatch(c.Expression, $@"(^|[^\w]){Regex.Escape(o.Name)}\[|'{Regex.Escape(o.Name)}'\["));
        if (others || Regex.IsMatch(c.Expression, @"RELATED(TABLE)?\s*\(", RegexOptions.IgnoreCase))
            Add("CM005", "warning", $"calculated column {t.Name}[{c.Name}] on a {mode[t.Name]} table refers to another table: it can only refer to columns of its own table");
    }

// ---- measures: what an aggregation can answer (CM006 info, --explain) -------------------------------------
var measures = model.Tables.SelectMany(t => t.Measures.Select(m => (Table: t, Measure: m))).ToDictionary(x => x.Measure.Name, x => x);

string Explain(Measure m, HashSet<string> visiting)
{
    // returns "HIT" / "MISS: reason" for the whole expression, from the same rules as Learn's examples
    var expr = m.Expression;
    var reasons = new List<string>();
    foreach (Match f in Regex.Matches(expr, @"\b(SUMX|AVERAGEX|MINX|MAXX|COUNTX|PRODUCTX)\s*\(", RegexOptions.IgnoreCase))
        reasons.Add($"{f.Groups[1].Value.ToUpperInvariant()} is an iterator: Learn lists SUM, MIN, MAX, COUNT, COUNTROWS, AVERAGE and DISTINCTCOUNT as aggregation aware, iterators are not mentioned (test it)");
    foreach (Match f in Regex.Matches(expr, @"\bSUM\(\s*'?(\w[\w ]*?)'?\[([^\]]+)\]\s*\)", RegexOptions.IgnoreCase))
        reasons.AddRange(Need(f.Groups[1].Value, f.Groups[2].Value, SummarizationType.Sum, "SUM"));
    foreach (Match f in Regex.Matches(expr, @"\bMIN\(\s*'?(\w[\w ]*?)'?\[([^\]]+)\]\s*\)", RegexOptions.IgnoreCase))
        reasons.AddRange(Need(f.Groups[1].Value, f.Groups[2].Value, SummarizationType.Min, "MIN"));
    foreach (Match f in Regex.Matches(expr, @"\bMAX\(\s*'?(\w[\w ]*?)'?\[([^\]]+)\]\s*\)", RegexOptions.IgnoreCase))
        reasons.AddRange(Need(f.Groups[1].Value, f.Groups[2].Value, SummarizationType.Max, "MAX"));
    foreach (Match f in Regex.Matches(expr, @"\bCOUNTROWS\(\s*'?(\w[\w ]*?)'?\s*\)", RegexOptions.IgnoreCase))
    {
        var t = model.Tables.Find(f.Groups[1].Value);
        if (t is not null && !aggTables.Any(a => a.Columns.Any(c => c.AlternateOf?.Summarization == SummarizationType.Count && c.AlternateOf.BaseTable == t)))
            reasons.Add($"COUNTROWS({t.Name}) needs a 'Count table rows' mapping (baseTable: {t.Name})");
    }
    foreach (Match f in Regex.Matches(expr, @"\bDISTINCTCOUNT\(\s*'?(\w[\w ]*?)'?\[([^\]]+)\]\s*\)", RegexOptions.IgnoreCase))
    {
        var t = model.Tables.Find(f.Groups[1].Value);
        var col = t?.Columns.Find(f.Groups[2].Value);
        var grouped = col is not null && aggTables.Any(a => a.Columns.Any(c => c.AlternateOf?.BaseColumn == col && c.AlternateOf.Summarization == SummarizationType.GroupBy));
        if (!grouped) reasons.Add($"DISTINCTCOUNT({f.Groups[1].Value}[{f.Groups[2].Value}]) needs a GroupBy mapping of that column");
    }
    foreach (Match f in Regex.Matches(expr, @"(?<![\w'\]])\[([^\]]+)\]"))
        if (measures.TryGetValue(f.Groups[1].Value, out var inner) && visiting.Add(inner.Measure.Name))
        {
            var r = Explain(inner.Measure, visiting);
            if (r != "HIT") reasons.Add($"[{inner.Measure.Name}]: {r.Replace("MISS: ", "")}");
        }
    return reasons.Count == 0 ? "HIT" : "MISS: " + string.Join("; ", reasons.Distinct());

    IEnumerable<string> Need(string table, string column, SummarizationType s, string fn)
    {
        var t = model.Tables.Find(table);
        var col = t?.Columns.Find(column);
        if (col is null) return Array.Empty<string>();
        var ok = aggTables.Any(a => a.Columns.Any(c => c.AlternateOf?.BaseColumn == col && c.AlternateOf.Summarization == s));
        return ok ? Array.Empty<string>() : new[] { $"{fn}({table}[{column}]) has no {s} mapping" };
    }
}

if (aggTables.Count > 0)
    foreach (var (t, m) in measures.Values.Where(x => aggTables.Count > 0 && mode[x.Table.Name] == "DirectQuery"))
    {
        var r = Explain(m, new HashSet<string> { m.Name });
        if (r.StartsWith("MISS") && r.Contains("iterator")) Add("CM006", "info", $"measure [{m.Name}]: {r.Replace("MISS: ", "")}");
    }

findings = findings.OrderBy(f => f.Rule).ToList();
foreach (var f in findings)
    Console.WriteLine($"  {f.Severity.ToUpperInvariant(),-7} {f.Rule}  {f.Message}");
var errors = findings.Count(f => f.Severity == "error");
var warnings = findings.Count(f => f.Severity == "warning");

if (args.Contains("--explain") && aggTables.Count > 0)
{
    Console.WriteLine("prediction (Learn's rules, not the engine)");
    foreach (var (t, m) in measures.Values.Where(x => mode[x.Table.Name] == "DirectQuery"))
        Console.WriteLine($"  measure [{m.Name}]  {Explain(m, new HashSet<string> { m.Name })}");
    foreach (var a in aggTables)
    {
        var detail = a.Columns.Where(c => c.AlternateOf is not null).Select(c => c.AlternateOf.BaseColumn?.Table ?? c.AlternateOf.BaseTable).First()!;
        var dims = rels.SelectMany(r => new[] { r.FromColumn.Table, r.ToColumn.Table }).Distinct()
            .Where(d => d != a && d != detail && rels.Any(r => (r.FromColumn.Table == detail || r.ToColumn.Table == detail) && (r.FromColumn.Table == d || r.ToColumn.Table == d)));
        foreach (var d in dims)
        {
            var viaRel = rels.Any(r => (r.FromColumn.Table == a && r.ToColumn.Table == d || r.ToColumn.Table == a && r.FromColumn.Table == d) && IsRegular(r));
            Console.WriteLine($"  group by {d.Name}[...]  {(viaRel ? "HIT (regular relationship from " + a.Name + ")" : "MISS (no regular relationship from " + a.Name + "): goes to the source")}");
        }
    }
}

Console.WriteLine($"{model.Tables.Count} table(s), {rels.Count} relationship(s), {aggTables.Count} aggregation table(s): {errors} error(s), {warnings} warning(s)");
return errors > 0 ? 1 : 0;
