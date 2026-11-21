using Xunit;

namespace EquipmentDesk.Mobile.Tests;

/// <summary>Scan an asset tag (or type it) to open the loan. The barcode reader's Barcodes table is set by the test.</summary>
public class ScannerTests
{
    private static readonly CanvasSource App = SourceTests.AppSource;
    private static Harness NewHarness() => SourceTests.NewHarness();

    private static string SelectedTag(Harness h) => h.Text("selectedLoan.Equipment.'Asset tag'");

    [Fact]
    public void Scanning_a_tag_with_an_open_loan_opens_it()
    {
        var h = NewHarness();
        h.Scan("CT-0043");
        h.Run("bcrScan", "OnScan");
        Assert.Equal("CT-0043", SelectedTag(h));
        Assert.Equal("alex.demo@contoso.com", h.Text("selectedLoan.'Borrower email'"));
        Assert.True(h.Bool(App.Formula("conDetail", "Visible"))); // upright phone: the loan replaces the list
        Assert.Empty(h.Calls);
    }

    [Theory]
    [InlineData(" ct-0107 ", "CT-0107")]
    [InlineData("ct-0108", "CT-0108")]
    public void Case_and_spaces_from_the_label_dont_matter(string scanned, string tag)
    {
        var h = NewHarness();
        h.Scan(scanned);
        h.Run("bcrScan", "OnScan");
        Assert.Equal(tag, SelectedTag(h));
    }

    [Fact]
    public void A_device_with_no_open_loan_says_so_and_keeps_the_screen_as_it_was()
    {
        var h = NewHarness();
        h.Eval("Set(selectedLoan, LookUp(Loans, Equipment.'Asset tag' = \"CT-0107\" && IsBlank('Returned on')))");
        h.Scan("CT-0042"); // returned on 20 Nov
        h.Run("bcrScan", "OnScan");
        Assert.Equal(new[] { "Notify(Information): CT-0042 has no open loan" }, h.Calls);
        Assert.Equal("CT-0107", SelectedTag(h));
    }

    [Theory]
    [InlineData("https://contoso.com/asset/42")]
    [InlineData("CT-00431")]
    [InlineData("4006381333931")]
    public void A_code_that_isnt_an_asset_tag_is_refused_by_the_library_rule(string scanned)
    {
        var h = NewHarness();
        h.Scan(scanned);
        h.Run("bcrScan", "OnScan");
        Assert.Equal(new[] { $"Notify(Warning): That code isn't an asset tag: {scanned}" }, h.Calls);
        Assert.Equal("", SelectedTag(h));
    }

    [Fact]
    public void With_several_codes_in_one_session_the_first_one_wins()
    {
        var h = NewHarness();
        h.Scan("CT-0108", "CT-0043");
        h.Run("bcrScan", "OnScan");
        Assert.Equal("CT-0108", SelectedTag(h));
    }

    [Fact]
    public void Typing_the_tag_does_the_same_without_a_camera()
    {
        var h = NewHarness();
        h.SetControl("txtFindTag", ("Text", Microsoft.PowerFx.Types.FormulaValue.New("ct-0043")));
        h.Run("txtFindTag", "OnChange");
        Assert.Equal("CT-0043", SelectedTag(h));

        h.SetControl("txtFindTag", ("Text", Microsoft.PowerFx.Types.FormulaValue.New("laptop")));
        h.Run("txtFindTag", "OnChange");
        Assert.Equal("Notify(Warning): Type a tag like CT-0043", h.Calls.Last());
    }

    [Fact]
    public void Scanner_and_text_box_share_one_lookup_and_one_tag_rule()
    {
        foreach (var (control, prop) in new[] { ("bcrScan", "OnScan"), ("txtFindTag", "OnChange") })
        {
            var f = App.Formula(control, prop);
            Assert.Contains("deskRules.TagIsValid(tag)", f);
            Assert.Contains("FindLoan(tag)", f);
        }
        Assert.Contains(App.Definitions(), d => d.Name == "FindLoan" && d.Kind == CanvasSource.DefinitionKind.BehaviorFunction);
    }
}
