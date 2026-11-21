using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.PowerFx.Types;
using Json.Schema;
using Xunit;

namespace ContosoInspections.AI.Tests;

public class FormulaTests
{
    private static readonly CanvasSource Source = new(CanvasSource.AppDir);
    private static Harness H() => new(Source);
    private const string Good = "{\"summary\": \"Fire door wedged open.\", \"category\": \"Fire\", \"severity\": \"Major\", \"confidence\": 80}";

    [Fact]
    public void Every_function_compiles() { var h = H(); Assert.True(h.FunctionsResult.IsSuccess, string.Join("\n", h.FunctionsResult.Errors.Select(e => e.ToString()))); }

    [Fact]
    public void A_contract_conforming_answer_is_valid_and_readable()
    {
        var h = H();
        Assert.True(h.Bool($"TriageValid(\"{Good.Replace("\"", "\"\"")}\")"));
        Assert.Equal("Major", h.Text($"TriageSeverity(\"{Good.Replace("\"", "\"\"")}\")"));
        Assert.Equal("Fire", h.Text($"TriageCategory(\"{Good.Replace("\"", "\"\"")}\")"));
        Assert.Equal(80, h.Num($"TriageConfidence(\"{Good.Replace("\"", "\"\"")}\")"));
    }

    [Fact]
    public void A_code_fenced_answer_is_accepted_like_the_python_scorer_does()
    {
        var fenced = "```json\n" + Good + "\n```";
        Assert.True(H().Bool($"TriageValid(\"{fenced.Replace("\"", "\"\"")}\")"));
    }

    [Theory]
    [InlineData("")]
    [InlineData("not json at all")]
    [InlineData("{\"summary\": \"x\", \"category\": \"Fire\", \"severity\": \"Severe\", \"confidence\": 80}")]
    [InlineData("{\"summary\": \"x\", \"category\": \"Plumbing\", \"severity\": \"Major\", \"confidence\": 80}")]
    [InlineData("{\"summary\": \"x\", \"category\": \"Fire\", \"severity\": \"Major\", \"confidence\": 101}")]
    [InlineData("{\"summary\": \"x\", \"category\": \"Fire\", \"severity\": \"Major\", \"confidence\": 80.5}")]
    [InlineData("{\"summary\": \"\", \"category\": \"Fire\", \"severity\": \"Major\", \"confidence\": 80}")]
    [InlineData("{\"category\": \"Fire\", \"severity\": \"Major\", \"confidence\": 80}")]
    public void Anything_off_contract_is_invalid_and_reads_as_blank(string raw)
    {
        var h = H();
        var lit = raw.Replace("\"", "\"\"");
        Assert.False(h.Bool($"TriageValid(\"{lit}\")"));
        Assert.Equal("", h.Text($"TriageSeverity(\"{lit}\")"));
        Assert.Equal(0, h.Num($"TriageConfidence(\"{lit}\")"));
    }

    [Fact]
    public void A_summary_over_240_characters_is_invalid()
    {
        var raw = "{\"summary\": \"" + new string('a', 241) + "\", \"category\": \"Fire\", \"severity\": \"Major\", \"confidence\": 80}";
        Assert.False(H().Bool($"TriageValid(\"{raw.Replace("\"", "\"\"")}\")"));
    }

    [Theory]
    [InlineData("data:image/jpeg;base64,AAAA", "AAAA")]
    [InlineData("\"data:image/jpeg;base64,QUJD\"", "QUJD")]
    [InlineData("null", "")]
    [InlineData("", "")]
    public void Photo_json_becomes_bare_base64_for_the_flow(string json, string expected) =>
        Assert.Equal(expected, H().Text($"PhotoBase64(\"{json.Replace("\"", "\"\"")}\")"));

    [Theory]
    [InlineData("Major", false, true)]
    [InlineData("Critical", false, true)]
    [InlineData("Major", true, false)]
    [InlineData("Minor", false, false)]
    public void Major_and_Critical_suggestions_remind_about_the_photo_rule(string severity, bool hasPhoto, bool expected)
    {
        var raw = Good.Replace("Major", severity).Replace("\"", "\"\"");
        Assert.Equal(expected, H().Bool($"SuggestionNeedsPhoto(\"{raw}\", {hasPhoto.ToString().ToLowerInvariant()})"));
    }

    [Theory]
    [InlineData("", false, false)]
    [InlineData("short", false, false)]
    [InlineData("Wet floor by the dock", false, true)]
    [InlineData("Wet floor by the dock", true, false)]
    public void Suggest_needs_8_characters_and_no_call_in_flight(string notes, bool busy, bool expected) =>
        Assert.Equal(expected, H().Bool($"CanTriage(\"{notes}\", {busy.ToString().ToLowerInvariant()})"));

    [Fact]
    public void Notes_are_trimmed_and_capped_at_1500() =>
        Assert.Equal(1500, H().Text("BuildTriageNotes(Concatenate(\"   x\", \"" + new string('y', 2000) + "\"))").Length);

    [Fact]
    public void Banner_names_the_route_and_says_a_person_decides()
    {
        var banner = H().Text($"TriageBanner(\"{Good.Replace("\"", "\"\"")}\", \"claude\")");
        Assert.Equal("Claude suggests Major, Fire (80 of 100). You decide.", banner);
    }

    [Fact]
    public void Banner_on_a_bad_answer_says_nothing_was_saved() =>
        Assert.Contains("nothing was saved", H().Text("TriageBanner(\"nope\", \"foundry\")"));
}

