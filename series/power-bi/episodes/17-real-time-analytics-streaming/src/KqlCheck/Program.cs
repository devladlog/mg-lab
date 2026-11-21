// KqlCheck: parse and analyze every .kql file with Microsoft's Kusto.Language (the same parser the Kusto tools use).
// Usage: KqlCheck <folder>. The table schema is read from the .create-merge table statement in 01-schema.kql.
// A statement is a block of consecutive non-empty lines. Exit code 1 if any statement has an error.
using System.Text.RegularExpressions;
using Kusto.Language;
using Kusto.Language.Symbols;

if (args.Length != 1 || !Directory.Exists(args[0]))
{
    Console.Error.WriteLine("usage: KqlCheck <folder with 01-schema.kql and queries/*.kql>");
    return 2;
}

var root = args[0];
var schemaFile = Path.Combine(root, "01-schema.kql");
var schemaText = File.ReadAllText(schemaFile);
var m = Regex.Match(schemaText, @"^\.create-merge table (\w+) \((.+)\)\s*$", RegexOptions.Multiline);
if (!m.Success)
{
    Console.Error.WriteLine("no .create-merge table statement found in 01-schema.kql");
    return 2;
}

var columns = m.Groups[2].Value;
var globals = GlobalState.Default.WithDatabase(new DatabaseSymbol("lab",
    new TableSymbol(m.Groups[1].Value, "(" + columns + ")"),
    new TableSymbol("TillEventsUnique", "(" + columns + ")")));

var files = new List<string> { schemaFile };
var queries = Path.Combine(root, "queries");
if (Directory.Exists(queries)) files.AddRange(Directory.GetFiles(queries, "*.kql").OrderBy(f => f, StringComparer.Ordinal));

var errors = 0;
var statements = 0;
foreach (var file in files)
{
    var block = new List<string>();
    var lines = File.ReadAllLines(file).Append("");
    foreach (var line in lines)
    {
        if (line.Trim().Length > 0) { block.Add(line); continue; }
        if (block.Count == 0) continue;
        var text = string.Join("\n", block);
        block.Clear();
        if (text.Split('\n').All(l => l.TrimStart().StartsWith("//"))) continue;   // comment-only block
        statements++;
        var code = KustoCode.ParseAndAnalyze(text, globals);
        var diags = code.GetDiagnostics().Where(d => d.Severity == "Error").ToList();
        if (diags.Count == 0)
        {
            Console.WriteLine($"ok    {Path.GetFileName(file)}: {text.Split('\n').First(l => !l.TrimStart().StartsWith("//")).Trim()[..Math.Min(70, text.Split('\n').First(l => !l.TrimStart().StartsWith("//")).Trim().Length)]}");
            continue;
        }
        foreach (var d in diags)
        {
            errors++;
            Console.WriteLine($"ERROR {Path.GetFileName(file)}: {d.Message}  [at {d.Start}]");
        }
    }
}

Console.WriteLine($"{statements} statements, {errors} errors");
return errors == 0 ? 0 : 1;
