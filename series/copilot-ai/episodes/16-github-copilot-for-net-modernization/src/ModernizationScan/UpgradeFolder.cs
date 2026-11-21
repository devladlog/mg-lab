using System.Text.RegularExpressions;

namespace ModernizationScan;

public sealed record TaskState(string Id, string Title, char Mark)
{
    public bool Done => Mark is '✓' or 'x' or 'X';
    public bool Pending => Mark == ' ';
}

public sealed record ScenarioState(
    string ScenarioId,
    IReadOnlyList<string> FilesPresent,
    IReadOnlyList<string> FilesMissing,
    string Stage,
    IReadOnlyList<TaskState> Tasks,
    int? DeclaredDone,
    int? DeclaredTotal,
    IReadOnlyList<string> Problems)
{
    public bool Complete => Problems.Count == 0 && Tasks.Count > 0 && Tasks.All(t => t.Done);
}

/// <summary>
/// Reads the state GitHub Copilot upgrade keeps in the repository: .github/upgrades/{scenarioId}/ with
/// assessment.md, upgrade-options.md, plan.md, scenario-instructions.md and tasks.md (Learn: "Upgrade a .NET app",
/// "GitHub Copilot upgrade concepts"). The task list format (### [ ] TASK-001: ... and a Progress line) is the one
/// shown in Learn's example; the tool tolerates other marks and says so instead of guessing.
/// </summary>
public static partial class UpgradeFolder
{
    public static readonly string[] ExpectedFiles = ["assessment.md", "upgrade-options.md", "plan.md", "scenario-instructions.md", "tasks.md"];

    [GeneratedRegex(@"^#{2,4}\s*\[(?<mark>[^\]])\]\s*(?<id>TASK-\d+)\s*:\s*(?<title>.+?)\s*$", RegexOptions.Multiline)]
    private static partial Regex TaskHeading();

    [GeneratedRegex(@"\*\*Progress\*\*:\s*(?<done>\d+)\s*/\s*(?<total>\d+)")]
    private static partial Regex Progress();

    [GeneratedRegex(@"\s*\*\(.*\)\*\s*$")]
    private static partial Regex TrailingNote();

    public static IReadOnlyList<ScenarioState> Inspect(string repoRoot)
    {
        var upgrades = Path.Combine(repoRoot, ".github", "upgrades");
        if (!Directory.Exists(upgrades)) return [];
        return Directory.EnumerateDirectories(upgrades).OrderBy(d => d, StringComparer.Ordinal).Select(InspectScenario).ToList();
    }

    public static ScenarioState InspectScenario(string dir)
    {
        var present = ExpectedFiles.Where(f => File.Exists(Path.Combine(dir, f))).ToList();
        var missing = ExpectedFiles.Except(present).ToList();
        var stage = present.Contains("tasks.md") ? "execution" : present.Contains("plan.md") ? "planning" : present.Contains("assessment.md") ? "assessment" : "not started";

        var problems = new List<string>();
        var tasks = new List<TaskState>();
        int? done = null, total = null;
        var tasksPath = Path.Combine(dir, "tasks.md");
        if (File.Exists(tasksPath))
        {
            var text = File.ReadAllText(tasksPath);
            foreach (Match m in TaskHeading().Matches(text))
                tasks.Add(new TaskState(m.Groups["id"].Value, TrailingNote().Replace(m.Groups["title"].Value, ""), m.Groups["mark"].Value[0]));
            var pm = Progress().Match(text);
            if (pm.Success) { done = int.Parse(pm.Groups["done"].Value); total = int.Parse(pm.Groups["total"].Value); }
            if (tasks.Count == 0) problems.Add("tasks.md has no task headings in the form '### [ ] TASK-001: title'");
            if (total is not null && tasks.Count > 0 && total != tasks.Count) problems.Add($"Progress says {total} tasks but {tasks.Count} task headings were found");
            if (done is not null && tasks.Count > 0 && done != tasks.Count(t => t.Done)) problems.Add($"Progress says {done} done but {tasks.Count(t => t.Done)} headings are marked done");
            var odd = tasks.Where(t => !t.Done && !t.Pending).ToList();
            if (odd.Count > 0) problems.Add("tasks with an in-progress or unknown mark: " + string.Join(", ", odd.Select(t => $"{t.Id} [{t.Mark}]")));
        }
        else if (stage == "execution") problems.Add("tasks.md missing");

        if (present.Contains("tasks.md") && !present.Contains("plan.md")) problems.Add("tasks.md exists without plan.md");
        return new ScenarioState(Path.GetFileName(dir), present, missing, stage, tasks, done, total, problems);
    }
}
