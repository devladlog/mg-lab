using Microsoft.PowerFx.Types;
using Xunit;

namespace EquipmentDesk.Components.Tests;

/// <summary>The three library components, run through their instances in the app and on the library test screen.</summary>
public class ComponentTests
{
    private static Harness NewHarness() => SourceTests.NewHarness();

    // ---- DeskHeader ----------------------------------------------------------------------------------------------

    [Fact]
    public void A_fresh_DeskHeader_shows_the_default_title_and_no_back_arrow()
    {
        var h = NewHarness();
        Assert.Equal("Equipment Desk", ((StringValue)h.InsideDefaults("DeskHeader", "lblHeaderTitle", "Text")).Value);
        Assert.False(((BooleanValue)h.InsideDefaults("DeskHeader", "icoBack", "Visible")).Value);
        Assert.Equal(32m, ((DecimalValue)h.InsideDefaults("DeskHeader", "lblHeaderTitle", "X")).Value);
        Assert.Equal("#005A9EFF", Harness.Hex(((ColorValue)h.Eval(SourceTests.LibrarySource.Components["DeskHeader"].CustomProperties["Accent"].Default![1..])).Value));
    }

    [Fact]
    public void On_the_Loans_screen_the_header_has_a_back_arrow_and_moves_the_title()
    {
        var h = NewHarness();
        Assert.Equal("Open loans", ((StringValue)h.Inside("hdrLoans", "lblHeaderTitle", "Text")).Value);
        Assert.True(((BooleanValue)h.Inside("hdrLoans", "icoBack", "Visible")).Value);
        Assert.Equal(112m, ((DecimalValue)h.Inside("hdrLoans", "lblHeaderTitle", "X")).Value);
    }

    [Fact]
    public void Tapping_back_raises_OnBack_and_the_app_decides_what_back_means()
    {
        var h = NewHarness();
        h.Tap("hdrLoans", "icoBack");
        Assert.Equal(new[] { "hdrLoans.OnBack", "Back()" }, h.Calls);

        var t = NewHarness(); // the library's test screen handles the same event differently
        t.Tap("hdrTest", "icoBack");
        Assert.Equal("OnBack", t.Text("lastEvent"));
        Assert.DoesNotContain("Back()", t.Calls);
    }

    // ---- ConfirmDialog ---------------------------------------------------------------------------------------------

    [Fact]
    public void The_return_dialog_uses_its_own_texts_and_a_non_destructive_button()
    {
        var h = NewHarness();
        Assert.Equal("Mark as returned?", ((StringValue)h.Inside("dlgReturn", "lblDialogTitle", "Text")).Value);
        Assert.Equal("Mark returned", ((StringValue)h.Inside("dlgReturn", "btnDialogConfirm", "Text")).Value);
        Assert.Equal("#005A9EFF", Harness.Hex(((ColorValue)h.Inside("dlgReturn", "btnDialogConfirm", "Fill")).Value));
    }

    [Fact]
    public void A_destructive_dialog_paints_confirm_red_and_defaults_apply_when_the_app_sets_nothing()
    {
        var h = NewHarness();
        Assert.Equal("#A80000FF", Harness.Hex(((ColorValue)h.Inside("dlgTest", "btnDialogConfirm", "Fill")).Value));
        Assert.Equal("Confirm", ((StringValue)h.InsideDefaults("ConfirmDialog", "btnDialogConfirm", "Text")).Value);
        Assert.Equal("Are you sure?", ((StringValue)h.InsideDefaults("ConfirmDialog", "lblDialogTitle", "Text")).Value);
    }

    [Theory]
    [InlineData("btnDialogCancel", "OnCancel")]
    [InlineData("recScrim", "OnCancel")]
    [InlineData("btnDialogConfirm", "OnConfirm")]
    public void Each_button_raises_its_event_on_the_test_screen(string control, string evt)
    {
        var h = NewHarness();
        h.Eval("Set(showDialog, true)");
        h.Tap("dlgTest", control);
        Assert.Equal(evt, h.Text("lastEvent"));
        Assert.False(h.Bool("showDialog"));
        Assert.Equal(new[] { $"dlgTest.{evt}" }, h.Calls);
    }

    // ---- DeskRules -------------------------------------------------------------------------------------------------

    [Theory]
    [InlineData("Overdue", "#A80000FF")]
    [InlineData("Due soon", "#8A5A00FF")]
    [InlineData("Returned", "#107C10FF")]
    [InlineData("On loan", "#323130FF")]
    [InlineData("anything else", "#323130FF")]
    public void StateColor_gives_the_same_colours_as_the_episode_3_UDF(string state, string hex)
    {
        // Episode 3's StateColor: RGBA(168,0,0) overdue, (138,90,0) due soon, (16,124,16) returned, (50,49,48) default.
        var h = NewHarness();
        Assert.Equal(hex, h.Color($"deskRules.StateColor(\"{state}\")"));
    }

    [Theory]
    [InlineData("CT-0042", true)]
    [InlineData(" ct-0042 ", true)]
    [InlineData("CT-42", false)]
    [InlineData("CT-00421", false)]
    [InlineData("XCT-0042", false)]
    [InlineData("CT 0042", false)]
    [InlineData("", false)]
    public void TagIsValid_accepts_a_whole_asset_tag_only(string tag, bool valid)
    {
        // Learn (IsMatch): Complete is the default "on Power Apps", Contains everywhere else. Without ^...$ this test
        // failed here for CT-00421 and XCT-0042 (the open-source engine is "outside Power Apps"). See the next test.
        var h = NewHarness();
        Assert.Equal(valid, h.Bool($"deskRules.TagIsValid(\"{tag}\")"));
    }

    [Fact]
    public void Without_anchors_the_same_pattern_matches_inside_longer_text_outside_Power_Apps()
    {
        var h = NewHarness();
        Assert.True(h.Bool("IsMatch(\"XCT-00421\", \"CT-\\d{4}\")"));      // Contains: what we hit first
        Assert.False(h.Bool("IsMatch(\"XCT-00421\", \"^CT-\\d{4}$\")"));   // anchored: same answer in every host
        Assert.Contains("^CT-\\d{4}$", SourceTests.LibrarySource.Components["DeskRules"].Properties["TagIsValid"]);
    }

    [Fact]
    public void The_library_test_screen_shows_the_functions_working()
    {
        var h = NewHarness();
        Assert.Equal("Tag check works", h.Text(SourceTests.LibrarySource.Formula("lblTagCheck", "Text")));
        Assert.Equal("#A80000FF", h.Color(SourceTests.LibrarySource.Formula("lblOverdueSwatch", "Color")));
        Assert.Equal("No event yet", h.Text(SourceTests.LibrarySource.Formula("lblLastEvent", "Text")));
    }
}