public class ScreenTests
{
    private static readonly CanvasSource Source = new(CanvasSource.AppDir);
    private static Harness H() => new(Source);
    private const string Good = "{\"summary\": \"Fire door wedged open.\", \"category\": \"Fire\", \"severity\": \"Major\", \"confidence\": 80}";

    [Fact]
    public void Foundry_route_sends_the_prompt_as_system_message_and_the_notes_as_user_message()
    {
        var h = H();
        h.Answer = Good;
        h.Run("btnSuggest", "OnSelect");
        var call = Assert.Single(h.FoundryCalls);
        Assert.Equal("triage", call.Model);
        Assert.Equal(h.Text("TriageSystemPrompt"), call.System);
        Assert.Equal("Notes: Fire door wedged open with an extinguisher in the east stairwell.", call.User);
        Assert.Equal(Good, h.Text("triageRaw"));
        Assert.False(h.Bool("triageBusy"));
    }

    [Fact]
    public void Claude_route_sends_notes_photo_and_model_to_the_flow_and_nothing_else()
    {
        var h = H();
        h.SetVariable("triageRoute", FormulaValue.New("claude"));
        h.PhotoJsonValue = "\"data:image/jpeg;base64,QUJD\"";
        h.Answer = Good;
        h.Run("btnSuggest", "OnSelect");
        var call = Assert.Single(h.ClaudeCalls);
        Assert.Equal(("Fire door wedged open with an extinguisher in the east stairwell.", "QUJD", "claude-haiku-5-5"), call);
        Assert.Empty(h.FoundryCalls);
        Assert.Empty(h.PredictInputs);
    }

    [Fact]
    public void AI_Builder_route_gets_text_only()
    {
        var h = H();
        h.SetVariable("triageRoute", FormulaValue.New("aibuilder"));
        h.PhotoJsonValue = "\"data:image/jpeg;base64,QUJD\"";
        h.Answer = Good;
        h.Run("btnSuggest", "OnSelect");
        Assert.Equal(["Fire door wedged open with an extinguisher in the east stairwell."], h.PredictInputs);
        Assert.Empty(h.ClaudeCalls);
    }

    [Fact]
    public void A_failed_call_tells_the_inspector_and_leaves_the_result_empty()
    {
        var h = H();
        h.Error = "403 from the model route";
        h.Run("btnSuggest", "OnSelect");
        Assert.Contains(h.Calls, c => c.StartsWith("Notify(Error): The model could not answer: 403 from the model route"));
        Assert.Equal("", h.Text("triageRaw"));
        Assert.False(h.Bool("triageBusy"));
        Assert.Equal("", h.Run("lblTriageResult", "Text"));
    }

