using System.Text.RegularExpressions;
using Xunit;

namespace ContosoInspections.Canvas.Tests;

/// <summary>
/// Source lints. A lint reads the formulas, it doesn't run a service: the delegation lint can say "this uses something Learn lists
/// as not delegable to Dataverse", it can't say "Studio shows no blue underline". Studio's delegation warnings are the proof.
/// </summary>
public class LintTests
{
    private static readonly CanvasSource App = SourceTests.AppSource;

    // ---- delegation ------------------------------------------------------------------------------------------------------

    /// <summary>Learn (Connect to Dataverse, delegable operations): not delegable, or only partly, on Dataverse.</summary>
    private static readonly Regex NotDelegable = new(
        @"\b(Search|Distinct|GroupBy|AddColumns|DropColumns|RenameColumns|Len|Trim|TrimEnds|ForAll|FirstN|LastN|Last|Concat|Text|Value|Average|Sum|Min|Max|Abs|Round|Mid|Left|Right|Lower|Upper|Substitute|Replace)\s*\(",
        RegexOptions.Compiled);

    [Fact]
    public void Gallery_items_use_only_delegable_functions()
    {
        foreach (var g in App.Controls.Values.Where(c => c.Type == "Gallery"))
            Assert.False(NotDelegable.IsMatch(g.Properties["Items"]), $"{g.Name}.Items uses a function Learn lists as not delegable");
    }

    [Fact]
    public void Named_formulas_that_read_tables_use_only_delegable_functions()
    {
        foreach (var d in App.Definitions().Where(d => d.Kind == CanvasSource.DefinitionKind.NamedFormula))
            Assert.False(NotDelegable.IsMatch(d.Expression), $"{d.Name} uses a function Learn lists as not delegable");
    }

    [Fact]
    public void Queries_inside_UDFs_use_only_delegable_functions_in_their_Filter_calls()
    {
        // Only the data-source expressions: the UDFs also do text work (Trim, Len) on values, which is fine.
        foreach (var d in App.Definitions().Where(d => d.Kind != CanvasSource.DefinitionKind.NamedFormula))
            foreach (Match m in Regex.Matches(d.Text, @"\bFilter\(\s*\w+\s*,([^;]*?)\)\s*\)"))
                Assert.DoesNotMatch(@"\b(Search|Len|Trim|Lower|Upper|Mid|Left|Right|Text|Value)\s*\(", m.Groups[1].Value);
    }

    [Fact]
    public void No_gallery_pulls_a_whole_table_without_a_filter_or_a_sort()
    {
        foreach (var g in App.Controls.Values.Where(c => c.Type == "Gallery"))
            Assert.Matches(@"Filter\(", g.Properties["Items"]);
    }

    // ---- touch and accessibility ---------------------------------------------------------------------------------------

    private static readonly string[] Interactive = ["Classic/Button", "Classic/TextInput", "Classic/Dropdown", "Classic/DatePicker", "Classic/Toggle", "Camera", "Gallery"];

    private static decimal HeightOf(CanvasSource.ControlInfo c)
    {
        var raw = c.Properties.GetValueOrDefault("Height") ?? c.Properties.GetValueOrDefault("TemplateSize") ?? "=0";
        var text = CanvasSource.Strip(raw).Trim();
        return text == "TapTarget" ? 88m : decimal.Parse(text, System.Globalization.CultureInfo.InvariantCulture);
    }

    [Fact]
    public void Every_interactive_control_has_an_AccessibleLabel()
    {
        foreach (var c in App.Controls.Values.Where(c => Interactive.Contains(c.Type)))
            Assert.True(c.Properties.ContainsKey("AccessibleLabel"), $"{c.Name} ({c.Type}) has no AccessibleLabel");
        foreach (var c in App.Controls.Values.Where(c => c.Type == "Classic/Icon" && c.Properties.ContainsKey("OnSelect")))
            Assert.True(c.Properties.ContainsKey("AccessibleLabel"), $"{c.Name} is tappable but has no AccessibleLabel");
    }

    [Fact]
    public void Every_interactive_control_is_a_touch_target_of_at_least_88_units_44_pixels()
    {
        // Learn (build responsive apps): phone-layout apps use coordinates that are effectively double, so 88 units = 44 effective pixels.
        foreach (var c in App.Controls.Values.Where(c => Interactive.Contains(c.Type)))
            Assert.True(HeightOf(c) >= 88m, $"{c.Name} is {HeightOf(c)} high");
    }

    [Fact]
    public void No_control_sets_a_TabIndex_above_zero_and_interactive_controls_are_reachable()
    {
        // Learn (create accessible canvas apps): don't set TabIndex greater than zero; use 0 (reachable) or -1 (not). The screen's
        // control order is the tab order, so the file order below is what a keyboard or switch user gets.
        foreach (var c in App.Controls.Values.Where(c => c.Properties.ContainsKey("TabIndex")))
            Assert.Contains(CanvasSource.Strip(c.Properties["TabIndex"]), new[] { "0", "-1" });
        foreach (var c in App.Controls.Values.Where(c => Interactive.Contains(c.Type) && c.Type != "Gallery"))
            Assert.Equal("=0", c.Properties.GetValueOrDefault("TabIndex", "=0"));
    }

