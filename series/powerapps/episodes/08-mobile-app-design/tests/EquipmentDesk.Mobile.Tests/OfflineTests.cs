using System.Text.RegularExpressions;
using Microsoft.PowerFx.Types;
using Xunit;

namespace EquipmentDesk.Mobile.Tests;

/// <summary>
/// What the app shows and allows when the phone is offline. The sync itself is Power Apps' offline-first feature
/// (Dataverse offline profile); these tests cover our formulas around it, with the Connection signal set by the test.
/// </summary>
public class OfflineTests
{
    private static readonly CanvasSource App = SourceTests.AppSource;
    private static Harness NewHarness() => SourceTests.NewHarness();

    private static void Select(Harness h, string tag) => h.Eval($"Set(selectedLoan, LookUp(Loans, IsBlank('Returned on') && Equipment.'Asset tag' = \"{tag}\"))");

    [Fact]
    public void The_offline_banner_shows_only_without_a_connection()
    {
        var h = NewHarness();
        Assert.False(h.Bool(App.Formula("lblOffline", "Visible")));
        h.SetConnection(false, "NotConnected");
        Assert.True(h.Bool(App.Formula("lblOffline", "Visible")));
        Assert.Equal("Offline. Changes stay on this phone and sync when you're back online.", h.Text(App.Formula("lblOffline", "Text")));
        Assert.Equal("Polite", h.Text(App.Formula("lblOffline", "Live")));
    }

    [Theory]
    [InlineData("Connected", "Globe")]
    [InlineData("ConnectedPendingUpsync", "GlobeChangesPending")]
    [InlineData("ConnectedRefresh", "GlobeRefresh")]
    [InlineData("NotConnected", "GlobeNotConnected")]
    [InlineData("NotConnectedPendingUpsync", "GlobeChangesPending")]
    [InlineData("NotConnectedSyncError", "GlobeError")]
    [InlineData("ConnectedWithWarning", "GlobeWarning")]
    public void The_sync_icon_follows_Connection_Sync_as_in_Learns_offline_template(string sync, string icon)
    {
        var h = NewHarness();
        h.SetConnection(sync.StartsWith("Connected"), sync);
        Assert.Equal(icon, h.Text(App.Formula("icoSync", "Icon")));
    }

    [Fact]
    public void The_sync_icon_appears_only_in_an_offline_capable_player_and_opens_the_device_status_page()
    {
        var h = NewHarness();
        Assert.True(h.Bool(App.Formula("icoSync", "Visible")));
        h.SetHost(offlineEnabled: false); // e.g. the browser: Learn says canvas apps in a browser can't run offline
        Assert.False(h.Bool(App.Formula("icoSync", "Visible")));
        h.Run("icoSync", "OnSelect");
        Assert.Equal(new[] { "ShowHostInfo(OfflineSync)" }, h.Calls);
    }

    [Fact]
    public void Send_reminder_is_disabled_offline_because_flows_need_a_connection()
    {
        var h = NewHarness();
        Select(h, "CT-0043"); // overdue
        Assert.True(h.Bool(App.Formula("btnRemind", "Visible")));
        Assert.Equal("Edit", h.Text(App.Formula("btnRemind", "DisplayMode")));
        Assert.Equal("Send reminder", h.Text(App.Formula("btnRemind", "Text")));

        h.SetConnection(false, "NotConnected");
        Assert.Equal("Disabled", h.Text(App.Formula("btnRemind", "DisplayMode")));
        Assert.Equal("Send reminder (needs a connection)", h.Text(App.Formula("btnRemind", "Text")));
    }

    [Fact]
    public void While_a_reminder_is_sending_the_button_waits()
    {
        var h = NewHarness();
        Select(h, "CT-0043");
        h.Eval("Set(sendingLoan, selectedLoan.contoso_loanid)");
        Assert.Equal("Sending...", h.Text(App.Formula("btnRemind", "Text")));
        Assert.Equal("Disabled", h.Text(App.Formula("btnRemind", "DisplayMode")));
    }

