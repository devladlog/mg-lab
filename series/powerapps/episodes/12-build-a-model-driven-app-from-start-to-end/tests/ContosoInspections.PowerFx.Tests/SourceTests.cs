using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Json.Schema;
using Xunit;

namespace ContosoInspections.PowerFx.Tests;

public class SourceTests
{
    private static readonly PageSource Page = new();
    private static readonly string SchemaFile = Path.Combine(Episode.Dir, "tests", "schema", "pa.schema.yaml");

    public static IEnumerable<object[]> Files() => Directory.GetFiles(PageSource.SrcDir, "*.pa.yaml").Select(f => new object[] { Path.GetFileName(f) });

    // The official v3.0 schema has a broken regex (unbalanced parenthesis in CodeComponent-ComponentName); patch it in memory (see episode 2).
    private const string Broken = "^([a-zA-Z][a-zA-Z0-9]{1,7})_)?";
    private const string Fixed = "^(([a-zA-Z][a-zA-Z0-9]{1,7})_)?";

    private static JsonSchema LoadSchema()
    {
        var yaml = Episode.Yaml().Deserialize<object?>(File.ReadAllText(SchemaFile));
        return JsonSchema.FromText(PageSource.ToJson(yaml)!.ToJsonString().Replace(Broken, Fixed));
    }

    [Theory]
    [MemberData(nameof(Files))]
    public void Every_file_is_valid_against_the_official_pa_yaml_v3_schema(string file)
    {
        var doc = Page.Documents[file];
        var result = LoadSchema().Evaluate(PageSource.ToJson(doc), new EvaluationOptions { OutputFormat = OutputFormat.List });
        var errors = result.Details.Where(d => d.Errors is { Count: > 0 }).SelectMany(d => d.Errors!.Select(e => $"{d.InstanceLocation}: {e.Value}"));
        Assert.True(result.IsValid, string.Join("\n", errors));
    }

    [Fact]
    public void Control_names_are_unique_and_the_page_is_a_single_screen()
    {
        Assert.Empty(Page.DuplicateNames);
        Assert.Single(Page.Controls.Values.Select(c => c.Screen).Distinct());   // Learn: custom pages typically have one screen
    }

    [Fact]
    public void Named_formulas_are_one_per_line_and_end_with_a_semicolon()
    {
        var raw = Page.AppProperties["Formulas"].TrimStart('=').Trim();
        var lines = raw.Split('\n').Select(l => l.Trim()).Where(l => l.Length > 0).ToList();
        Assert.All(lines, l => Assert.EndsWith(";", l));
        Assert.Equal(lines.Count, Page.NamedFormulas().Count);
        Assert.Equal(new[] { "InspectionId", "ThisInspection", "Findings", "OpenFindings", "OpenCritical", "PassRate", "ScoreBand", "Verdict" }, Page.NamedFormulas().Select(f => f.Name));
    }

    [Fact]
    public void Seed_files_contain_no_quoted_commas_which_the_simple_reader_would_split()
    {
        foreach (var f in new[] { "inspectors.csv", "sites.csv", "inspections.csv", "items.csv" })
            Assert.DoesNotContain('"', File.ReadAllText(Episode.Src("data", f)));
    }

    [Fact]
    public void Commands_yaml_covers_the_four_commands_and_their_locations()
    {
        var c = Commands.Load().ToDictionary(x => x.Id);
        Assert.Equal(new[] { "approve", "flagfollowup", "reject", "reviewboard" }, c.Keys.Order());
        Assert.Equal(new[] { "mainForm", "mainGrid" }, c["approve"].Locations);
        Assert.Equal(new[] { "mainGrid" }, c["flagfollowup"].Locations);
        Assert.Equal(new[] { "mainForm" }, c["reviewboard"].Locations);
    }

    [Fact]
    public void The_custom_page_name_used_by_the_command_is_the_display_name_of_the_page()
    {
        var cmd = Commands.Get("reviewboard").OnSelect;
        Assert.Contains("'Inspection review board'", cmd);
        Assert.Contains("Inspection review board", File.ReadAllText(Path.Combine(PageSource.SrcDir, "App.pa.yaml")));
    }
}