    [Fact]
    public void Result_label_shows_banner_summary_and_the_photo_reminder()
    {
        var h = H();
        h.SetVariable("triageRaw", FormulaValue.New(Good));
        var text = h.Run("lblTriageResult", "Text");
        Assert.Contains("Azure OpenAI suggests Major, Fire (80 of 100). You decide.", text);
        Assert.Contains("Fire door wedged open.", text);
        Assert.Contains("needs a photo", text);
        h.SetItem("x", "has-photo");
        Assert.DoesNotContain("needs a photo", h.Run("lblTriageResult", "Text"));
    }

    [Fact]
    public void Accept_writes_only_the_five_AI_columns_and_never_the_base_severity()
    {
        var h = H();
        h.SetVariable("triageRaw", FormulaValue.New(Good));
        h.SetVariable("triageRoute", FormulaValue.New("claude"));
        h.Run("btnAccept", "OnSelect");
        var patch = Assert.Single(h.Patches);
        Assert.Equal(new[] { "AI confidence", "AI provider", "AI severity", "AI suggestion accepted", "AI summary" }, patch.Keys.OrderBy(k => k, StringComparer.Ordinal).ToArray());
        Assert.Equal("Major", patch["AI severity"]);
        Assert.Equal("claude", patch["AI provider"]);
        Assert.Equal("80", patch["AI confidence"]);
        Assert.Equal("True", patch["AI suggestion accepted"]);
        Assert.DoesNotContain(patch.Keys, k => k is "Severity" or "Category" or "Passed");
    }

    [Fact]
    public void Save_is_disabled_until_there_is_a_valid_suggestion()
    {
        var h = H();
        Assert.Equal("Disabled", h.Run("btnAccept", "DisplayMode"));
        h.SetVariable("triageRaw", FormulaValue.New("nope"));
        Assert.Equal("Disabled", h.Run("btnAccept", "DisplayMode"));
        h.SetVariable("triageRaw", FormulaValue.New(Good));
        Assert.Equal("Edit", h.Run("btnAccept", "DisplayMode"));
    }

    [Fact]
    public void Suggest_is_disabled_while_busy_or_with_short_notes()
    {
        var h = H();
        Assert.Equal("Edit", h.Run("btnSuggest", "DisplayMode"));
        h.SetNotes("short");
        Assert.Equal("Disabled", h.Run("btnSuggest", "DisplayMode"));
    }
}

public class SourceTests
{
    private static readonly CanvasSource Source = new(CanvasSource.AppDir);
    private static string Ep(params string[] p) => Path.Combine([CanvasSource.EpisodeDir, .. p]);


    public static IEnumerable<object[]> Files() => new CanvasSource(CanvasSource.AppDir).Documents.Keys.Select(k => new object[] { k });
    private const string Broken = "^([a-zA-Z][a-zA-Z0-9]{1,7})_)?";
    private const string Fixed = "^(([a-zA-Z][a-zA-Z0-9]{1,7})_)?";

    [Theory]
    [MemberData(nameof(Files))]
    public void Every_file_is_valid_against_the_official_pa_yaml_v3_schema(string file)
    {
        var yaml = CanvasSource.YamlReader().Deserialize<object?>(File.ReadAllText(Path.Combine(CanvasSource.EpisodeDir, "tests", "schema", "pa.schema.yaml")));
        var schema = JsonSchema.FromText(CanvasSource.ToJson(yaml)!.ToJsonString().Replace(Broken, Fixed));
        var result = schema.Evaluate(CanvasSource.ToJson(Source.Documents[file]), new EvaluationOptions { OutputFormat = OutputFormat.List });
        var errors = (result.Details ?? []).Where(d => d.HasErrors).SelectMany(d => d.Errors!.Select(e => $"{d.InstanceLocation}: {e.Value}"));
        Assert.True(result.IsValid, string.Join("\n", errors));
    }

