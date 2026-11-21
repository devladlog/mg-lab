using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace ModernizationScan;

public static class ReportWriter
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web) { WriteIndented = true, DefaultIgnoreCondition = JsonIgnoreCondition.Never };

    public static string ToJson(Report r) => JsonSerializer.Serialize(r, JsonOptions);

    public static string ToMarkdown(Report r)
    {
        var sb = new StringBuilder();
        sb.AppendLine("# Modernization pre-scan");
        sb.AppendLine();
        sb.AppendLine($"{r.Projects.Count} project(s). Scan score {r.Score} ({r.Readiness}; our own heuristic, not a Microsoft measure).");
        sb.AppendLine();
        sb.AppendLine($"Suggested starting strategy: {r.SuggestedStrategy}. The agent proposes its own in `upgrade-options.md`.");
        sb.AppendLine();
        sb.AppendLine("## Projects, in upgrade order (leaves first)");
        sb.AppendLine();
        sb.AppendLine("| # | Project | Format | Target | Packages | Depends on |");
        sb.AppendLine("|---|---|---|---|---|---|");
        var i = 1;
        foreach (var name in r.UpgradeOrder.Concat(r.Projects.Select(p => p.Name).Except(r.UpgradeOrder, StringComparer.OrdinalIgnoreCase)))
        {
            var p = r.Projects.First(x => x.Name.Equals(name, StringComparison.OrdinalIgnoreCase));
            var kind = (p.IsSdkStyle ? "SDK-style" : "legacy") + (p.UsesPackagesConfig ? " + packages.config" : "") + (p.IsWebApplication ? " + web" : "");
            sb.AppendLine($"| {i++} | {p.Name} | {kind} | {p.TargetFramework} | {p.Packages.Count} | {(p.ProjectReferences.Count == 0 ? "-" : string.Join(", ", p.ProjectReferences))} |");
        }
        sb.AppendLine();
        sb.AppendLine("## Findings");
        sb.AppendLine();
        sb.AppendLine("| Project | Kind | What | Evidence | Learn scenario or skill |");
        sb.AppendLine("|---|---|---|---|---|");
        foreach (var f in r.Findings.OrderBy(f => f.Project, StringComparer.OrdinalIgnoreCase).ThenBy(f => f.Kind).ThenBy(f => f.What))
            sb.AppendLine($"| {f.Project} | {f.Kind} | {f.What} | `{f.Evidence}` | {f.LearnCapability ?? "none listed"} |");
        var notes = r.Findings.Where(f => f.Note.Length > 0).Select(f => $"- {f.What}: {f.Note}").Distinct().ToList();
        if (notes.Count > 0)
        {
            sb.AppendLine();
            sb.AppendLine("## Watch for");
            sb.AppendLine();
            foreach (var n in notes) sb.AppendLine(n);
        }
        if (r.Warnings.Count > 0)
        {
            sb.AppendLine();
            sb.AppendLine("## Warnings");
            sb.AppendLine();
            foreach (var w in r.Warnings) sb.AppendLine($"- {w}");
        }
        return sb.ToString();
    }
}
