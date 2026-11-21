using MGLab.StarSchemaLinter;

// star-lint <tmdl definition folder> [--data <csv folder>] [--script <out.tmdl>]
// Exit code: 0 = no errors, 1 = errors found, 2 = bad arguments / unreadable model.
if (args.Length == 0 || args[0] is "-h" or "--help")
{
    Console.WriteLine("usage: star-lint <definition folder> [--data <csv folder>] [--script <out.tmdl>]");
    return 2;
}

string folder = args[0];
string? data = ArgValue("--data");
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

var result = Linter.Lint(model, data);

Console.WriteLine($"Star schema lint: {folder}");
Console.WriteLine($"  fact tables      : {string.Join(", ", result.FactTables)}");
Console.WriteLine($"  dimension tables : {string.Join(", ", result.DimensionTables)}");
Console.WriteLine($"  relationships    : {result.ActiveRelationships} active, {result.InactiveRelationships} inactive");
Console.WriteLine();
foreach (var rule in result.PassedRules)
    Console.WriteLine($"  PASS {rule}  {Linter.Rules[rule]}");
foreach (var f in result.Findings.OrderByDescending(f => f.Severity).ThenBy(f => f.Rule))
    Console.WriteLine($"  {f.Severity.ToString().ToUpperInvariant(),-7} {f.Rule}  {f.Message}");
Console.WriteLine();
Console.WriteLine($"{result.Errors} error(s), {result.Warnings} warning(s)");

if (script is not null)
{
    File.WriteAllText(script, Linter.CreateOrReplaceScript(model));
    Console.WriteLine($"TMDL view script written to {script}");
}

return result.Errors > 0 ? 1 : 0;

string? ArgValue(string name)
{
    int i = Array.IndexOf(args, name);
    return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
}