    [Fact]
    public void The_prompt_formula_is_the_system_prompt_file()
    {
        var h = new Harness(Source);
        var file = File.ReadAllText(Ep("src", "prompts", "system.md")).Trim().Replace("\r\n", "\n");
        Assert.Equal(file, h.Text("TriageSystemPrompt").Replace("\r\n", "\n"));
    }

    [Fact]
    public void Label_lists_match_the_base_schema_and_the_contract()
    {
        using var schema = JsonDocument.Parse(File.ReadAllText(Ep("src", "schema", "contosoinspections.schema.json")));
        var item = schema.RootElement.GetProperty("tables").EnumerateArray().First(t => t.GetProperty("logicalName").GetString() == "cin_inspectionitem");
        List<string> Labels(string col) => item.GetProperty("columns").EnumerateArray().First(c => c.GetProperty("logicalName").GetString() == col)
            .GetProperty("options").EnumerateArray().Select(o => o[0].GetString()!).ToList();
        var h = new Harness(Source);
        Assert.Equal(Labels("cin_severity"), h.Eval("SeverityLabels") is TableValue t ? t.Rows.Select(r => ((StringValue)r.Value.GetField("Value")).Value).ToList() : []);
        Assert.Equal(Labels("cin_category"), ((TableValue)h.Eval("CategoryLabels")).Rows.Select(r => ((StringValue)r.Value.GetField("Value")).Value).ToList());
    }

    [Fact]
    public void Every_AI_column_the_screen_writes_exists_in_the_extension_schema_with_the_same_display_name()
    {
        using var ext = JsonDocument.Parse(File.ReadAllText(Ep("src", "solution", "extension.schema.json")));
        var names = ext.RootElement.GetProperty("tables")[0].GetProperty("columns").EnumerateArray().Select(c => c.GetProperty("displayName").GetString()).ToHashSet();
        var onSelect = Source.Formula("btnAccept", "OnSelect");
        var used = Regex.Matches(onSelect, @"^\s*'(AI [^']+)':", RegexOptions.Multiline).Select(m => m.Groups[1].Value).ToList();
        Assert.Equal(5, used.Count);
        Assert.All(used, n => Assert.Contains(n, names));
    }

    [Fact]
    public void Model_calls_appear_in_exactly_one_place_and_always_inside_IfError()
    {
        var src = Source.Formula("btnSuggest", "OnSelect");
        foreach (var call in new[] { ".Predict(", "TriageFinding(", "ClaudeTriage.Run(" })
            Assert.Equal(1, src.Split(call).Length - 1);
        Assert.Contains("IfError(", src);
        foreach (var f in Directory.GetFiles(CanvasSource.AppDir, "*.pa.yaml").Where(f => !f.EndsWith("TriageScreen.pa.yaml")))
            Assert.DoesNotContain(".Predict(", File.ReadAllText(f));
    }

    [Fact]
    public void No_key_token_or_endpoint_is_in_the_app_source()
    {
        foreach (var f in Directory.GetFiles(CanvasSource.AppDir, "*.pa.yaml"))
        {
            var t = File.ReadAllText(f);
            Assert.DoesNotMatch(@"sk-[A-Za-z0-9]{10,}|x-api-key|Bearer |\.openai\.azure\.com|https?://", t.Replace("# ", "#"));
        }
    }

    [Fact]
    public void Touch_targets_are_88_units_and_controls_have_accessible_labels()
    {
        foreach (var name in new[] { "btnSuggest", "btnAccept", "btnBackTriage", "drpTriageRoute" })
        {
            var p = Source.Controls[name].Properties;
            Assert.True(p.ContainsKey("AccessibleLabel"), name);
            Assert.True(p.ContainsKey("TabIndex"), name);
        }
        Assert.Equal("=88", Source.Controls["btnSuggest"].Properties["Height"]);
    }

