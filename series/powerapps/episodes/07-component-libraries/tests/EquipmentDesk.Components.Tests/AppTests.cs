using Microsoft.PowerFx.Types;
using Xunit;

namespace EquipmentDesk.Components.Tests;

/// <summary>The Equipment Desk app using the library: the return flow through ConfirmDialog, and the moved colour rule.</summary>
public class AppTests
{
    private static readonly CanvasSource App = SourceTests.AppSource;
    private static Harness NewHarness() => SourceTests.NewHarness();

    private static Harness TapReturnedOn(string tag)
    {
        var h = NewHarness();
        h.SetThisItem(h.OpenLoan(tag));
        h.Run("btnReturn", "OnSelect");
        return h;
    }

    [Fact]
    public void Returned_on_a_row_opens_the_dialog_and_changes_nothing_yet()
    {
        var h = NewHarness();
        Assert.False(((BooleanValue)h.InstanceValue("dlgReturn", "Visible")).Value);

        h = TapReturnedOn("CT-0043");
        Assert.True(((BooleanValue)h.InstanceValue("dlgReturn", "Visible")).Value);
        Assert.Equal("CT-0043 Laptop 14 from alex.demo@contoso.com is marked as returned today and the device becomes available again.",
            ((StringValue)h.Inside("dlgReturn", "lblDialogMessage", "Text")).Value);
        Assert.Equal("", Harness.Field(h.LoanRow("CT-0043"), "contoso_returnedon"));
        Assert.Empty(h.Calls);
    }

    [Fact]
    public void Confirm_closes_the_loan_frees_the_device_and_closes_the_dialog()
    {
        var h = TapReturnedOn("CT-0043");
        Assert.Equal(1m, h.Number("OverdueCount"));

        h.Tap("dlgReturn", "btnDialogConfirm");

        Assert.Equal("2026-11-30", Harness.Field(h.LoanRow("CT-0043"), "contoso_returnedon"));
        Assert.Equal("Available", Harness.Field(h.DeviceRow("CT-0043"), "contoso_status"));
        Assert.Equal(new[] { "dlgReturn.OnConfirm", "Notify(Success): CT-0043 is back and available" }, h.Calls);
        Assert.False(((BooleanValue)h.InstanceValue("dlgReturn", "Visible")).Value);
        h.Recalc();
        Assert.Equal(0m, h.Number("OverdueCount"));
        Assert.Equal("Nothing overdue", h.Text(App.Formula("lblSummary", "Text")));
        Assert.Equal("#107C10FF", h.Color(App.Formula("lblSummary", "Color")));
        var open = (TableValue)h.Eval(App.Formula("galLoans", "Items"));
        Assert.DoesNotContain("CT-0043", open.Rows.Select(r => Harness.Field((RecordValue)r.Value.GetField("contoso_equipmentid"), "contoso_assettag")));
    }

    [Theory]
    [InlineData("btnDialogCancel")]
    [InlineData("recScrim")]
    public void Cancel_or_a_tap_outside_changes_nothing(string control)
    {
        var h = TapReturnedOn("CT-0043");
        h.Tap("dlgReturn", control);
        Assert.Equal("", Harness.Field(h.LoanRow("CT-0043"), "contoso_returnedon"));
        Assert.Equal("OnLoan", Harness.Field(h.DeviceRow("CT-0043"), "contoso_status"));
        Assert.Equal(new[] { "dlgReturn.OnCancel" }, h.Calls);
        Assert.False(((BooleanValue)h.InstanceValue("dlgReturn", "Visible")).Value);
    }

    [Fact]
    public void A_user_who_cannot_write_loans_gets_the_error_and_the_device_stays_on_loan()
    {
        var h = TapReturnedOn("CT-0107");
        h.MakeReadOnly("Loans", "You don't have Write privilege on Loan");
        h.Tap("dlgReturn", "btnDialogConfirm");
        Assert.Equal("OnLoan", Harness.Field(h.DeviceRow("CT-0107"), "contoso_status"));
        Assert.Equal(new[] { "dlgReturn.OnConfirm", "Notify(Error): Couldn't mark it as returned: You don't have Write privilege on Loan" }, h.Calls);
        Assert.False(((BooleanValue)h.InstanceValue("dlgReturn", "Visible")).Value);
    }

    [Fact]
    public void If_only_the_device_update_fails_the_app_says_so_instead_of_pretending()
    {
        var h = TapReturnedOn("CT-0107");
        h.MakeReadOnly("Equipment", "You don't have Write privilege on Equipment");
        h.Tap("dlgReturn", "btnDialogConfirm");
        Assert.Equal("2026-11-30", Harness.Field(h.LoanRow("CT-0107"), "contoso_returnedon"));
        Assert.Equal("OnLoan", Harness.Field(h.DeviceRow("CT-0107"), "contoso_status"));
        Assert.Equal("Notify(Warning): Loan closed, but the device status wasn't updated: You don't have Write privilege on Equipment", h.Calls[1]);
    }

    [Fact]
    public void StateColor_left_App_Formulas_and_every_colour_now_comes_from_the_library()
    {
        Assert.DoesNotContain(App.Definitions(), d => d.Name == "StateColor");
        var uses = App.Controls.Values.SelectMany(c => c.Properties.Values).Where(f => f.Contains("StateColor(")).ToList();
        Assert.NotEmpty(uses);
        Assert.All(uses, f => Assert.Contains("deskRules.StateColor(", f));
    }

    [Theory]
    [InlineData("CT-0043", "#A80000FF")] // overdue since 16 Nov
    [InlineData("CT-0107", "#8A5A00FF")] // due Wed 2 Dec: Tue 1 Dec is a holiday, so 1 working day away -> due soon
    [InlineData("CT-0108", "#323130FF")] // due 18 Dec
    public void Gallery_rows_get_their_colour_from_deskRules(string tag, string hex)
    {
        var h = NewHarness();
        h.SetThisItem(h.OpenLoan(tag));
        Assert.Equal(hex, h.Color(App.Formula("lblLoanDetail", "Color")));
    }
}
