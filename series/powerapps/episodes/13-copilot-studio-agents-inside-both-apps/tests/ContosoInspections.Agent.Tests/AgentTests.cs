using Json.Schema;
using Microsoft.PowerFx.Types;
using Xunit;

namespace ContosoInspections.Agent.Tests;

public class FormulaTests
{
    private static readonly CanvasSource Source = new(CanvasSource.AppDir);
    private static Harness H() => new(Source);

    [Fact]
    public void Every_function_compiles() { var h = H(); Assert.True(h.FunctionsResult.IsSuccess, string.Join("\n", h.FunctionsResult.Errors.Select(e => e.ToString()))); }

    [Theory]
    [InlineData("INS-00003", "CWN-01", "About inspection INS-00003 at site CWN-01. ")]
    [InlineData("INS-00003", "", "About inspection INS-00003. ")]
    [InlineData("", "CWN-01", "")]
    public void Context_names_the_inspection_and_site(string number, string site, string expected) =>
        Assert.Equal(expected, H().Text($"AgentContext(\"{number}\", \"{site}\")"));

    [Fact]
    public void Message_is_context_then_trimmed_question() =>
        Assert.Equal("About inspection INS-00003 at site CWN-01. Which items are open?", H().Text("BuildAgentMessage(\"INS-00003\", \"CWN-01\", \"   Which items are open?  \")"));

    [Fact]
    public void Message_never_exceeds_500_characters_and_keeps_the_context()
    {
        var h = H();
        var msg = h.Text("BuildAgentMessage(\"INS-00003\", \"CWN-01\", Concatenate(\"x\", \"" + new string('y', 800) + "\"))");
        Assert.Equal(500, msg.Length);
        Assert.StartsWith("About inspection INS-00003 at site CWN-01. ", msg);
    }

    [Theory]
    [InlineData("", false, false)]
    [InlineData("hi", false, false)]
    [InlineData("  ab ", false, false)]
    [InlineData("What is open?", false, true)]
    [InlineData("What is open?", true, false)]
    public void Ask_needs_three_characters_and_no_call_in_flight(string q, bool busy, bool expected) =>
        Assert.Equal(expected, H().Bool($"CanAskAgent(\"{q}\", {busy.ToString().ToLowerInvariant()})"));

    [Fact]
    public void Blank_reply_becomes_a_hint_to_carry_on_by_hand() =>
        Assert.Equal("The agent did not answer. Try again, or carry on by hand.", H().Text("CleanAgentReply(\"   \")"));

    [Fact]
    public void Long_reply_is_capped_at_1500() =>
        Assert.Equal(1500, H().Text("CleanAgentReply(Concatenate(\"a\", \"" + new string('b', 2000) + "\"))").Length);

    [Theory]
    [InlineData("Finding created: Fire door on INS-00003.", true)]
    [InlineData("  Finding created: x", true)]
    [InlineData("A Major or Critical finding needs notes of at least 10 characters. Nothing was written.", false)]
    [InlineData("Nothing was written.", false)]
    public void Only_the_flow_confirmation_counts_as_a_created_finding(string reply, bool expected) =>
        Assert.Equal(expected, H().Bool($"AgentCreatedFinding(\"{reply}\")"));

    [Fact]
    public void Named_formulas_have_the_agreed_values()
    {
        var h = H();
        Assert.Equal("cin_InspectionAssistant", h.Text("AgentName"));
        Assert.Equal(500m, ((DecimalValue)h.Eval("AgentMaxQuestion")).Value);
        Assert.Equal(1500m, ((DecimalValue)h.Eval("AgentMaxReply")).Value);
    }

    [Fact]
    public void No_name_clashes_with_the_field_app_of_episode_11()
    {
        var ep11 = new CanvasSource(Path.Combine(CanvasSource.EpisodeDir, "..", "11-build-a-canvas-app-from-start-to-end", "src", "app", "Src"));
        var mine = Source.Definitions().Select(d => d.Name).ToHashSet();
        Assert.Empty(ep11.Definitions().Select(d => d.Name).Where(mine.Contains));
        Assert.Empty(Source.Controls.Keys.Intersect(ep11.Controls.Keys));
    }
}

public class ScreenTests
{
    private static Harness H() => new(new CanvasSource(CanvasSource.AppDir));