    [Fact]
    public void No_formula_name_clashes_with_episode_11()
    {
        var ep11 = Path.GetFullPath(Path.Combine(CanvasSource.EpisodeDir, "..", "11-build-a-canvas-app-from-start-to-end", "src", "app", "Src", "App.pa.yaml"));
        var theirs = new CanvasSource(Path.GetDirectoryName(ep11)!).Definitions().Select(d => d.Name).ToHashSet();
        var mine = Source.Definitions().Select(d => d.Name).ToList();
        Assert.Empty(mine.Where(theirs.Contains));
        Assert.Equal(mine.Count, mine.Distinct().Count());
    }
}

/// <summary>The model-driven custom page: generated from the canvas files by src/custompage/sync_from_canvas.py, so the same behaviour is checked on its own copy.</summary>
public class CustomPageTests
{
    private static readonly string PageDir = Path.Combine(CanvasSource.EpisodeDir, "src", "custompage", "Src");
    private static readonly CanvasSource Page = new(PageDir);
    private const string Good = "{\"summary\": \"Fire door wedged open.\", \"category\": \"Fire\", \"severity\": \"Major\", \"confidence\": 80}";
    private static Harness H() => new(Page, "ThisInspectionItem", "ItemId", "ThisInspectionItem");

    [Fact]
    public void Every_function_compiles() { var h = H(); Assert.True(h.FunctionsResult.IsSuccess, string.Join("\n", h.FunctionsResult.Errors.Select(e => e.ToString()))); }

    [Fact]
    public void The_page_formulas_are_the_canvas_formulas_plus_the_two_record_lookups()
    {
        var canvas = new CanvasSource(CanvasSource.AppDir).Definitions().Select(d => d.Name).ToList();
        var page = Page.Definitions().Select(d => d.Name).ToList();
        Assert.Equal(canvas.Concat(new[] { "ItemId", "ThisInspectionItem" }).OrderBy(x => x), page.OrderBy(x => x));
        foreach (var d in new CanvasSource(CanvasSource.AppDir).Definitions())
            Assert.Equal(d.Text.Trim(), Page.Definitions().Single(x => x.Name == d.Name).Text.Trim());
    }

    [Fact]
    public void Claude_route_on_the_page_sends_the_same_three_values()
    {
        var h = H();
        h.SetVariable("triageRoute", FormulaValue.New("claude"));
        h.PhotoJsonValue = "\"data:image/jpeg;base64,QUJD\"";
        h.Answer = Good;
        h.Run("btnSuggest", "OnSelect");
        Assert.Equal(("Fire door wedged open with an extinguisher in the east stairwell.", "QUJD", "claude-haiku-5-5"), Assert.Single(h.ClaudeCalls));
    }

    [Fact]
    public void Accept_on_the_page_writes_only_the_AI_columns()
    {
        var h = H();
        h.SetVariable("triageRaw", FormulaValue.New(Good));
        h.Run("btnAccept", "OnSelect");
        var patch = Assert.Single(h.Patches);
        Assert.Equal(5, patch.Count);
        Assert.All(patch.Keys, k => Assert.StartsWith("AI ", k));
    }

    [Fact]
    public void Page_file_is_valid_against_the_official_schema_and_names_the_page_in_the_command()
    {
        var yaml = CanvasSource.YamlReader().Deserialize<object?>(File.ReadAllText(Path.Combine(CanvasSource.EpisodeDir, "tests", "schema", "pa.schema.yaml")));
        var schema = JsonSchema.FromText(CanvasSource.ToJson(yaml)!.ToJsonString().Replace("^([a-zA-Z][a-zA-Z0-9]{1,7})_)?", "^(([a-zA-Z][a-zA-Z0-9]{1,7})_)?"));
        foreach (var f in Page.Documents.Keys)
        {
            var r = schema.Evaluate(CanvasSource.ToJson(Page.Documents[f]), new EvaluationOptions { OutputFormat = OutputFormat.List });
            Assert.True(r.IsValid, f);
        }
        Assert.Contains("{Page: 'Item AI triage'}", File.ReadAllText(Path.Combine(CanvasSource.EpisodeDir, "src", "custompage", "commands.yaml")));
    }
}
