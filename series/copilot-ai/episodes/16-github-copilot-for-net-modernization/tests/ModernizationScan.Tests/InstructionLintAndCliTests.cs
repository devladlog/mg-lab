using static ModernizationScan.Tests.Fixtures;

namespace ModernizationScan.Tests;

public class InstructionLintAndCliTests
{
    private static string DemoInstruction => Path.Combine(Fixtures.Legacy, "upgrade-instructions", "replace_newtonsoft_with_system_text_json.md");

    [Fact]
    public void The_episode_instruction_file_passes()
    {
        var issues = InstructionLint.Check(Path.GetFileName(DemoInstruction), File.ReadAllText(DemoInstruction));
        Assert.DoesNotContain(issues, i => i.Level != "info");
    }

    [Fact]
    public void Vague_instruction_is_rejected_on_every_documented_tip()
    {
        var issues = InstructionLint.Check("json.md", "# Improve JSON and logging\n\nMake serialization better and fix problems.\n");
        var codes = issues.Select(i => i.Code).ToHashSet();
        Assert.Contains("file-name", codes);
        Assert.Contains("one-transformation", codes);
        Assert.Contains("conditional", codes);
        Assert.Contains("example", codes);
        Assert.Contains("ambiguous-verb", codes);
        Assert.Equal(["better", "fix", "improve"], issues.Where(i => i.Code == "ambiguous-verb").Select(i => i.Message.Split('\'')[1]).Order().ToArray());
    }

    [Fact]
    public void Ambiguous_words_inside_code_blocks_are_not_flagged()
    {
        var text = "# Replace a with b\n\nIf a is found, then use b.\n\n```diff\n-fix\n+better\n```\n";
        Assert.DoesNotContain(InstructionLint.Check("replace_a_with_b.md", text), i => i.Code == "ambiguous-verb");
    }

    [Fact]
    public void Missing_title_and_wrong_extension_are_errors()
    {
        var codes = InstructionLint.Check("replace_a.txt", "If x, then y\n```\nx\n```").Where(i => i.Level == "error").Select(i => i.Code);
        Assert.Contains("title", codes);
        Assert.Contains("extension", codes);
    }

    [Fact]
    public void Cli_scan_writes_markdown_and_json_files()
    {
        using var t = new Temp();
        var md = Path.Combine(t.Path, "r.md");
        var json = Path.Combine(t.Path, "r.json");
        Assert.Equal(0, Cli.Run(["scan", Fixtures.Legacy, "--md", md, "--json", json], new StringWriter(), new StringWriter()));
        Assert.Contains("# Modernization pre-scan", File.ReadAllText(md));
        Assert.StartsWith("{", File.ReadAllText(json).TrimStart());
    }

    [Fact]
    public void Cli_reports_errors_with_exit_code_2()
    {
        var err = new StringWriter();
        Assert.Equal(2, Cli.Run(["scan", "/definitely/not/here"], new StringWriter(), err));
        Assert.Contains("not a directory", err.ToString());
        Assert.Equal(2, Cli.Run(["scan"], new StringWriter(), err));
        Assert.Equal(2, Cli.Run(["nope", "x"], new StringWriter(), err));
    }

    [Fact]
    public void Cli_lint_instruction_exit_code()
    {
        var o = new StringWriter();
        Assert.Equal(0, Cli.Run(["lint-instruction", DemoInstruction], o, new StringWriter()));
    }
}
