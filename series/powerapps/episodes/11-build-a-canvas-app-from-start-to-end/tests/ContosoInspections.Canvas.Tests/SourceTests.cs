using System.Text.RegularExpressions;
using Json.Schema;
using Microsoft.PowerFx.Types;
using Xunit;

namespace ContosoInspections.Canvas.Tests;

/// <summary>The source files are valid pa.yaml, every formula binds against the schema-built tables, and the schema/app agree.</summary>
public class SourceTests
{
    internal static readonly CanvasSource AppSource = new(CanvasSource.AppDir);
    internal static Harness NewHarness() => new(AppSource);

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
        // Same note as episodes 3 to 9: the published schema's code-component pattern has an unbalanced group, patched in memory only.
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
    public void The_app_has_the_four_screens_and_starts_on_the_list()
    {
        Assert.Equal(Harness.ScreenNames.OrderBy(x => x), AppSource.ScreenProperties.Keys.OrderBy(x => x));
        Assert.Equal("=InspectionsScreen", AppSource.AppProperties["StartScreen"]);
    }

    [Fact]
    public void Control_names_are_unique_across_the_app()
    {
        Assert.Empty(AppSource.DuplicateNames);
    }

    [Fact]
    public void Every_UDF_and_named_formula_compiles_against_the_schema_built_tables()
    {
        var h = NewHarness();
        Assert.True(h.FunctionsResult.IsSuccess, string.Join("\n", h.FunctionsResult.Errors.Select(e => e.ToString())));
        var defs = AppSource.Definitions();
        Assert.Equal(6, defs.Count(d => d.Kind == CanvasSource.DefinitionKind.NamedFormula));
        Assert.Equal(new[] { "StartInspection", "AddFinding", "ResolveFinding", "SubmitInspection" },
            defs.Where(d => d.Kind == CanvasSource.DefinitionKind.BehaviorFunction).Select(d => d.Name));
    }

    /// <summary>
    /// Every property formula of every control binds: no typo in a column, choice, control or variable name survives. Template
    /// controls see ThisItem as the gallery's table row; Self and Parent are generic records (layout only).
    /// </summary>
    [Fact]
    public void Every_control_formula_binds()
    {
        // The engine fixes a variable's type when it is first declared, so ThisItem gets one harness per gallery table.
        var inspections = NewHarness();
        inspections.SetThisItem(inspections.InspectionRow("CPE-02-20261127-AD-001"));
        var findings = NewHarness();
        findings.SetThisItem(findings.FindingRow("Fire door wedged open"));
        var problems = new List<string>();
        foreach (var c in AppSource.Controls.Values)
        {
            var h = c.Parent == "galFindings" || c.Name == "galFindings" ? findings : inspections;
            foreach (var (prop, raw) in c.Properties)
            {
                if (!raw.StartsWith('=')) { problems.Add($"{c.Name}.{prop}: not a formula"); continue; }
                var check = h.Check(CanvasSource.Strip(raw));
                if (!check.IsSuccess) problems.Add($"{c.Name}.{prop}: {string.Join("; ", check.Errors.Select(e => e.Message))}");
            }
        }
        foreach (var (screen, props) in AppSource.ScreenProperties)
            foreach (var (prop, raw) in props)
            {
                var check = inspections.Check(CanvasSource.Strip(raw));
                if (!check.IsSuccess) problems.Add($"{screen}.{prop}: {string.Join("; ", check.Errors.Select(e => e.Message))}");
            }
        Assert.True(problems.Count == 0, string.Join("\n", problems));
    }

    [Fact]
    public void The_dropdown_lists_are_the_schema_choices()
    {
        var h = NewHarness();
        string[] Items(string control) =>
            ((TableValue)h.Eval(AppSource.Formula(control, "Items"))).Rows.Select(r => ((StringValue)r.Value.GetField("Value")).Value).ToArray();
        string[] Options(string column)
        {
            var (table, col) = (column.Split('.')[0], column.Split('.')[1]);
            return h.Schema.GetProperty("tables").EnumerateArray().First(t => Harness.Logical(t.GetProperty("schemaName").GetString()!) == table)
                .GetProperty("columns").EnumerateArray().First(c => Harness.Logical(c.GetProperty("schemaName").GetString()!) == col)
                .GetProperty("options").EnumerateArray().Select(o => o.GetString()!).ToArray();
        }

        Assert.Equal(Options("cin_finding.cin_severity"), Items("drpSeverity"));
        Assert.Equal(Options("cin_finding.cin_category"), Items("drpCategory"));
        Assert.Equal(Options("cin_inspection.cin_result"), Items("drpResult"));
    }

    [Fact]
    public void MaxPhotoKB_is_the_image_column_limit_in_the_schema()
    {
        var h = NewHarness();
        var finding = h.Schema.GetProperty("tables").EnumerateArray().First(t => t.GetProperty("schemaName").GetString() == "cin_Finding");
        var photo = finding.GetProperty("columns").EnumerateArray().First(c => c.GetProperty("schemaName").GetString() == "cin_Photo");
        Assert.Equal(photo.GetProperty("maxSizeKB").GetDecimal(), h.Number("MaxPhotoKB"));
    }

    [Fact]
    public void The_app_only_reads_tables_the_security_role_can_read()
    {
        // Dataverse, not the app, decides who sees what: the role must let the inspector read every table the app queries.
        var h = NewHarness();
        var role = h.Schema.GetProperty("securityRole").GetProperty("privileges").EnumerateArray()
            .Where(p => p.TryGetProperty("Read", out _)).Select(p => p.GetProperty("table").GetString()!).ToHashSet();
        var yaml = string.Join("\n", Directory.GetFiles(CanvasSource.AppDir, "*.yaml").Select(File.ReadAllText));
        var used = h.Schema.GetProperty("tables").EnumerateArray()
            .Where(t => Regex.IsMatch(yaml, $@"\b{t.GetProperty("pluralName").GetString()}\b"))
            .Select(t => Harness.Logical(t.GetProperty("schemaName").GetString()!)).ToList();
        Assert.Equal(4, used.Count);
        Assert.All(used, t => Assert.Contains(t, role));
    }

    [Fact]
    public void There_is_no_my_inspections_filter_in_the_app_because_the_role_scopes_the_rows()
    {
        var all = string.Join("\n", Directory.GetFiles(CanvasSource.AppDir, "*.yaml").Select(File.ReadAllText));
        Assert.DoesNotMatch(@"Owner\b|\bCreated By\b|User\(\)\.Email\s*=\s*Owner", all);
        var role = Harness.LoadSchema().GetProperty("securityRole").GetProperty("privileges").EnumerateArray();
        foreach (var table in new[] { "cin_inspection", "cin_finding" })
            Assert.Equal("Basic", role.First(p => p.GetProperty("table").GetString() == table).GetProperty("Read").GetString());
    }
}