    [Fact]
    public void Errors_and_banners_are_live_regions_and_text_not_only_colour()
    {
        foreach (var name in new[] { "lblOffline", "lblProblem", "lblWho", "lblDecision" })
            Assert.Equal("=Live.Polite", App.Controls[name].Properties["Live"]);
        // Status is written out with a leading mark, severity and open/resolved are words.
        Assert.Contains("\"● \"", App.Controls["lblMeta"].Properties["Text"]);
        Assert.Contains("resolved", App.Controls["lblItemMeta"].Properties["Text"]);
        Assert.Contains("\"✕ \"", App.Controls["lblMeta"].Properties["Text"]);
    }

    [Fact]
    public void The_screen_title_is_a_heading_and_decorative_icons_have_no_label()
    {
        foreach (var title in new[] { "lblListTitle", "lblNewTitle", "lblInspectionTitle", "lblItemScreenTitle" })
            Assert.Equal("=TextRole.Heading1", App.Controls[title].Properties["Role"]);
        Assert.False(App.Controls["icoOpen"].Properties.ContainsKey("AccessibleLabel")); // the row is the target
    }

    // ---- contrast (WCAG 1.4.3, 4.5:1) ---------------------------------------------------------------------------------------

    private static readonly Regex Rgba = new(@"RGBA\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*[\d.]+\s*\)");

    private static double Luminance((int R, int G, int B) c)
    {
        static double Lin(int v) { var s = v / 255.0; return s <= 0.03928 ? s / 12.92 : Math.Pow((s + 0.055) / 1.055, 2.4); }
        return 0.2126 * Lin(c.R) + 0.7152 * Lin(c.G) + 0.0722 * Lin(c.B);
    }

    public static double Ratio((int, int, int) a, (int, int, int) b)
    {
        var (x, y) = (Luminance(a), Luminance(b));
        return (Math.Max(x, y) + 0.05) / (Math.Min(x, y) + 0.05);
    }

    private static List<(int R, int G, int B)> Colours(string? formula) =>
        formula is null ? [] : Rgba.Matches(formula).Select(m => (int.Parse(m.Groups[1].Value), int.Parse(m.Groups[2].Value), int.Parse(m.Groups[3].Value))).ToList();

    [Fact]
    public void Text_colours_have_at_least_4_5_to_1_against_their_background()
    {
        var checkedPairs = 0;
        foreach (var c in App.Controls.Values)
        {
            var text = Colours(c.Properties.GetValueOrDefault("Color"));
            if (text.Count == 0) continue;
            var screenFill = Colours(App.ScreenProperties[c.Owner].GetValueOrDefault("Fill")).First();
            var fills = Colours(c.Properties.GetValueOrDefault("Fill"));
            // If(cond, a, b) in both Color and Fill: pair them in order (chips: blue fill + white text, white fill + blue text).
            var pairs = fills.Count == text.Count ? text.Zip(fills) : text.Select(t => (t, fills.Count > 0 ? fills[0] : screenFill));
            foreach (var (t, f) in pairs)
            {
                checkedPairs++;
                Assert.True(Ratio(t, f) >= 4.5, $"{c.Name}: {t} on {f} is {Ratio(t, f):0.0}:1");
            }
        }
        Assert.True(checkedPairs >= 10, $"only {checkedPairs} colour pairs were checked");
    }

    [Fact]
    public void Contrast_helper_matches_known_values()
    {
        Assert.Equal(21.0, Ratio((0, 0, 0), (255, 255, 255)), 1);
        Assert.Equal(1.0, Ratio((10, 20, 30), (10, 20, 30)), 3);
    }

    // ---- structure -----------------------------------------------------------------------------------------------------------

    [Fact]
    public void Formulas_do_not_use_hash_comments_which_are_not_Power_Fx()
    {
        foreach (var c in App.Controls.Values)
            foreach (var (p, f) in c.Properties)
                Assert.DoesNotMatch(@"(?m)^\s*#", f);
        Assert.DoesNotMatch(@"(?m)^\s*#", App.AppProperties["Formulas"]);
    }

    [Fact]
    public void The_UDFs_never_name_a_screen_so_they_cannot_form_a_cycle_with_the_screens()
    {
        foreach (var d in App.Definitions().Where(d => d.Kind != CanvasSource.DefinitionKind.NamedFormula))
            foreach (var s in Harness.ScreenNames) Assert.DoesNotContain(s, d.Text);
    }

    [Fact]
    public void Behavior_UDFs_report_success_as_a_boolean_and_screens_navigate_on_true()
    {
        foreach (var name in new[] { "StartInspection", "AddItem", "ResolveItem", "SubmitInspection" })
            Assert.Matches($@"{name}\([^)]*\): Boolean = \{{", App.Definitions().First(d => d.Name == name).Text);
        Assert.StartsWith("=If(StartInspection(", App.Controls["btnStart"].Properties["OnSelect"]);
        Assert.StartsWith("=If(AddItem(", App.Controls["btnSave"].Properties["OnSelect"]);
        Assert.StartsWith("=If(SubmitInspection(", App.Controls["btnSubmit"].Properties["OnSelect"]);
    }
}
