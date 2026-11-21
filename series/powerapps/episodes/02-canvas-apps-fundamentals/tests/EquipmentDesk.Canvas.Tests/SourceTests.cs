using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Json.Schema;
using Microsoft.PowerFx.Types;
using Xunit;

namespace EquipmentDesk.Canvas.Tests;

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
        // The v3.0 schema's CodeComponent-ComponentName pattern has an unbalanced ')' and doesn't compile as a regex.
        // Patch that one pattern in memory (we don't use code components); see the test below.
        return JsonSchema.FromText(text.Replace(BrokenPattern, FixedPattern));
    }

    internal const string BrokenPattern = "^([a-zA-Z][a-zA-Z0-9]{1,7})_)?";
    internal const string FixedPattern = "^(([a-zA-Z][a-zA-Z0-9]{1,7})_)?";

    [Fact]
    public void Upstream_schema_still_has_the_broken_code_component_pattern()
    {
        // When this fails, Microsoft fixed the schema: delete the workaround in LoadSchema.
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
    public void Schema_rejects_a_formula_without_the_leading_equals_sign()
    {
        var bad = JsonNode.Parse("""{ "Screens": { "S": { "Children": [ { "lbl": { "Control": "Label", "Properties": { "Text": "Hello" } } } ] } } }""");
        Assert.False(LoadSchema().Evaluate(bad).IsValid);
    }

    [Fact]
    public void Control_names_are_unique_across_the_app()
    {
        Assert.Empty(Source.DuplicateNames);
        Assert.Equal(15, Source.Controls.Count);
    }

    [Fact]
    public void Named_formulas_are_declared_once_in_App_Formulas()
    {
        var h = new Harness(Source);
        Assert.Equal(new[] { "DefaultLoanDays", "MaxLoanDays" }, Source.NamedFormulas().Select(f => f.Name));
        Assert.Equal(14m, ((DecimalValue)h.Eval("DefaultLoanDays")).Value);
        Assert.Equal(90m, ((DecimalValue)h.Eval("MaxLoanDays")).Value);
    }

    // Layout and colour properties use Parent.* and RGBA, which only Studio knows; these are the logic properties.
    private static readonly string[] LogicProperties = ["Items", "Text", "OnSelect", "Default", "DefaultDate", "DisplayMode", "HintText"];

    public static IEnumerable<object[]> LogicFormulas() =>
        Source.Controls.Values.SelectMany(c => c.Properties.Keys.Where(LogicProperties.Contains).Select(p => new object[] { c.Name, p }));

    [Theory]
    [MemberData(nameof(LogicFormulas))]
    public void Every_logic_formula_binds_against_the_Dataverse_shaped_tables(string control, string property)
    {
        var h = new Harness(Source);
        h.Engine.UpdateVariable("ThisItem", h.Equipment.Rows.First().Value);
        h.SetControl("lblError", ("Text", FormulaValue.New("")));
        var check = h.Check(Source.Formula(control, property));
        Assert.True(check.IsSuccess, $"{control}.{property}: " + string.Join("; ", check.Errors.Select(e => e.Message)));
    }
}
