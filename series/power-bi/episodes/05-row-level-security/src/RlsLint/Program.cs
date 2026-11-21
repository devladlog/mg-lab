using MGLab.RlsLint;

// rls-lint <tmdl definition folder> [--sensitive Customer,Store] [--script <out.tmdl>]
// Exit code: 0 = no errors, 1 = errors found, 2 = bad arguments / unreadable model.
if (args.Length == 0 || args[0] is "-h" or "--help")
{
    Console.WriteLine("usage: rls-lint <definition folder> [--sensitive Table1,Table2] [--script <out.tmdl>]");
    return 2;
}

string folder = args[0];
var sensitive = (ArgValue("--sensitive") ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
string? script = ArgValue("--script");

Microsoft.AnalysisServices.Tabular.Model model;
try
{
    model = Linter.Load(folder);
}
catch (Exception ex)
{
    Console.Error.WriteLine($"cannot read TMDL in {folder}: {ex.Message}");
    return 2;
}

var result = Linter.Lint(model, sensitive);

Console.WriteLine($"RLS lint: {folder}");
foreach (var r in result.Roles)
{
    var filters = r.FilteredTables.Count == 0 ? "(none: every row)" : string.Join(", ", r.FilteredTables);
    var reached = r.ReachedTables.Count == 0 ? "-" : string.Join(", ", r.ReachedTables);
    Console.WriteLine($"  role {r.Role,-16} {(r.Dynamic ? "dynamic" : "static "),-8} filters: {filters}  ->  reaches: {reached}");
}
Console.WriteLine();
var failed = result.Findings.Select(f => f.Rule).ToHashSet();
foreach (var rule in Linter.Rules.Keys.Where(k => !failed.Contains(k)))
    Console.WriteLine($"  PASS    {rule}  {Linter.Rules[rule]}");
foreach (var f in result.Findings.OrderByDescending(f => f.Severity).ThenBy(f => f.Rule))
    Console.WriteLine($"  {f.Severity.ToString().ToUpperInvariant(),-7} {f.Rule}  {f.Message}");
Console.WriteLine();
Console.WriteLine($"{result.Errors} error(s), {result.Warnings} warning(s)");

if (script is not null)
{
    File.WriteAllText(script, Linter.CreateOrReplaceScript(model,
        tables: ["Store Access", "Sales"], expressions: ["UpnDomain"], relationships: ["Sales to Customer"]));
    Console.WriteLine($"TMDL view script written to {script}");
}

return result.Errors > 0 ? 1 : 0;

string? ArgValue(string name)
{
    int i = Array.IndexOf(args, name);
    return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
}
