using System.Text.Json;
using PowerFxReview;

return await Cli.RunAsync(args, Console.Out, Console.Error);

public static class Cli
{
    const string Usage = """
        PowerFxReview: review the Power Fx that Copilot wrote, with the real Power Fx engine.

          review <file.pa.yaml | folder> --context context.json [--json]
              Reads every formula under Properties, checks it, applies the extra rules.
              Exit code 1 when at least one formula has an error.
          check "<formula>" --context context.json [--property Text] [--json]
              The same for one formula you pasted from the formula bar.
          run "<formula>" --context context.json --data sample-data.json
              Evaluates the formula on sample rows and prints the result.
        """;

    public static async Task<int> RunAsync(string[] args, TextWriter @out, TextWriter err)
    {
        if (args.Length == 0 || args[0] is "-h" or "--help") { @out.WriteLine(Usage); return args.Length == 0 ? 2 : 0; }
        try
        {
            var opts = Options.Parse(args.Skip(1).ToArray());
            var ctxPath = opts.Get("--context") ?? throw new ArgumentException("--context is required");
            var ctx = ReviewContext.Load(ctxPath);
            switch (args[0])
            {
                case "review":
                {
                    var path = opts.Positional ?? throw new ArgumentException("review needs a file or folder");
                    var files = Directory.Exists(path)
                        ? Directory.EnumerateFiles(path, "*.pa.yaml", SearchOption.AllDirectories).OrderBy(f => f, StringComparer.Ordinal).ToList()
                        : new List<string> { path };
                    if (files.Count == 0) throw new ArgumentException($"No *.pa.yaml files in {path}");
                    var (formulas, screens) = FormulaExtractor.FromFiles(files);
                    return Report(new Reviewer(ctx, screens), formulas, opts.Has("--json"), @out);
                }
                case "check":
                {
                    var f = opts.Positional ?? throw new ArgumentException("check needs a formula");
                    var item = new FormulaItem("(pasted)", "", "", opts.Get("--property") ?? "Text", f);
                    return Report(new Reviewer(ctx, Array.Empty<string>()), new List<FormulaItem> { item }, opts.Has("--json"), @out);
                }
                case "run":
                {
                    var f = opts.Positional ?? throw new ArgumentException("run needs a formula");
                    var data = File.ReadAllText(opts.Get("--data") ?? throw new ArgumentException("--data is required"));
                    @out.WriteLine(await Evaluator.RunAsync(f, ctx, data));
                    return 0;
                }
                default:
                    err.WriteLine($"Unknown command '{args[0]}'.\n{Usage}");
                    return 2;
            }
        }
        catch (Exception ex) when (ex is ArgumentException or IOException or FormatException or InvalidOperationException or JsonException or YamlDotNet.Core.YamlException)
        {
            err.WriteLine("error: " + ex.Message);
            return 2;
        }
    }

    static int Report(Reviewer reviewer, List<FormulaItem> formulas, bool json, TextWriter @out)
    {
        var reviews = formulas.Select(reviewer.Review).ToList();
        if (json)
        {
            var payload = reviews.Select(r => new
            {
                where = r.Item.Where, file = r.Item.File, status = r.Status, returns = r.ReturnType, formula = r.Item.Formula,
                findings = r.Findings.Select(f => new { f.Code, severity = f.Severity.ToString().ToLowerInvariant(), f.Message }),
            });
            @out.WriteLine(JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true }));
        }
        else
        {
            foreach (var r in reviews)
            {
                var mark = r.Status switch { "ok" when r.Findings.Count == 0 => "OK     ", "ok" => "WARN   ", "partial" => "PARTIAL", _ => "ERROR  " };
                @out.WriteLine($"{mark} {r.Item.Where}" + (r.ReturnType is null ? "" : $"  -> {r.ReturnType}"));
                foreach (var f in r.Findings) @out.WriteLine($"          {f.Code} {f.Severity.ToString().ToLowerInvariant(),-7} {f.Message}");
            }
            int ok = reviews.Count(r => r.Status == "ok" && r.Findings.Count == 0);
            int err = reviews.Count(r => r.HasErrors);
            int warn = reviews.Count(r => !r.HasErrors && r.Findings.Any(f => f.Severity == Severity.Warning));
            int partial = reviews.Count(r => r.Status == "partial" && !r.HasErrors);
            @out.WriteLine($"\n{reviews.Count} formulas: {ok} clean, {warn} with warnings, {partial} partly checked, {err} with errors");
        }
        return reviews.Any(r => r.HasErrors) ? 1 : 0;
    }
}

sealed class Options
{
    readonly Dictionary<string, string?> _named = new();
    public string? Positional { get; private set; }
    public static Options Parse(string[] args)
    {
        var o = new Options();
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i].StartsWith("--"))
            {
                bool hasValue = i + 1 < args.Length && !args[i + 1].StartsWith("--") && args[i] != "--json";
                o._named[args[i]] = hasValue ? args[++i] : null;
            }
            else o.Positional ??= args[i];
        }
        return o;
    }
    public string? Get(string name) => _named.TryGetValue(name, out var v) ? v : null;
    public bool Has(string name) => _named.ContainsKey(name);
}
