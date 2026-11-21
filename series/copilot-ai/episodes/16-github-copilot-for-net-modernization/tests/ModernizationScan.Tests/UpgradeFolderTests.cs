using static ModernizationScan.Tests.Fixtures;

namespace ModernizationScan.Tests;

public class UpgradeFolderTests
{
    // The task list format is the one in Microsoft Learn's "Upgrade a .NET app with GitHub Copilot upgrade" example.
    private const string Done = """
        # MvcMovieNet6 .NET 10 Upgrade Tasks

        **Progress**: 3/3 tasks complete (100%) ![0%](https://progress-bar.xyz/100)

        ### [✓] TASK-001: Verify prerequisites *(Completed: 2025-12-12 21:09)*
        - [✓] (1) Verify .NET 10 SDK installed per Plan §Phase 0

        ### [✓] TASK-002: Atomic framework and package upgrade with compilation fixes *(Completed: 2025-12-12 21:20)*

        ### [✓] TASK-003: Run full test suite and validate upgrade *(Completed: 2025-12-12 21:30)*
        """;

    private const string Partial = """
        **Progress**: 0/3 tasks complete (0%)

        ### [ ] TASK-001: Verify prerequisites
        ### [ ] TASK-002: Atomic framework and package upgrade
        ### [ ] TASK-003: Run full test suite and validate upgrade
        """;

    private static string Scenario(Temp t, string tasks, params string[] files)
    {
        foreach (var f in files) t.Write($".github/upgrades/dotnet-version-upgrade/{f}", "# x");
        t.Write(".github/upgrades/dotnet-version-upgrade/tasks.md", tasks);
        return t.Path;
    }

    [Fact]
    public void No_upgrades_folder_means_the_agent_has_not_run()
    {
        using var t = new Temp();
        Assert.Empty(UpgradeFolder.Inspect(t.Path));
    }

    [Fact]
    public void Finished_upgrade_is_complete()
    {
        using var t = new Temp();
        var s = Assert.Single(UpgradeFolder.Inspect(Scenario(t, Done, "assessment.md", "upgrade-options.md", "plan.md", "scenario-instructions.md")));
        Assert.Equal("dotnet-version-upgrade", s.ScenarioId);
        Assert.Equal("execution", s.Stage);
        Assert.Equal(3, s.Tasks.Count(x => x.Done));
        Assert.Equal("Verify prerequisites", s.Tasks[0].Title);   // the trailing completion note is stripped
        Assert.True(s.Complete, string.Join("; ", s.Problems));
        Assert.Empty(s.FilesMissing);
    }

    [Fact]
    public void Fresh_task_list_is_not_complete_and_lists_open_tasks()
    {
        using var t = new Temp();
        var s = UpgradeFolder.Inspect(Scenario(t, Partial, "assessment.md", "plan.md")).Single();
        Assert.False(s.Complete);
        Assert.Equal(3, s.Tasks.Count(x => x.Pending));
        Assert.Contains("upgrade-options.md", s.FilesMissing);
    }

    [Fact]
    public void Stage_follows_the_files_present()
    {
        using var t = new Temp();
        t.Write(".github/upgrades/a/assessment.md", "x");
        t.Write(".github/upgrades/b/assessment.md", "x");
        t.Write(".github/upgrades/b/plan.md", "x");
        var stages = UpgradeFolder.Inspect(t.Path).ToDictionary(s => s.ScenarioId, s => s.Stage);
        Assert.Equal("assessment", stages["a"]);
        Assert.Equal("planning", stages["b"]);
    }

    [Fact]
    public void Progress_line_that_disagrees_with_the_headings_is_a_problem()
    {
        using var t = new Temp();
        var text = Done.Replace("3/3 tasks", "2/3 tasks");
        var s = UpgradeFolder.Inspect(Scenario(t, text, "plan.md")).Single();
        Assert.Contains(s.Problems, p => p.Contains("Progress says 2 done"));
        Assert.False(s.Complete);
    }

    [Fact]
    public void Unknown_marks_are_reported_not_guessed()
    {
        using var t = new Temp();
        var s = UpgradeFolder.Inspect(Scenario(t, Partial.Replace("[ ] TASK-002", "[~] TASK-002"), "plan.md")).Single();
        Assert.Contains(s.Problems, p => p.Contains("TASK-002 [~]"));
    }

    [Fact]
    public void Tasks_file_without_headings_is_a_problem()
    {
        using var t = new Temp();
        var s = UpgradeFolder.Inspect(Scenario(t, "nothing useful", "plan.md")).Single();
        Assert.Contains(s.Problems, p => p.Contains("no task headings"));
    }

    [Fact]
    public void Tasks_without_a_plan_is_a_problem()
    {
        using var t = new Temp();
        var s = UpgradeFolder.Inspect(Scenario(t, Partial)).Single();
        Assert.Contains(s.Problems, p => p.Contains("without plan.md"));
    }

    [Fact]
    public void Cli_exit_codes_follow_completion()
    {
        using var t = new Temp();
        Scenario(t, Done, "assessment.md", "upgrade-options.md", "plan.md", "scenario-instructions.md");
        var o = new StringWriter();
        Assert.Equal(0, Cli.Run(["check-upgrade", t.Path], o, new StringWriter()));
        Assert.Contains("tasks 3/3 (complete)", o.ToString());

        using var t2 = new Temp();
        Scenario(t2, Partial, "plan.md");
        var o2 = new StringWriter();
        Assert.Equal(1, Cli.Run(["check-upgrade", t2.Path], o2, new StringWriter()));
        Assert.Contains("open: TASK-001", o2.ToString());
    }
}
