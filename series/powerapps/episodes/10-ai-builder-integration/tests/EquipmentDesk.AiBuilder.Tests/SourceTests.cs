using System.Text.RegularExpressions;
using Json.Schema;
using Xunit;

namespace EquipmentDesk.AiBuilder.Tests;

public class SourceTests
{
    internal const string BrokenPattern = "^([a-zA-Z][a-zA-Z0-9]{1,7})_)?";
    internal const string FixedPattern = "^(([a-zA-Z][a-zA-Z0-9]{1,7})_)?";

    internal static JsonSchema LoadSchema()
    {
        var yaml = CanvasSource.YamlReader().Deserialize<object?>(File.ReadAllText(Path.Combine(CanvasSource.EpisodeDir, "tests", "schema", "pa.schema.yaml")));
        // Same workaround as episodes 2, 3, 7 and 8: the v3.0 schema's CodeComponent-ComponentName pattern has an unbalanced ')'.
        return JsonSchema.FromText(CanvasSource.ToJson(yaml)!.ToJsonString().Replace(BrokenPattern, FixedPattern));
    }

    public static IEnumerable<object[]> Files() => FormulaTests.App.Documents.Keys.Select(f => new object[] { f });

    [Theory]
    [MemberData(nameof(Files))]
    public void Every_file_is_valid_against_the_official_pa_yaml_v3_schema(string file)
    {
        var result = LoadSchema().Evaluate(CanvasSource.ToJson(FormulaTests.App.Documents[file]), new EvaluationOptions { OutputFormat = OutputFormat.List });
        var errors = (result.Details ?? []).Where(d => d.HasErrors).SelectMany(d => d.Errors!.Select(e => $"{d.InstanceLocation}: {e.Value}"));
        Assert.True(result.IsValid, string.Join("\n", errors));
    }

    [Fact]
    public void Control_names_are_unique_and_the_start_screen_exists()
    {
        Assert.Empty(FormulaTests.App.DuplicateNames);
        Assert.Equal("=ReturnCheckScreen", FormulaTests.App.AppProperties["StartScreen"]);
        Assert.Contains(FormulaTests.App.Controls.Values, c => c.Owner == "ReturnCheckScreen");
    }

    [Fact]
    public void Every_triage_function_compiles_and_the_named_formulas_evaluate()
    {
        var h = new Harness(FormulaTests.App);
        Assert.True(h.FunctionsResult.IsSuccess, string.Join("\n", h.FunctionsResult.Errors.Select(e => e.Message)));
        Assert.Equal(8, FormulaTests.App.Definitions().Count(d => d.Kind == CanvasSource.DefinitionKind.Function));
        Assert.Equal(4, FormulaTests.App.Definitions().Count(d => d.Kind == CanvasSource.DefinitionKind.NamedFormula));
    }

    // Layout properties use Parent/Self, which only Studio knows; these are the logic properties.
    private static readonly string[] LogicProperties = ["Items", "Text", "OnSelect", "Default", "Visible", "DisplayMode", "MaxLength", "Mode"];

    public static IEnumerable<object[]> Formulas() =>
        FormulaTests.App.Controls.Values
            .SelectMany(c => c.Properties.Keys.Where(LogicProperties.Contains).Select(p => new object[] { c.Name, p }));

    [Theory]
    [MemberData(nameof(Formulas))]
    public void Every_logic_formula_binds(string control, string property)
    {
        var check = new Harness(FormulaTests.App).Check(FormulaTests.App.Formula(control, property));
        Assert.True(check.IsSuccess, $"{control}.{property}: " + string.Join("; ", check.Errors.Select(e => e.Message)));
    }

    [Fact]
    public void The_Predict_rewrite_only_touches_the_prompt_call()
    {
        Assert.Equal("ReturnNoteTriage__Predict(TriageInput(txtNote.Text)).text", Harness.Rewrite("'ReturnNoteTriage'.Predict(TriageInput(txtNote.Text)).text"));
        foreach (var untouched in new[] { "Notify(\"x\", NotificationType.Error)", "returnLoan.Equipment.'Asset tag'", "ParseJSON(raw).condition" })
            Assert.Equal(untouched, Harness.Rewrite(untouched));
    }

    [Fact]
    public void Predict_is_called_in_exactly_one_place_and_always_inside_IfError()
    {
        var calls = FormulaTests.App.Controls.Values
            .SelectMany(c => c.Properties.Select(p => (c.Name, p.Key, p.Value)))
            .Where(x => x.Value.Contains(".Predict(")).ToList();
        var only = Assert.Single(calls);
        Assert.Equal(("btnCheck", "OnSelect"), (only.Name, only.Key));
        Assert.Matches(@"IfError\('ReturnNoteTriage'\.Predict\(TriageInput\(txtNote\.Text\)\)\.text, """"\)", only.Value);
    }

    [Fact]
    public void Nothing_in_the_source_has_a_real_tenant_name_url_or_guid()
    {
        var files = Directory.GetFiles(Path.Combine(CanvasSource.EpisodeDir, "src"), "*", SearchOption.AllDirectories);
        Assert.NotEmpty(files);
        foreach (var f in files)
        {
            var text = File.ReadAllText(f);
            Assert.DoesNotContain("devladlog", text, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotMatch(@"https?://", text);
            Assert.DoesNotMatch(@"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", text);
        }
    }
}
