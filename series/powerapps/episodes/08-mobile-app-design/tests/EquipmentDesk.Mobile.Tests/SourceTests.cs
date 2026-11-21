using System.Text.RegularExpressions;
using Json.Schema;
using Xunit;

namespace EquipmentDesk.Mobile.Tests;

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
        return JsonSchema.FromText(CanvasSource.ToJson(yaml)!.ToJsonString().Replace(BrokenPattern, FixedPattern));
    }

    public static IEnumerable<object[]> Files() => AppSource.Documents.Keys.Select(f => new object[] { f });

    [Fact]
    public void Upstream_schema_still_has_the_broken_code_component_pattern()
    {
        var raw = File.ReadAllText(Path.Combine(CanvasSource.EpisodeDir, "tests", "schema", "pa.schema.yaml"));
        Assert.Contains(BrokenPattern, raw);
        Assert.Throws<RegexParseException>(() => new Regex(BrokenPattern + "(\\w+\\.)+(\\w+)$"));
    }

    [Theory]
    [MemberData(nameof(Files))]
    public void Every_file_is_valid_against_the_official_pa_yaml_v3_schema(string file)
    {
        var result = LoadSchema().Evaluate(CanvasSource.ToJson(AppSource.Documents[file]), new EvaluationOptions { OutputFormat = OutputFormat.List });
        var errors = (result.Details ?? []).Where(d => d.HasErrors).SelectMany(d => d.Errors!.Select(e => $"{d.InstanceLocation}: {e.Value}"));
        Assert.True(result.IsValid, string.Join("\n", errors));
    }

    [Fact]
    public void The_library_is_episode_7s_and_names_are_unique()
    {
        Assert.True(Directory.Exists(CanvasSource.LibraryDir), CanvasSource.LibraryDir);
        Assert.Equal(new[] { "ConfirmDialog", "DeskHeader", "DeskRules" }, LibrarySource.Components.Keys.Order());
        Assert.Empty(AppSource.DuplicateNames);
        Assert.Equal(new[] { "deskRules", "dlgReturn", "hdrLoans" }, AppSource.Instances.Select(i => i.Name).Order(StringComparer.Ordinal));
    }

    [Fact]
    public void Every_UDF_and_output_function_compiles()
    {
        var h = NewHarness();
        Assert.True(h.AppFunctionsResult.IsSuccess, string.Join("\n", h.AppFunctionsResult.Errors.Select(e => e.Message)));
        Assert.True(h.ComponentFunctionsResult.IsSuccess, string.Join("\n", h.ComponentFunctionsResult.Errors.Select(e => e.Message)));
    }

    private static readonly string[] LogicProperties =
        ["Items", "Text", "OnSelect", "OnScan", "OnChange", "Default", "Visible", "Color", "Fill", "DisplayMode", "Icon", "LayoutDirection", "Live"];
    internal static readonly string[] Template = ["lblLoanTitle", "lblLoanDetail", "icoOpen"];
    // btnRemind.OnSelect calls the SendLoanReminder flow; tested in episode 6.
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
        h.Eval("Set(selectedLoan, LookUp(Loans, Equipment.'Asset tag' = \"CT-0043\"))");
        if (Template.Contains(control) || control == "galLoans") h.SetThisItem(h.OpenLoan("CT-0043"));
        var check = h.Check(AppSource.Formula(control, property));
        Assert.True(check.IsSuccess, $"{control}.{property}: " + string.Join("; ", check.Errors.Select(e => e.Message)));
    }

    public static IEnumerable<object[]> InstanceProperties() =>
        AppSource.Instances.SelectMany(i => i.Properties.Keys.Where(p => p is not ("X" or "Y" or "Width" or "Height")).Select(p => new object[] { i.Name, p }));

    [Theory]
    [MemberData(nameof(InstanceProperties))]
    public void Every_instance_property_binds_in_the_app(string instance, string property)
    {
        var h = NewHarness();
        var check = h.Check(AppSource.Formula(instance, property));
        Assert.True(check.IsSuccess, $"{instance}.{property}: " + string.Join("; ", check.Errors.Select(e => e.Message)));
    }

    [Fact]
    public void Instances_set_only_what_the_library_declares()
    {
        string[] standard = ["X", "Y", "Width", "Height", "Visible"];
        foreach (var inst in AppSource.Instances)
        {
            var def = LibrarySource.Components[inst.ComponentName!];
            foreach (var prop in inst.Properties.Keys.Where(p => !standard.Contains(p)))
                Assert.True(def.CustomProperties.TryGetValue(prop, out var cp) && cp.Kind is "Input" or "Event", $"{inst.Name}.{prop}");
        }
    }

    [Fact]
    public void Screen_and_app_sizing_formulas_evaluate()
    {
        var h = NewHarness();
        Assert.Equal(780m, h.ScreenWidth);
        Assert.Equal(1688m, h.ScreenHeight);
        Assert.Equal(1, h.ScreenSize);
    }
}
