using System.Text.RegularExpressions;
using Json.Schema;
using Xunit;

namespace EquipmentDesk.Formulas.Tests;

public class SourceTests
{
    private static readonly CanvasSource Source = new();

    public static IEnumerable<object[]> Files() =>
        Directory.GetFiles(CanvasSource.SrcDir, "*.pa.yaml").Select(f => new object[] { Path.GetFileName(f) });

    internal static JsonSchema LoadSchema()
    {
        var yaml = CanvasSource.YamlReader()
            .Deserialize<object?>(File.ReadAllText(Path.Combine(CanvasSource.RepoDir, "tests", "schema", "pa.schema.yaml")));
        var text = CanvasSource.ToJson(yaml)!.ToJsonString();
        // Same workaround as episode 2: the v3.0 schema's CodeComponent-ComponentName pattern has an unbalanced ')'.
        return JsonSchema.FromText(text.Replace(BrokenPattern, FixedPattern));
    }

    internal const string BrokenPattern = "^([a-zA-Z][a-zA-Z0-9]{1,7})_)?";
    internal const string FixedPattern = "^(([a-zA-Z][a-zA-Z0-9]{1,7})_)?";

    [Fact]
    public void Upstream_schema_still_has_the_broken_code_component_pattern()
    {
        var raw = File.ReadAllText(Path.Combine(CanvasSource.RepoDir, "tests", "schema", "pa.schema.yaml"));
        Assert.Contains(BrokenPattern, raw);
        Assert.Throws<RegexParseException>(() => new Regex(BrokenPattern + "(\\w+\\.)+(\\w+)$"));
    }

    [Theory]
    [MemberData(nameof(Files))]
    public void Every_file_is_valid_against_the_official_pa_yaml_v3_schema(string file)
    {
        var result = LoadSchema().Evaluate(CanvasSource.ToJson(Source.Documents[file]), new EvaluationOptions { OutputFormat = OutputFormat.List });
        var errors = (result.Details ?? []).Where(d => d.HasErrors).SelectMany(d => d.Errors!.Select(e => $"{d.InstanceLocation}: {e.Value}"));
        Assert.True(result.IsValid, string.Join("\n", errors));
    }

    [Fact]
    public void Control_names_are_unique()
    {
        Assert.Empty(Source.DuplicateNames);
        Assert.Equal(9, Source.Controls.Count);
    }

    [Fact]
    public void App_Formulas_declares_named_formulas_functions_and_one_behavior_function()
    {
        var defs = Source.Definitions();
        Assert.Equal(new[] { "DefaultLoanDays", "MaxLoanDays", "Holidays", "OverdueCount" },
            defs.Where(d => d.Kind == CanvasSource.DefinitionKind.NamedFormula).Select(d => d.Name));
        Assert.Equal(new[] { "IsWorkingDay", "WorkingDaysBetween", "WorkingDays", "LoanState", "StateColor", "FirstName", "ReminderText" },
            defs.Where(d => d.Kind == CanvasSource.DefinitionKind.Function).Select(d => d.Name));
        Assert.Equal(new[] { "CopyReminder" },
            defs.Where(d => d.Kind == CanvasSource.DefinitionKind.BehaviorFunction).Select(d => d.Name));
    }

    [Fact]
    public void Every_user_defined_function_compiles()
    {
        var h = new Harness(Source);
        Assert.True(h.FunctionsResult.IsSuccess, string.Join("\n", h.FunctionsResult.Errors.Select(e => e.Message)));
    }

    [Fact]
    public void Named_formulas_have_values()
    {
        var h = new Harness(Source);
        Assert.Equal(14m, h.Number("DefaultLoanDays"));
        Assert.Equal(90m, h.Number("MaxLoanDays"));
        Assert.Equal(4m, h.Number("CountRows(Holidays)"));
        Assert.Equal(2m, h.Number("OverdueCount"));
    }

    [Fact]
    public void The_splitter_keeps_semicolons_inside_behavior_bodies_and_interpolated_strings()
    {
        var copy = Source.Definitions().Single(d => d.Name == "CopyReminder");
        Assert.Contains("IfError(", copy.Text);
        Assert.EndsWith("}", copy.Text);
        var reminder = Source.Definitions().Single(d => d.Name == "ReminderText");
        Assert.Contains("Thank you!\"", reminder.Text);
    }

    // Layout properties use Parent.*, which only Studio knows; these are the logic properties.
    private static readonly string[] LogicProperties = ["Items", "Text", "OnSelect", "Default", "Visible", "Color"];
    private static readonly string[] TemplateControls = ["lblLoanTitle", "lblLoanDetail", "lblLoanNotes", "btnRemind"];

    public static IEnumerable<object[]> LogicFormulas() =>
        Source.Controls.Values.SelectMany(c => c.Properties.Keys.Where(LogicProperties.Contains).Select(p => new object[] { c.Name, p }));

    [Theory]
    [MemberData(nameof(LogicFormulas))]
    public void Every_logic_formula_binds_against_the_Dataverse_shaped_tables(string control, string property)
    {
        var h = new Harness(Source);
        if (TemplateControls.Contains(control)) h.SetThisItem(h.LoanFor("CT-0043"));
        var check = h.Check(Source.Formula(control, property));
        Assert.True(check.IsSuccess, $"{control}.{property}: " + string.Join("; ", check.Errors.Select(e => e.Message)));
    }
}
