using Microsoft.PowerFx.Types;
using Xunit;

namespace EquipmentDesk.Mobile.Tests;

/// <summary>Screen size, orientation and the one-screen/two-pane layout.</summary>
public class ResponsiveTests
{
    private static readonly CanvasSource App = SourceTests.AppSource;
    private static Harness NewHarness() => SourceTests.NewHarness();

    private static bool Visible(Harness h, string control) => h.Bool(App.Formula(control, "Visible"));

    private static void Select(Harness h, string tag) => h.Eval($"Set(selectedLoan, LookUp(Loans, IsBlank('Returned on') && Equipment.'Asset tag' = \"{tag}\"))");

    [Fact]
    public void Breakpoints_are_Learns_phone_defaults_written_out()
    {
        // Learn: tablet/web apps default to [600, 900, 1200]; phone apps to [1200, 1800, 2400] (doubled coordinates).
        var h = NewHarness();
        var bps = ((TableValue)h.Eval(CanvasSource.Strip(App.AppProperties["SizeBreakpoints"]))).Rows
            .Select(r => ((DecimalValue)r.Value.GetField("Value")).Value);
        Assert.Equal(new[] { 1200m, 1800m, 2400m }, bps);
    }

    [Fact]
    public void Learns_landscape_example_needs_the_orientation_formulas()
    {
        // Learn's example: a phone app designed at 640 x 1136, turned to landscape, reports App 1136 x 640.
        var h = NewHarness();
        h.SetDevice(1136, 640, screenWidthFormula: "Max(App.Width, App.DesignWidth)", screenHeightFormula: "Max(App.Height, App.DesignHeight)");
        Assert.Equal((1136m, 1136m), (h.ScreenWidth, h.ScreenHeight)); // the default: 1136 tall on a 640 tall device = scrolling

        h.SetDevice(1136, 640); // our screen's formulas
        Assert.Equal((1136m, 640m), (h.ScreenWidth, h.ScreenHeight));

        h.SetDevice(640, 1136);
        Assert.Equal((640m, 1136m), (h.ScreenWidth, h.ScreenHeight));
    }

    // App.Width x App.Height examples in phone-layout units (not device specs): upright phone, phone on its side,
    // tablet upright, tablet on its side, a desktop browser window.
    [Theory]
    [InlineData(780, 1688, 1)]
    [InlineData(1688, 780, 2)]
    [InlineData(1640, 2360, 2)]
    [InlineData(2360, 1640, 3)]
    [InlineData(2880, 1600, 4)]
    [InlineData(500, 900, 1)] // smaller than the design width: the screen stays 640 wide and the user scrolls
    public void Screen_size_follows_the_screen_width_and_the_breakpoints(int width, int height, int size)
    {
        var h = NewHarness();
        h.SetDevice(width, height);
        Assert.Equal(size, h.ScreenSize);
        Assert.Equal(size, (int)h.Number("LoansScreen.Size"));
    }

    [Fact]
    public void Upright_phone_shows_the_list_then_the_loan_instead_of_the_list()
    {
        var h = NewHarness();
        h.SetDevice(780, 1688);
        Assert.True(Visible(h, "conList"));
        Assert.False(Visible(h, "conDetail"));
        Assert.Equal("Open loans", ((StringValue)h.InstanceValue("hdrLoans", "Title")).Value);

        h.SetThisItem(h.OpenLoan("CT-0043"));
        h.Run("galLoans", "OnSelect"); // tap the row

        Assert.False(Visible(h, "conList"));
        Assert.True(Visible(h, "conDetail"));
        Assert.Equal("CT-0043", ((StringValue)h.InstanceValue("hdrLoans", "Title")).Value);
        Assert.Equal("CT-0043 · Laptop 14", h.Text(App.Formula("lblDetailTitle", "Text")));
        Assert.Equal("Overdue · due Monday 16 November", h.Text(App.Formula("lblDetailDue", "Text")));
        Assert.Equal("#A80000FF", h.Color(App.Formula("lblDetailDue", "Color")));
    }

    [Fact]
    public void On_an_upright_phone_back_first_returns_to_the_list()
    {
        var h = NewHarness();
        h.SetDevice(780, 1688);
        Select(h, "CT-0043");
        h.Tap("hdrLoans", "icoBack");
        Assert.True(h.Eval("selectedLoan") is BlankValue);
        Assert.DoesNotContain("Back()", h.Calls);

        h.Tap("hdrLoans", "icoBack"); // list showing now: back leaves the screen
        Assert.Contains("Back()", h.Calls);
    }

    [Fact]
    public void Turning_the_phone_sideways_shows_list_and_loan_side_by_side()
    {
        var h = NewHarness();
        h.SetDevice(780, 1688);
        Select(h, "CT-0107");
        Assert.False(Visible(h, "conList"));

        h.SetDevice(1688, 780);
        Assert.True(Visible(h, "conList"));
        Assert.True(Visible(h, "conDetail"));
        Assert.Equal("Open loans", ((StringValue)h.InstanceValue("hdrLoans", "Title")).Value);
        Assert.Equal("CT-0107 · Monitor 27", h.Text(App.Formula("lblDetailTitle", "Text")));

        h.Tap("hdrLoans", "icoBack"); // side by side: back leaves the screen, the selection doesn't matter
        Assert.Contains("Back()", h.Calls);
    }

    [Fact]
    public void Wide_screen_without_a_selection_says_so()
    {
        var h = NewHarness();
        h.SetDevice(2360, 1640);
        Assert.True(Visible(h, "conDetail"));
        Assert.True(Visible(h, "lblNoSelection"));
        Assert.False(Visible(h, "btnReturn"));
        Assert.False(Visible(h, "btnRemind"));
    }

    [Fact]
    public void The_two_panes_split_two_to_three_and_the_list_keeps_a_phone_width()
    {
        Assert.Equal("=2", App.Controls["conList"].Properties["FillPortions"]);
        Assert.Equal("=3", App.Controls["conDetail"].Properties["FillPortions"]);
        Assert.Equal("=560", App.Controls["conList"].Properties["LayoutMinWidth"]);
        Assert.Equal("GroupContainer", App.Controls["conBody"].Type);
    }
}
