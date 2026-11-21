using PowerFxReview;
using Xunit;

namespace PowerFxReview.Tests;

public class ExtractorTests
{
    [Fact]
    public void Reads_app_and_screen_formulas_with_their_path()
    {
        var files = Directory.GetFiles(Samples.Src, "*.pa.yaml");
        var (formulas, screens) = FormulaExtractor.FromFiles(files);

        Assert.Equal(new[] { "ListScreen" }, screens);
        Assert.Equal(15, formulas.Count);
        Assert.Contains(formulas, f => f.Where == "App.StartScreen" && f.Formula == "ListScreen");
        Assert.Contains(formulas, f => f.Where == "ListScreen.galLoans.Items");
        Assert.Contains(formulas, f => f.Where == "ListScreen.OnVisible");
    }

    [Fact]
    public void Multiline_block_scalars_keep_all_lines()
    {
        var (formulas, _) = FormulaExtractor.FromYaml("""
            Screens:
              S1:
                Children:
                  - btn:
                      Control: Button
                      Properties:
                        OnSelect: |
                          =IfError(
                              Patch(T, X, {A: 1}),
                              Notify("x")
                          )
                        Text: ="plain"
            """);
        var onSelect = Assert.Single(formulas, f => f.Property == "OnSelect");
        Assert.StartsWith("IfError(", onSelect.Formula);
        Assert.Contains("Patch(T, X, {A: 1})", onSelect.Formula);
        Assert.True(onSelect.IsBehavior);
        Assert.False(Assert.Single(formulas, f => f.Property == "Text").IsBehavior);
    }

    [Fact]
    public void Values_without_an_equals_sign_are_not_formulas()
    {
        var (formulas, _) = FormulaExtractor.FromYaml("""
            Screens:
              S1:
                Children:
                  - lbl:
                      Control: Label
                      Properties:
                        Text: null
                        Font: Arial
            """);
        Assert.Empty(formulas);
    }

    [Fact]
    public void A_colon_inside_a_single_line_formula_is_not_valid_yaml()
    {
        // Learn, "Power Fx YAML formula grammar": a colon is not allowed anywhere in a single-line formula.
        // A record like {Status: "x"} has to be written as a multiline formula.
        Assert.ThrowsAny<Exception>(() => FormulaExtractor.FromYaml("""
            Screens:
              S1:
                Children:
                  - btn:
                      Control: Button
                      Properties:
                        OnSelect: =Patch(T, X, {Status: "x"})
            """));
    }
}

static class Samples
{
    public static string Root => Path.Combine(AppContext.BaseDirectory, "samples");
    public static string Src => Path.Combine(Root, "Src");
    public static ReviewContext Context() => ReviewContext.Load(Path.Combine(Root, "context.json"));
    public static string Data => File.ReadAllText(Path.Combine(Root, "sample-data.json"));
    public static Reviewer Reviewer() => new(Context(), new[] { "ListScreen" });

    public static FormulaReview Review(string property, string formula) =>
        Reviewer().Review(new FormulaItem("test", "ListScreen", "ctl", property, formula));
}
