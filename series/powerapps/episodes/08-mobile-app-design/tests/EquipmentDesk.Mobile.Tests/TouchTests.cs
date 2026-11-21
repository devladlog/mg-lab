using Xunit;

namespace EquipmentDesk.Mobile.Tests;

/// <summary>
/// Tap targets. Our rule: anything a finger taps is at least TapTarget (88) phone-layout units high. Where 88 comes from:
/// Microsoft's touch guidance calls 44 x 44 effective pixels "touch-optimized", and Learn says phone-layout apps use
/// coordinates that are "effectively double". The rule is ours; the two inputs are Learn's.
/// </summary>
public class TouchTests
{
    private static readonly CanvasSource App = SourceTests.AppSource;
    private static readonly CanvasSource Library = SourceTests.LibrarySource;

    private static readonly string[] InteractiveTypes = ["Classic/Button", "Classic/Toggle", "Classic/TextInput", "BarcodeReader"];

    internal static bool IsInteractive(CanvasSource.ControlInfo c) =>
        InteractiveTypes.Contains(c.Type) || c.Properties.Keys.Any(p => p is "OnSelect" or "OnScan" or "OnChange");

    /// <summary>Controls that are too small to tap. Galleries are judged by row (TemplateSize); full-size layers
    /// (Height relative to Parent, like a dialog scrim) are skipped.</summary>
    internal static IEnumerable<string> TooSmall(Harness h, CanvasSource s, decimal min) =>
        from c in s.Controls.Values
        where IsInteractive(c) && c.Type != "CanvasComponent"
        let prop = c.Type == "Gallery" ? "TemplateSize" : "Height"
        where c.Properties.ContainsKey(prop) && !c.Properties[prop].Contains("Parent.")
        let value = h.Number(CanvasSource.Strip(c.Properties[prop]))
        where value < min
        select $"{c.Name}.{prop} = {value}";

    [Fact]
    public void TapTarget_is_88_phone_layout_units()
    {
        Assert.Equal(88m, SourceTests.NewHarness().Number("TapTarget"));
    }

    [Fact]
    public void Every_tappable_control_on_the_screen_is_at_least_TapTarget_high()
    {
        var h = SourceTests.NewHarness();
        Assert.Empty(TooSmall(h, App, 88));
        // and they all have a height to check (an interactive control without Height would slip through)
        var unchecked_ = App.Controls.Values.Where(c => IsInteractive(c) && c.Type is not ("CanvasComponent" or "Gallery") && !c.Properties.ContainsKey("Height"));
        Assert.Empty(unchecked_.Select(c => c.Name));
    }

    [Fact]
    public void The_library_components_we_use_pass_the_same_rule()
    {
        // DeskHeader's back arrow and ConfirmDialog's buttons were built 88 high in episode 7.
        var h = SourceTests.NewHarness();
        Assert.Empty(TooSmall(h, Library, 88));
    }

    [Fact]
    public void Episode_7s_row_buttons_would_fail_the_rule()
    {
        // Episode 7 had 40-high Send reminder / Returned buttons inside each gallery row. Same check, that snippet:
        var dir = Directory.CreateTempSubdirectory("pa-yaml-");
        try
        {
            File.WriteAllText(Path.Combine(dir.FullName, "Old.pa.yaml"), """
                Screens:
                  OldScreen:
                    Children:
                      - galLoans:
                          Control: Gallery
                          Properties:
                            TemplateSize: =112
                          Children:
                            - btnReturn:
                                Control: Classic/Button
                                Properties:
                                  OnSelect: =Set(returnLoan, ThisItem)
                                  Height: =40
                      - tglOverdueOnly:
                          Control: Classic/Toggle
                          Properties:
                            Height: =40
                """);
            var h = SourceTests.NewHarness();
            Assert.Equal(new[] { "btnReturn.Height = 40", "tglOverdueOnly.Height = 40" }, TooSmall(h, new CanvasSource(dir.FullName), 88).Order());
        }
        finally { dir.Delete(true); }
    }

    [Fact]
    public void Gallery_rows_have_no_buttons_the_whole_row_is_the_target()
    {
        Assert.DoesNotContain(App.Controls.Values, c => c.Parent == "galLoans" && IsInteractive(c));
        Assert.Contains("Set(selectedLoan, ThisItem)", App.Controls["galLoans"].Properties["OnSelect"]);
    }

    [Fact]
    public void Interactive_icons_and_inputs_have_an_accessible_label_and_the_decorative_icon_has_none()
    {
        // Learn (accessible apps): icons used as buttons get an AccessibleLabel; an empty label hides a decorative icon.
        foreach (var c in App.Controls.Values.Where(c => c.Type is "Classic/Icon" or "Classic/TextInput" or "Classic/Toggle" && IsInteractive(c)))
            Assert.True(c.Properties.ContainsKey("AccessibleLabel"), c.Name);
        Assert.False(App.Controls["icoOpen"].Properties.ContainsKey("AccessibleLabel"));
        Assert.False(IsInteractive(App.Controls["icoOpen"]));
    }
}
