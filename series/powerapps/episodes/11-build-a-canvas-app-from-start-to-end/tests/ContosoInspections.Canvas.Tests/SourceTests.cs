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
        Assert.Equal(new[] { "StartInspection", "AddItem", "ResolveItem", "SubmitInspection" },
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
        inspections.SetThisItem(inspections.InspectionRow("INS-00003"));
        var items = NewHarness();
        items.SetThisItem(items.ItemRow("Fire door"));
        var problems = new List<string>();
        foreach (var c in AppSource.Controls.Values)
        {
            var h = c.Parent == "galItems" || c.Name == "galItems" ? items : inspections;
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
        string[] Options(string table, string column) =>
            h.Schema.GetProperty("tables").EnumerateArray().First(t => t.GetProperty("logicalName").GetString() == table)
                .GetProperty("columns").EnumerateArray().First(c => c.GetProperty("logicalName").GetString() == column)
                .GetProperty("options").EnumerateArray().Select(o => o[0].GetString()!).ToArray();

        Assert.Equal(Options("cin_inspectionitem", "cin_severity"), Items("drpSeverity"));
        Assert.Equal(Options("cin_inspectionitem", "cin_category"), Items("drpCategory"));
    }

    [Fact]
    public void The_status_flow_is_the_canonical_one_and_the_app_writes_only_the_inspectors_part()
    {
        // Episode 12's schema owns the choice: Draft, In progress, Submitted, Approved, Rejected. The canvas app only ever writes the first
        // three (Draft on start, In progress on the first item, Submitted on submit); Approved and Rejected are the reviewer's.
        var h = NewHarness();
        var status = h.Schema.GetProperty("tables").EnumerateArray().First(t => t.GetProperty("logicalName").GetString() == "cin_inspection")
            .GetProperty("columns").EnumerateArray().First(c => c.GetProperty("logicalName").GetString() == "cin_status")
            .GetProperty("options").EnumerateArray().Select(o => o[0].GetString()!).ToArray();
        Assert.Equal(new[] { "Draft", "In progress", "Submitted", "Approved", "Rejected" }, status);
        var written = Regex.Matches(AppSource.AppProperties["Formulas"], @"cin_status: 'Status \(Inspections\)'\.('[^']+'|\w+)").Select(m => m.Groups[1].Value.Trim('\'')).ToArray();
        Assert.Equal(new[] { "Draft", "In progress", "Submitted" }, written);
        var all = string.Join("\n", Directory.GetFiles(CanvasSource.AppDir, "*.yaml").Select(File.ReadAllText));
        Assert.DoesNotMatch(@"cin_status: 'Status \(Inspections\)'\.(Approved|Rejected)", all);
    }

    [Fact]
    public void MaxPhotoKB_is_the_image_column_limit_in_the_schema()
    {
        var h = NewHarness();
        var item = h.Schema.GetProperty("tables").EnumerateArray().First(t => t.GetProperty("logicalName").GetString() == "cin_inspectionitem");
        var photo = item.GetProperty("columns").EnumerateArray().First(c => c.GetProperty("logicalName").GetString() == "cin_photo");
        Assert.Equal(photo.GetProperty("maxSizeKB").GetDecimal(), h.Number("MaxPhotoKB"));
    }

    [Fact]
    public void The_schema_file_is_a_byte_for_byte_copy_of_episode_12s()
    {
        // One Dataverse solution, two apps: if the canonical file changes, this copy must change with it (cp, don't edit).
        var mine = Path.Combine(CanvasSource.EpisodeDir, "src", "schema", "contosoinspections.schema.json");
        var theirs = Path.GetFullPath(Path.Combine(CanvasSource.EpisodeDir, "..", "12-build-a-model-driven-app-from-start-to-end",
            "src", "schema", "contosoinspections.schema.json"));
        Assert.True(File.Exists(theirs), $"episode 12's schema is not at {theirs}");
        Assert.Equal(File.ReadAllBytes(theirs), File.ReadAllBytes(mine));
    }

    [Fact]
    public void The_app_only_reads_tables_the_security_role_can_read()
    {
        // Dataverse, not the app, decides who sees what: the field-inspector role must let the inspector read every table the app queries.
        var h = NewHarness();
        var role = FieldInspectorRole(h).GetProperty("privileges").EnumerateObject().Where(p => p.Value.TryGetProperty("Read", out _)).Select(p => p.Name).ToHashSet();
        var yaml = string.Join("\n", Directory.GetFiles(CanvasSource.AppDir, "*.yaml").Select(File.ReadAllText));
        var used = h.Schema.GetProperty("tables").EnumerateArray()
            .Where(t => Regex.IsMatch(yaml, $@"\b{t.GetProperty("pluralName").GetString()}\b|'{t.GetProperty("pluralName").GetString()}'"))
            .Select(t => t.GetProperty("logicalName").GetString()!).ToList();
        Assert.Equal(4, used.Count);
        Assert.All(used, t => Assert.Contains(t, role));
    }

    private static System.Text.Json.JsonElement FieldInspectorRole(Harness h) =>
        h.Schema.GetProperty("security").GetProperty("roles").EnumerateArray().First(r => r.GetProperty("name").GetString() == "Inspection Field Inspector");

    [Fact]
    public void There_is_no_my_inspections_filter_in_the_app_because_the_role_scopes_the_rows()
    {
        var all = string.Join("\n", Directory.GetFiles(CanvasSource.AppDir, "*.yaml").Select(File.ReadAllText));
        Assert.DoesNotMatch(@"Owner\b|\bCreated By\b|User\(\)\.Email\s*=\s*Owner", all);
        var role = FieldInspectorRole(NewHarness()).GetProperty("privileges");
        foreach (var table in new[] { "cin_inspection", "cin_inspectionitem" })
            Assert.Equal("Basic", role.GetProperty(table).GetProperty("Read").GetString());
    }
}
