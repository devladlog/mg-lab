using System.Text.RegularExpressions;
using Xunit;

namespace ContosoInspections.Canvas.Tests;

/// <summary>
/// What the app shows and allows offline, and how it lays out. The sync itself is Power Apps' offline-first feature (a Dataverse
/// offline profile on the phone); these tests cover our formulas around it, with the Connection signal set by the test.
/// </summary>
public class OfflineResponsiveTests
{
    private static readonly CanvasSource App = SourceTests.AppSource;
    private static Harness NewHarness() => SourceTests.NewHarness();
    private static string AllSource() => string.Join("\n", Directory.GetFiles(CanvasSource.AppDir, "*.yaml").Select(File.ReadAllText));

    [Fact]
    public void The_offline_banner_shows_only_without_a_connection_and_is_a_polite_live_region()
    {
        var h = NewHarness();
        Assert.False(h.Bool(App.Formula("lblOffline", "Visible")));
        h.SetConnection(false, "NotConnected");
        Assert.True(h.Bool(App.Formula("lblOffline", "Visible")));
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
    public void The_sync_icon_appears_only_in_an_offline_capable_player_and_opens_the_sync_status_page()
    {
        var h = NewHarness();
        Assert.True(h.Bool(App.Formula("icoSync", "Visible")));
        h.SetHost(offlineEnabled: false); // e.g. the browser: Learn says canvas apps in a browser can't run offline
        Assert.False(h.Bool(App.Formula("icoSync", "Visible")));
        h.Run("icoSync", "OnSelect");
        Assert.Equal(new[] { "ShowHostInfo(OfflineSync)" }, h.Calls);
    }

    [Fact]
    public void Creating_and_editing_work_without_a_connection()
    {
        var h = NewHarness();
        h.SetConnection(false, "NotConnected");
        h.SetControl("drpSite", ("Selected", h.SiteRow("CWN-01")));
        h.Run("btnStart", "OnSelect");
        Assert.Equal("CWN-01-20261130-AD-001", h.Text("selectedInspection.Reference"));
        h.PickText("drpSeverity", "Minor");
        h.SetControl("txtFindingTitle", ("Text", Microsoft.PowerFx.Types.FormulaValue.New("Wet floor")));
        h.Run("btnSave", "OnSelect");
        Assert.Equal("Wet floor", Harness.Field(h.FindingRow("Wet floor"), "cin_title"));
    }

    [Fact]
    public void No_write_button_depends_on_the_connection()
    {
        foreach (var name in new[] { "btnStart", "btnSave", "btnSubmit", "btnAddFinding", "btnResolve" })
            foreach (var (_, f) in App.Controls[name].Properties)
                Assert.DoesNotContain("Connection", f);
        foreach (var d in App.Definitions()) Assert.DoesNotContain("Connection", d.Text);
    }

    [Fact]
    public void The_app_uses_no_flows_no_SaveData_and_no_LoadData()
    {
        // Learn (mobile offline limitations): Power Automate flows aren't supported offline; Dataverse offline-first replaces SaveData/LoadData.
        var all = AllSource();
        Assert.DoesNotMatch(@"\.Run\(", all);
        Assert.DoesNotMatch(@"\b(SaveData|LoadData|ClearData)\s*\(", all);
    }

    [Fact]
    public void Galleries_are_sorted_because_rows_can_come_in_another_order_offline()
    {
        foreach (var g in new[] { "galInspections", "galFindings" })
            Assert.StartsWith("=Sort(", App.Controls[g].Properties["Items"].TrimStart());
    }

    // ---- responsive ---------------------------------------------------------------------------------------------------------

    [Theory]
    [InlineData(780, 1688, 1)]   // a phone held upright, in the phone-layout units Learn describes
    [InlineData(1688, 780, 2)]   // the same phone sideways: wide enough for Medium
    [InlineData(2048, 1536, 3)]  // a tablet
    public void The_screen_size_follows_the_breakpoints(int width, int height, int size)
    {
        var h = NewHarness();
        h.SetDevice(width, height);
        Assert.Equal(size, h.SizeOf("InspectionScreen"));
    }

    [Fact]
    public void The_inspection_screen_has_one_column_on_a_phone_and_two_panes_when_wide()
    {
        var h = NewHarness();
        var direction = App.Formula("conInspectionBody", "LayoutDirection");
        h.SetDevice(780, 1688);
        Assert.Equal("Vertical", h.Text(direction));
        h.SetDevice(1688, 780);
        Assert.Equal("Horizontal", h.Text(direction));
    }

    [Fact]
    public void A_screen_is_never_narrower_than_the_device_nor_the_design_size()
    {
        var h = NewHarness();
        h.SetDevice(780, 1688);
        Assert.Equal(780m, h.ScreenWidth);
        h.SetDevice(400, 700); // smaller than the phone-portrait design size: Learn's formula keeps the design width
        Assert.Equal(640m, h.ScreenWidth);
    }

    [Fact]
    public void The_app_declares_Learns_phone_breakpoints_and_no_scale_to_fit_dependency()
    {
        Assert.Equal("=[1200, 1800, 2400]", App.AppProperties["SizeBreakpoints"]);
        Assert.DoesNotContain("ScaleToFit", AllSource());
    }
}
