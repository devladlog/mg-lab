using MGLab.TmdlCheck;

// tmdl-check <definition folder> <queries folder> [--script <file>]
if (args.Length < 2)
{
    Console.Error.WriteLine("usage: tmdl-check <definition folder> <queries folder> [--script <file>]");
    return 2;
}

var model = Checker.Load(args[0]);
var findings = Checker.Check(model, Checker.ReadQueries(args[1]));
foreach (var f in findings)
    Console.WriteLine($"  {f.Severity,-5}  {f.Message}");

int idx = Array.IndexOf(args, "--script");
if (idx >= 0 && idx + 1 < args.Length)
{
    File.WriteAllText(args[idx + 1], Checker.CreateOrReplaceScript(model));
    Console.WriteLine($"  wrote {args[idx + 1]}");
}

int errors = findings.Count(f => f.Severity == "ERROR");
Console.WriteLine($"{model.Tables.Count} table(s), {model.Expressions.Count} expression(s), {model.Relationships.Count} relationship(s): {errors} error(s)");
return errors == 0 ? 0 : 1;
