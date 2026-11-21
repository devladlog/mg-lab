using System.Text.RegularExpressions;
using Json.Schema;
using Xunit;

namespace EquipmentDesk.Components.Tests;

public class SourceTests
{
    internal static readonly CanvasSource AppSource = new(CanvasSource.AppDir);
    internal static readonly CanvasSource LibrarySource = new(CanvasSource.LibraryDir);
    internal static Harness NewHarness() => new(AppSource, LibrarySource);

    internal const string BrokenPattern = "^([a-zA-Z][a-zA-Z0-9]{1,7})_)?";
    internal const string FixedPattern = "^(([a-zA-Z][a-zA-Z0-9]{1,7})_)?";

    internal static JsonSchema LoadSchema()
    {
        var yaml = CanvasSource.YamlReader().Deserialize<object?>(File.ReadAllText(Path.Combine(CanvasSource.EpisodeDir, "tests", "schema", "pa.schema.yaml")));
        // Same workaround as episodes 2 and 3: the v3.0 schema's CodeComponent-ComponentName pattern has an unbalanced ')'.
        return JsonSchema.FromText(CanvasSource.ToJson(yaml)!.ToJsonString().Replace(BrokenPattern, FixedPattern));
    }

    public static IEnumerable<object[]> Files() =>
        AppSource.Documents.Keys.Select(f => new object[] { "app", f })
            .Concat(LibrarySource.Documents.Keys.Select(f => new object[] { "library", f }));

    [Fact]
    public void Upstream_schema_still_has_the_broken_code_component_pattern()
    {
        var raw = File.ReadAllText(Path.Combine(CanvasSource.EpisodeDir, "tests", "schema", "pa.schema.yaml"));
        Assert.Contains(BrokenPattern, raw);
        Assert.Throws<RegexParseException>(() => new Regex(BrokenPattern + "(\\w+\\.)+(\\w+)$"));
    }

    [Theory]
    [MemberData(nameof(Files))]
    public void Every_file_is_valid_against_the_official_pa_yaml_v3_schema(string source, string file)
    {
        var doc = (source == "app" ? AppSource : LibrarySource).Documents[file];
        var result = LoadSchema().Evaluate(CanvasSource.ToJson(doc), new EvaluationOptions { OutputFormat = OutputFormat.List });
        var errors = (result.Details ?? []).Where(d => d.HasErrors).SelectMany(d => d.Errors!.Select(e => $"{d.InstanceLocation}: {e.Value}"));
        Assert.True(result.IsValid, string.Join("\n", errors));
    }

    [Fact]
    public void The_library_has_three_components_and_a_test_screen_and_names_are_unique()
    {
        Assert.Equal(new[] { "ConfirmDialog", "DeskHeader", "DeskRules" }, LibrarySource.Components.Keys.Order());
        Assert.Contains(LibrarySource.Controls.Values, c => c.Owner == "LibraryTestScreen" && !c.InComponent);
        Assert.Empty(LibrarySource.DuplicateNames);
        Assert.Empty(AppSource.DuplicateNames);
    }

    [Fact]
    public void Every_UDF_and_every_output_function_compiles()
    {
        var h = NewHarness();
        Assert.True(h.AppFunctionsResult.IsSuccess, string.Join("\n", h.AppFunctionsResult.Errors.Select(e => e.Message)));
        Assert.True(h.ComponentFunctionsResult.IsSuccess, string.Join("\n", h.ComponentFunctionsResult.Errors.Select(e => e.Message)));
        Assert.Equal(4, h.OutputFunctionUdfs().Count()); // 2 functions x 2 DeskRules instances (deskRules, rulesTest)
    }

    // Layout properties use Parent/Self, which only Studio knows; these are the logic properties.
    private static readonly string[] LogicProperties = ["Items", "Text", "OnSelect", "Default", "Visible", "Color", "Fill", "DisplayMode"];
    private static readonly string[] Template = ["lblLoanTitle", "lblLoanDetail", "lblLoanNotes", "btnRemind", "btnReturn"];
    // btnRemind calls the SendLoanReminder flow; its formulas are unchanged and tested in episode 6.
    private static readonly string[] TestedInEpisode6 = ["btnRemind.OnSelect"];

    public static IEnumerable<object[]> AppFormulas() =>
        AppSource.Controls.Values.Where(c => c.Type != "CanvasComponent")
            .SelectMany(c => c.Properties.Keys.Where(LogicProperties.Contains).Select(p => new object[] { c.Name, p }))
            .Where(x => !TestedInEpisode6.Contains($"{x[0]}.{x[1]}"));

    [Theory]
    [MemberData(nameof(AppFormulas))]
    public void Every_app_logic_formula_binds(string control, string property)
    {
        var h = NewHarness();
        if (Template.Contains(control)) h.SetThisItem(h.OpenLoan("CT-0043"));
        var check = h.Check(AppSource.Formula(control, property));
        Assert.True(check.IsSuccess, $"{control}.{property}: " + string.Join("; ", check.Errors.Select(e => e.Message)));
    }

    public static IEnumerable<object[]> InstanceProperties() =>
        AppSource.Instances.Concat(LibrarySource.Instances)
            .SelectMany(i => i.Properties.Keys.Where(p => p is not ("X" or "Y" or "Width" or "Height")).Select(p => new object[] { i.Name, p }));

    [Theory]
    [MemberData(nameof(InstanceProperties))]
    public void Every_instance_property_binds_in_the_app(string instance, string property)
    {
        var h = NewHarness();
        var src = AppSource.Controls.ContainsKey(instance) ? AppSource : LibrarySource;
        var check = h.Check(src.Formula(instance, property));
        Assert.True(check.IsSuccess, $"{instance}.{property}: " + string.Join("; ", check.Errors.Select(e => e.Message)));
    }

    public static IEnumerable<object[]> ComponentFormulas() =>
        LibrarySource.Controls.Values.Where(c => c.InComponent)
            .SelectMany(c => c.Properties.Keys.Where(LogicProperties.Contains).Select(p => new object[] { c.Owner, c.Name, p }));

    [Theory]
    [MemberData(nameof(ComponentFormulas))]
    public void Every_formula_inside_a_component_binds(string component, string control, string property)
    {
        var h = NewHarness();
        var check = h.CheckInside(component, LibrarySource.Formula(control, property));
        Assert.True(check.IsSuccess, $"{component}/{control}.{property}: " + string.Join("; ", check.Errors.Select(e => e.Message)));
    }

    [Fact]
    public void The_call_rewrite_only_touches_component_function_properties()
    {
        var h = NewHarness();
        Assert.Equal("deskRules__StateColor(\"Overdue\")", h.Rewrite("deskRules.StateColor(\"Overdue\")"));
        Assert.Equal("ConfirmDialog__OnConfirm()", h.Rewrite("ConfirmDialog.OnConfirm()"));
        foreach (var untouched in new[]
                 {
                     "returnLoan.Equipment.'Asset tag' & \" \" & Text(Today(), \"yyyy\")",
                     "ConfirmDialog.Title",            // an input: a plain value, not a call
                     "deskRules.Visible",
                     "Notify(\"x\", NotificationType.Error)",
                     "SendLoanReminder.Run(Text(ThisItem.contoso_loanid))",
                 })
            Assert.Equal(untouched, h.Rewrite(untouched));
    }
}
