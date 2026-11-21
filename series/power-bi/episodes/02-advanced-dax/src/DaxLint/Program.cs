using MGLab.DaxLint;

// dax-lint <tmdl definition folder> [--queries <DAXQueries folder>] [--script <out.tmdl>]
// Exit code: 0 = no errors, 1 = errors found, 2 = bad arguments / unreadable model.
if (args.Length == 0 || args[0] is "-h" or "--help")
{
    Console.WriteLine("usage: dax-lint <definition folder> [--queries <DAXQueries folder>] [--script <out.tmdl>]");
    return 2;
}

string folder = args[0];
int qi = Array.IndexOf(args, "--queries");
string? queries = qi >= 0 && qi + 1 < args.Length ? args[qi + 1] : null;
int si = Array.IndexOf(args, "--script");
string? script = si >= 0 && si + 1 < args.Length ? args[si + 1] : null;

Microsoft.AnalysisServices.Tabular.Model model;
try { model = Linter.Load(folder); }
catch (Exception ex)
{
    Console.Error.WriteLine($"cannot read TMDL in {folder}: {ex.Message}");
    return 2;
}

var result = Linter.Lint(model, queries);
Console.WriteLine($"DAX lint: {result.Measures} measures, {result.Queries} saved queries");
Console.WriteLine();
foreach (var rule in result.PassedRules)
    Console.WriteLine($"  PASS    {rule}  {Linter.Rules[rule]}");
foreach (var f in result.Findings.OrderByDescending(f => f.Severity).ThenBy(f => f.Rule))
    Console.WriteLine($"  {f.Severity.ToString().ToUpperInvariant(),-7} {f.Rule}  {f.Where}: {f.Message}");
Console.WriteLine();
Console.WriteLine($"{result.Errors} error(s), {result.Warnings} warning(s)");
if (script is not null)
{
    File.WriteAllText(script, Linter.CreateOrReplaceScript(model));
    Console.WriteLine($"TMDL view script written to {script}");
}
return result.Errors > 0 ? 1 : 0;
