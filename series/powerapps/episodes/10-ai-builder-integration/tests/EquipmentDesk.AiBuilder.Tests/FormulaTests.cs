using Xunit;

namespace EquipmentDesk.AiBuilder.Tests;

/// <summary>The rules around the prompt: what goes in, what comes out, and what the app does with it.</summary>
public class FormulaTests
{
    internal static readonly CanvasSource App = new(CanvasSource.AppDir);
    private static Harness NewHarness() => new(App);

    internal static string Json(string condition, object confidence, string summary = "A summary.") =>
        $"{{\"condition\": \"{condition}\", \"confidence\": {confidence}, \"summary\": \"{summary}\"}}";

    // ---- input --------------------------------------------------------------------------------------------------

    [Theory]
    [InlineData("", false)]
    [InlineData("   ", false)]
    [InlineData("ok", false)]
    [InlineData("1234567", false)]
    [InlineData("  1234567  ", false)]   // 7 characters once trimmed
    [InlineData("12345678", true)]
    [InlineData("  Cracked screen  ", true)]
    public void Only_notes_with_something_in_them_are_sent_to_the_prompt(string note, bool expected)
    {
        Assert.Equal(expected, NewHarness().Bool($"CanTriage(\"{note}\")"));
    }

    [Fact]
    public void The_input_is_trimmed_and_capped_at_600_characters()
    {
        var h = NewHarness();
        Assert.Equal("Cracked screen", h.FnText("TriageInput", "   Cracked screen \n"));
        var sent = h.FnText("TriageInput", new string('x', 5000));
        Assert.Equal(600, sent.Length);
        Assert.Equal(600m, h.Number("TriageMaxChars"));
    }

    // ---- reading the answer ---------------------------------------------------------------------------------------

    [Theory]
    [InlineData("ok")]
    [InlineData("damaged")]
    [InlineData("missing_accessory")]
    [InlineData("needs_repair")]
    public void Each_allowed_condition_comes_through(string condition)
    {
        Assert.Equal(condition, NewHarness().FnText("TriageCondition", Json(condition, 0.9)));
    }

    [Theory]
    [InlineData("DAMAGED", "damaged")]
    [InlineData(" Needs_Repair ", "needs_repair")]
    public void Case_and_spaces_in_the_condition_are_forgiven(string sent, string expected)
    {
        Assert.Equal(expected, NewHarness().FnText("TriageCondition", Json(sent, 0.9)));
    }

    [Theory]
    [InlineData("retired")]                  // a real status value, but not one the prompt may return
    [InlineData("stolen")]
    [InlineData("")]
    [InlineData("ok, but damaged")]
    public void A_condition_outside_the_allow_list_is_unclear(string condition)
    {
        Assert.Equal("unclear", NewHarness().FnText("TriageCondition", Json(condition, 0.99)));
    }

    [Theory]
    [InlineData("")]
    [InlineData("The device is damaged.")]
    [InlineData("{\"condition\": \"ok\"")]                       // cut off
    [InlineData("[\"ok\"]")]                                     // an array, not an object
    [InlineData("{\"status\": \"ok\", \"confidence\": 0.9}")]   // wrong key
    [InlineData("{\"condition\": 5, \"confidence\": 0.9}")]     // wrong type
    [InlineData("null")]
    public void Anything_that_is_not_the_expected_object_is_unclear_and_never_an_error(string raw)
    {
        var h = NewHarness();
        Assert.Equal("unclear", h.FnText("TriageCondition", raw));
        Assert.Equal("", h.FnText("TriageSummary", raw));
    }

    [Theory]
    [InlineData("```json\n{0}\n```")]
    [InlineData("```\n{0}\n```")]
    [InlineData("  {0}  ")]
    public void Markdown_fences_around_the_JSON_are_stripped(string wrapper)
    {
        var raw = wrapper.Replace("{0}", Json("damaged", 0.9, "Cracked screen."));
        var h = NewHarness();
        Assert.Equal("damaged", h.FnText("TriageCondition", raw));
        Assert.Equal("Cracked screen.", h.FnText("TriageSummary", raw));
    }

