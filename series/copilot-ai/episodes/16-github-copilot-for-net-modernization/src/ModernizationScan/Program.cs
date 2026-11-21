using ModernizationScan;

return Cli.Run(args, Console.Out, Console.Error);

public static class Cli
{
    private const string Usage = """
        usage:
          ModernizationScan scan <solution-folder> [--md <file>] [--json <file>]
          ModernizationScan check-upgrade <repo-folder>
          ModernizationScan lint-instruction <file.md>
        """;

    public static int Run(string[] args, TextWriter output, TextWriter error)
    {
        try
        {
            if (args.Length < 2) { error.WriteLine(Usage); return 2; }
            switch (args[0])
            {
                case "scan":
                {
                    var report = Scanner.Scan(args[1]);
                    string? md = Option(args, "--md"), json = Option(args, "--json");
                    if (md is not null) File.WriteAllText(md, ReportWriter.ToMarkdown(report));
                    if (json is not null) File.WriteAllText(json, ReportWriter.ToJson(report));
                    if (md is null && json is null) output.Write(ReportWriter.ToMarkdown(report));
                    return 0;
                }
                case "check-upgrade":
                {
                    var states = UpgradeFolder.Inspect(args[1]);
                    if (states.Count == 0) { output.WriteLine("no .github/upgrades folder: the agent has not run in this repository"); return 1; }
                    var ok = true;
                    foreach (var s in states)
                    {
                        output.WriteLine($"{s.ScenarioId}: stage {s.Stage}, tasks {s.Tasks.Count(t => t.Done)}/{s.Tasks.Count}" + (s.Complete ? " (complete)" : ""));
                        if (s.FilesMissing.Count > 0) output.WriteLine("  missing so far: " + string.Join(", ", s.FilesMissing));
                        foreach (var t in s.Tasks.Where(t => !t.Done)) output.WriteLine($"  open: {t.Id} [{t.Mark}] {t.Title}");
                        foreach (var p in s.Problems) output.WriteLine("  problem: " + p);
                        ok &= s.Complete;
                    }
                    return ok ? 0 : 1;
                }
                case "lint-instruction":
                {
                    var issues = InstructionLint.Check(Path.GetFileName(args[1]), File.ReadAllText(args[1]));
                    foreach (var i in issues) output.WriteLine($"{i.Level.ToUpperInvariant(),-7} {i.Code}: {i.Message}");
                    if (issues.Count == 0) output.WriteLine("instruction file: OK");
                    return issues.Any(i => i.Level == "error") ? 1 : 0;
                }
                default:
                    error.WriteLine(Usage);
                    return 2;
            }
        }
        catch (Exception ex) when (ex is IOException or InvalidOperationException or InvalidDataException or UnauthorizedAccessException or System.Xml.XmlException)
        {
            error.WriteLine("error: " + ex.Message);
            return 2;
        }
    }

    private static string? Option(string[] args, string name)
    {
        var i = Array.IndexOf(args, name);
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
    }
}