    [Fact]
    public void Ask_button_sends_context_and_question_to_the_named_agent_and_shows_the_cleaned_answer()
    {
        var h = H();
        h.AgentAnswer = "  Two items are open: Fire door and Extinguisher tag.  ";
        h.Run("btnAsk", "OnSelect");
        var call = Assert.Single(h.AgentCalls);
        Assert.Equal("cin_InspectionAssistant", call.Agent);
        Assert.Equal("About inspection INS-00003 at site CWN-01. Which items are still open?", call.Message);
        Assert.Equal("Two items are open: Fire door and Extinguisher tag.", h.Text("agentReply"));
        Assert.False(h.Bool("agentBusy"));
        Assert.DoesNotContain(h.Calls, c => c.StartsWith("Refresh"));
    }

    [Fact]
    public void A_created_finding_refreshes_the_items()
    {
        var h = H();
        h.AgentAnswer = "Finding created: Fire door on INS-00003. Add a photo in the field app for a Major or Critical finding.";
        h.Run("btnAsk", "OnSelect");
        Assert.Contains("Refresh(Inspection items)", h.Calls);
    }

    [Fact]
    public void A_failed_call_tells_the_inspector_and_leaves_the_app_working()
    {
        var h = H();
        h.AgentError = "no Copilot Credits";
        h.Run("btnAsk", "OnSelect");
        Assert.Contains(h.Calls, c => c.StartsWith("Notify(Error): The assistant could not answer: no Copilot Credits"));
        Assert.Equal("The agent did not answer. Try again, or carry on by hand.", h.Text("agentReply"));
        Assert.False(h.Bool("agentBusy"));
        Assert.DoesNotContain(h.Calls, c => c.StartsWith("Refresh"));
    }

    [Fact]
    public void Button_is_disabled_while_busy_or_without_a_question()
    {
        var h = H();
        Assert.Equal("Edit", h.Run("btnAsk", "DisplayMode"));
        h.SetVariable("agentBusy", FormulaValue.New(true));
        Assert.Equal("Disabled", h.Run("btnAsk", "DisplayMode"));
        h.SetVariable("agentBusy", FormulaValue.New(false));
        h.SetVariable("txtAsk", FormulaValue.NewRecordFromFields(new NamedValue("Text", FormulaValue.New("ab"))));
        Assert.Equal("Disabled", h.Run("btnAsk", "DisplayMode"));
    }

    [Fact]
    public void Back_button_goes_back_and_the_reply_is_a_live_region()
    {
        var h = H();
        h.Run("btnBackAgent", "OnSelect");
        Assert.Contains("Back()", h.Calls);
        Assert.Equal("Polite", h.Run("lblAgentReply", "Live"));
    }
}

public class SourceTests
{
    private static readonly CanvasSource Source = new(CanvasSource.AppDir);

    public static IEnumerable<object[]> Files() => Source.Documents.Keys.Select(f => new object[] { f });

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
    public void The_agent_is_called_in_exactly_one_place_and_only_inside_IfError()
    {
        var hits = Source.Controls.Values.SelectMany(c => c.Properties.Select(p => (c.Name, p.Key, p.Value))).Where(x => x.Value.Contains("ExecuteCopilotAsyncV2")).ToList();
        var hit = Assert.Single(hits);
        Assert.Equal("btnAsk", hit.Name);
        Assert.Contains("IfError(", hit.Value);
    }

    [Fact]
    public void Nothing_secret_is_sent_to_the_agent()
    {
        var all = string.Join("\n", Source.Documents.Keys.Select(k => File.ReadAllText(Path.Combine(CanvasSource.AppDir, k))));
        Assert.DoesNotContain("Reviewer notes", all);
        Assert.DoesNotContain("Photo", all.Replace("add a photo", ""));
    }

    [Fact]
    public void Interactive_controls_have_labels_and_touch_size()
    {
        foreach (var c in Source.Controls.Values.Where(c => c.Type is "Classic/Button" or "Classic/TextInput"))
        {
            Assert.True(c.Properties.ContainsKey("AccessibleLabel"), c.Name);
            Assert.DoesNotContain(c.Properties.GetValueOrDefault("TabIndex") ?? "=0", new[] { "=1", "=2", "=3" });
        }
        Assert.Equal("=88", Source.Controls["btnAsk"].Properties["Height"]);
    }

    [Fact]
    public void No_hash_comments_inside_formulas() =>
        Assert.DoesNotContain(Source.Controls.Values.SelectMany(c => c.Properties.Values), v => v.Contains("# "));
}