    [Fact]
    public void Text_before_the_JSON_is_not_guessed_at()
    {
        // The prompt says "nothing else"; if the model chats anyway the app doesn't hunt for braces.
        Assert.Equal("unclear", NewHarness().FnText("TriageCondition", "Sure! " + Json("ok", 0.9)));
    }

    // ---- confidence -----------------------------------------------------------------------------------------------

    [Theory]
    [InlineData("0.92", 0.92)]
    [InlineData("1", 1)]
    [InlineData("7", 1)]        // out of range is clamped
    [InlineData("-3", 0)]
    [InlineData("\"0.8\"", 0.8)] // a number in quotes still reads
    [InlineData("\"high\"", 0)]
    public void Confidence_is_a_number_between_0_and_1(string value, double expected)
    {
        var raw = $"{{\"condition\": \"ok\", \"confidence\": {value}, \"summary\": \"s\"}}";
        Assert.Equal((decimal)expected, NewHarness().Number($"TriageConfidence(\"{raw.Replace("\"", "\"\"")}\")"));
    }

    [Theory]
    [InlineData("{\"\"condition\"\": \"\"ok\"\"}")]
    [InlineData("null")]
    [InlineData("not json")]
    [InlineData("{\"\"confidence\"\": null}")]
    public void A_missing_confidence_counts_as_zero_not_one(string raw)
    {
        // Min(1, Blank()) is 1 in Power Fx: the first version of TriageConfidence let a missing confidence through the gate.
        Assert.Equal(0m, NewHarness().Number($"TriageConfidence(\"{raw}\")"));
    }

    [Fact]
    public void An_answer_with_no_confidence_is_unclear_even_when_the_condition_is_fine()
    {
        Assert.Equal("unclear", NewHarness().FnText("TriageCondition", "{\"condition\": \"ok\", \"summary\": \"s\"}"));
    }

    [Theory]
    [InlineData(0.69, "unclear")]
    [InlineData(0.7, "damaged")]
    [InlineData(0.71, "damaged")]
    [InlineData(0.1, "unclear")]
    public void Below_the_confidence_gate_the_answer_is_unclear(double confidence, string expected)
    {
        var h = NewHarness();
        Assert.Equal(0.7m, h.Number("TriageMinConfidence"));
        Assert.Equal(expected, h.FnText("TriageCondition", Json("damaged", confidence)));
    }

    // ---- summary --------------------------------------------------------------------------------------------------

    [Fact]
    public void The_summary_is_one_short_line()
    {
        var h = NewHarness();
        Assert.Equal("Cracked screen.", h.FnText("TriageSummary", Json("damaged", 0.9, "  Cracked screen.  ")));
        Assert.Equal("Line one Line two", h.FnText("TriageSummary", Json("damaged", 0.9, "Line one\\nLine two")));
        var long_ = h.FnText("TriageSummary", Json("damaged", 0.9, new string('a', 500)));
        Assert.Equal(140, long_.Length);
    }

    // ---- what the app does with a condition ----------------------------------------------------------------------

    [Theory]
    [InlineData("ok", "Available", "Looks fine")]
    [InlineData("missing_accessory", "Available", "Missing accessory")]
    [InlineData("damaged", "In repair", "Damaged")]
    [InlineData("needs_repair", "In repair", "Needs repair")]
    [InlineData("unclear", "", "Not sure")]
    public void Each_condition_maps_to_a_status_suggestion_and_a_label(string condition, string status, string label)
    {
        var h = NewHarness();
        Assert.Equal(status, h.FnText("SuggestedStatus", condition));
        Assert.Equal(label, h.FnText("ConditionLabel", condition));
    }

    [Theory]
    [InlineData("retired")]
    [InlineData("on loan")]
    [InlineData("")]
    [InlineData("Retired")]
    public void The_app_never_suggests_Retired_or_On_loan_whatever_the_model_says(string condition)
    {
        var h = NewHarness();
        var suggestion = h.FnText("SuggestedStatus", h.FnText("TriageCondition", Json(condition, 1)));
        Assert.DoesNotContain(suggestion, new[] { "Retired", "On loan" });
        Assert.Equal("", suggestion);
    }
}