    [Fact]
    public void Send_reminder_only_shows_for_overdue_loans()
    {
        var h = NewHarness();
        Select(h, "CT-0108"); // due 18 Dec
        Assert.False(h.Bool(App.Formula("btnRemind", "Visible")));
        Assert.True(h.Bool(App.Formula("btnReturn", "Visible")));
    }

    [Fact]
    public void Mark_returned_works_offline_and_closes_the_detail_pane()
    {
        var h = NewHarness();
        h.SetConnection(false, "NotConnected");
        Select(h, "CT-0043");
        h.Run("btnReturn", "OnSelect");
        Assert.True(((BooleanValue)h.InstanceValue("dlgReturn", "Visible")).Value);
        h.Tap("dlgReturn", "btnDialogConfirm");

        Assert.Equal("2026-11-30", Harness.Field(h.LoanRow("CT-0043"), "contoso_returnedon"));
        Assert.Equal("Available", Harness.Field(h.DeviceRow("CT-0043"), "contoso_status"));
        Assert.True(h.Eval("selectedLoan") is BlankValue);
        Assert.True(h.Eval("returnLoan") is BlankValue);
        Assert.Equal("Notify(Success): CT-0043 is back and available", h.Calls.Last());
    }

    [Fact]
    public void A_failed_return_keeps_the_loan_open_on_screen()
    {
        var h = NewHarness();
        Select(h, "CT-0107");
        h.Run("btnReturn", "OnSelect");
        h.MakeReadOnly("Loans", "You don't have Write privilege on Loan");
        h.Tap("dlgReturn", "btnDialogConfirm");
        Assert.False(h.Eval("selectedLoan") is BlankValue); // the user still sees the loan they tried to close
        Assert.True(h.Eval("returnLoan") is BlankValue);
        Assert.StartsWith("Notify(Error): Couldn't mark it as returned", h.Calls.Last());
    }

    // ---- lints from Learn's offline limitations --------------------------------------------------------------------

    private static IEnumerable<(string Where, string Formula)> AllFormulas() =>
        App.Controls.Values.SelectMany(c => c.Properties.Select(p => ($"{c.Name}.{p.Key}", p.Value)))
            .Append(("App.Formulas", App.AppProperties["Formulas"]));

    [Fact]
    public void The_gallery_has_a_sort_order()
    {
        // Learn: rows may come in a different order in an offline-capable app if no sort order is selected.
        Assert.StartsWith("=Sort(", App.Controls["galLoans"].Properties["Items"].TrimStart());
    }

    [Fact]
    public void No_Relate_or_Unrelate_anywhere()
    {
        // Learn: offline-first doesn't support the Relate and Unrelate functions.
        Assert.DoesNotContain(AllFormulas(), f => Regex.IsMatch(f.Formula, @"\b(Relate|Unrelate)\("));
    }

    [Fact]
    public void Every_flow_call_sits_behind_a_Connection_check()
    {
        // Learn: Power Automate flows aren't supported in offline mode.
        var flowCalls = App.Controls.Values.Where(c => c.Properties.Values.Any(v => v.Contains(".Run("))).ToList();
        Assert.Equal(new[] { "btnRemind" }, flowCalls.Select(c => c.Name));
        Assert.All(flowCalls, c => Assert.Contains("Connection.Connected", c.Properties["DisplayMode"]));
    }

    [Fact]
    public void Lookups_in_filters_go_one_level_deep_at_most()
    {
        // Learn: filtering on column lookups is limited to one level of the relationship offline
        // (Loans -> Equipment.'Asset tag' is fine; Loans -> Equipment -> something else isn't).
        var twoLevels = new Regex(@"\bEquipment\.('[^']+'|\w+)\.('[^']+'|\w+)");
        var filters = AllFormulas().Where(f => Regex.IsMatch(f.Formula, @"\b(Filter|LookUp|CountIf)\("));
        Assert.DoesNotContain(filters, f => twoLevels.IsMatch(f.Formula));
    }
}
