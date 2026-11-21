using System.Text.RegularExpressions;

namespace ModernizationScan;

/// <summary>
/// Checks a custom upgrade instruction file against the authoring tips on Microsoft Learn, "Apply custom upgrade
/// instructions for .NET upgrades": a short title describing the action; a concise problem or prerequisite section;
/// explicit "If X is found, do Y" logic; at least one diff or before/after example; explicit verbs (replace, remove,
/// update) instead of improve or fix; one transformation per file; a file name that starts with the verb.
/// </summary>
public static partial class InstructionLint
{
    public sealed record Issue(string Level, string Code, string Message);

    private static readonly string[] Verbs = ["replace", "remove", "update", "convert", "migrate", "add", "rename"];
    private static readonly string[] Ambiguous = ["improve", "fix", "clean up", "cleanup", "enhance", "optimize", "modernize", "better"];

    [GeneratedRegex(@"\bif\b[^.\n]{3,}\b(then|,)", RegexOptions.IgnoreCase)]
    private static partial Regex Conditional();

    [GeneratedRegex(@"^```", RegexOptions.Multiline)]
    private static partial Regex Fence();

    public static IReadOnlyList<Issue> Check(string fileName, string text)
    {
        var issues = new List<Issue>();
        var stem = Path.GetFileNameWithoutExtension(fileName);
        if (!fileName.EndsWith(".md", StringComparison.OrdinalIgnoreCase))
            issues.Add(new("error", "extension", "custom upgrade instructions are Markdown files (.md)"));
        if (!Verbs.Any(v => stem.StartsWith(v + "_", StringComparison.OrdinalIgnoreCase)))
            issues.Add(new("warning", "file-name", $"start the file name with the verb and use underscores, for example replace_x_with_y.md (got {fileName}): activation matches your request to the file name"));

        var first = text.Split('\n').FirstOrDefault(l => l.StartsWith("# ", StringComparison.Ordinal));
        if (first is null) issues.Add(new("error", "title", "no `# title` line: start with a short title describing the action"));
        else if (Regex.IsMatch(first, @"\band\b", RegexOptions.IgnoreCase)) issues.Add(new("warning", "one-transformation", "the title joins two actions with 'and': keep one transformation per file"));

        if (!Conditional().IsMatch(text))
            issues.Add(new("error", "conditional", "no explicit conditional step logic: write 'If X is found, then do Y'"));

        var fences = Fence().Matches(text).Count;
        if (fences < 2) issues.Add(new("error", "example", "no fenced code block: add at least one diff or before/after example"));
        else if (!text.Contains("```diff", StringComparison.Ordinal)) issues.Add(new("info", "diff", "no ```diff block: a diff captured from a real local edit is the recommended example"));

        var prose = Regex.Replace(text, "```.*?```", "", RegexOptions.Singleline).ToLowerInvariant();
        foreach (var word in Ambiguous.Where(w => Regex.IsMatch(prose, $@"\b{Regex.Escape(w)}\b")))
            issues.Add(new("warning", "ambiguous-verb", $"'{word}' is ambiguous: say replace, remove or update, and name the package or API"));

        if (text.Split('\n').Count(l => l.StartsWith("#", StringComparison.Ordinal)) < 2)
            issues.Add(new("info", "structure", "add a short prerequisite or detection section under the title"));
        return issues;
    }
}
