using Microsoft.Xrm.Sdk.Messages;
using Xunit;

namespace EquipmentSync.Tests;

public class ExporterTests
{
    private readonly FakeDataverse dv = new() { ChangeTrackingEnabled = true };
    private readonly SyncState state = new();

    public ExporterTests()
    {
        dv.Seed("CT-0042", "Laptop 14", Equipment.Available);
        dv.Seed("CT-0043", "Laptop 14", Equipment.Available);
        dv.Seed("CT-0107", "Monitor 27", Equipment.Available);
    }

    private async Task<(ExportResult Result, string[] Lines)> Export(bool full = false, int pageSize = 5000)
    {
        var csv = new StringWriter();
        var result = await new ChangeExporter(dv, pageSize).ExportAsync(state, csv, full);
        return (result, csv.ToString().TrimEnd().Split(Environment.NewLine));
    }

    [Fact]
    public async Task First_run_returns_every_row_and_remembers_the_token()
    {
        var (result, lines) = await Export();
        Assert.Equal(new[] { "asset_tag,status,change", "CT-0042,Available,new_or_updated", "CT-0043,Available,new_or_updated", "CT-0107,Available,new_or_updated" }, lines);
        Assert.True(result.FullSync);
        Assert.Equal(dv.CurrentToken, state.DataToken);
        Assert.Equal(3, state.Tags.Count);
    }

    [Fact]
    public async Task Next_run_returns_only_what_changed()
    {
        await Export();
        var previous = state.DataToken;
        dv.DeskSetsStatus("CT-0043", Equipment.OnLoan);

        var (result, lines) = await Export();

        Assert.Equal(new[] { "asset_tag,status,change", "CT-0043,On loan,new_or_updated" }, lines);
        Assert.False(result.FullSync);
        Assert.Equal(previous, dv.Requests.OfType<RetrieveEntityChangesRequest>().Last().DataVersion);
        Assert.NotEqual(previous, state.DataToken);
    }

    [Fact]
    public async Task A_deleted_row_comes_back_as_an_id_and_the_state_supplies_the_tag()
    {
        await Export();
        dv.DeleteRow("CT-0107");

        var (result, lines) = await Export();

        Assert.Equal(new[] { "asset_tag,status,change", "CT-0107,,deleted" }, lines);
        Assert.Equal(1, result.Deleted);
        Assert.DoesNotContain("CT-0107", state.Tags.Values);
    }

    [Fact]
    public async Task A_row_created_and_deleted_between_runs_is_counted_not_exported()
    {
        await Export();
        dv.Seed("CT-0999", "Temp", Equipment.Available);
        dv.DeleteRow("CT-0999");

        var (result, lines) = await Export();

        Assert.Single(lines); // header only
        Assert.Equal(1, result.UnknownDeleted);
    }

    [Fact]
    public async Task No_changes_writes_just_the_header_and_keeps_going()
    {
        await Export();
        var (result, lines) = await Export();
        Assert.Single(lines);
        Assert.Equal(0, result.NewOrUpdated);
    }

    [Fact]
    public async Task Pages_are_followed_with_the_paging_cookie_and_the_token_moves_only_at_the_end()
    {
        dv.Seed("CT-0108", "Monitor 24", Equipment.Available);
        dv.Seed("CT-0311", "Phone", Equipment.InRepair);

        var (result, lines) = await Export(pageSize: 2);

        Assert.Equal(3, result.Pages);
        Assert.Equal(6, lines.Length); // header + 5
        var requests = dv.Requests.OfType<RetrieveEntityChangesRequest>().ToList();
        Assert.Equal(3, requests.Count);                     // the fake rejects a page without the previous page's cookie
        Assert.Equal("page2", requests[^1].PageInfo.PagingCookie);
        Assert.Equal(dv.CurrentToken, state.DataToken);
    }

    [Fact]
    public async Task An_expired_token_stops_with_advice_and_leaves_the_state_alone()
    {
        await Export();
        var token = state.DataToken!;
        dv.ExpiredTokens.Add(token);

        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() => Export());

        Assert.Contains("--full", ex.Message);
        Assert.Equal(token, state.DataToken);
    }

    [Fact]
    public async Task Full_resends_everything_and_rebuilds_the_tag_map()
    {
        await Export();
        dv.ExpiredTokens.Add(state.DataToken!);
        state.Tags[Guid.NewGuid()] = "CT-STALE";

        var (result, lines) = await Export(full: true);

        Assert.True(result.FullSync);
        Assert.Equal(4, lines.Length);
        Assert.DoesNotContain("CT-STALE", state.Tags.Values);
        Assert.Null(dv.Requests.OfType<RetrieveEntityChangesRequest>().Last().DataVersion);
    }

    [Fact]
    public void State_survives_a_save_and_load()
    {
        var path = Path.Combine(Path.GetTempPath(), $"equipmentsync-{Guid.NewGuid():N}.json");
        try
        {
            var s = new SyncState { DataToken = "42!fake", LastRun = new DateTimeOffset(2026, 11, 30, 9, 0, 0, TimeSpan.Zero) };
            s.Tags[Guid.Empty] = "CT-0042";
            s.Save(path);
            var loaded = SyncState.Load(path);
            Assert.Equal(("42!fake", "CT-0042"), (loaded.DataToken, loaded.Tags[Guid.Empty]));
            Assert.Null(SyncState.Load(path + ".missing").DataToken);
        }
        finally { File.Delete(path); }
    }
}
