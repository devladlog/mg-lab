using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Messages;
using Xunit;

namespace EquipmentSync.Tests;

public class ImporterTests
{
    private readonly FakeDataverse dv = new();

    public ImporterTests() => dv.ActivateKeyNow();

    private static IReadOnlyList<AssetRow> Sample()
    {
        using var reader = File.OpenText(CsvTests.SamplePath);
        return AssetRegisterCsv.Parse(reader).Rows;
    }

    private static AssetRow Row(string tag, string status = "in_service", string? serial = "SN") =>
        new(2, tag, "Laptop 14", "Laptop", serial, new DateOnly(2025, 3, 14), status);

    [Fact]
    public async Task First_import_creates_every_device_and_gives_new_ones_a_status()
    {
        var report = await new EquipmentImporter(dv).ImportAsync(Sample());

        Assert.Equal(9, report.Count(RowOutcome.Created));
        Assert.Equal(Equipment.Available, dv.StatusOf("CT-0042"));
        Assert.Equal(Equipment.InRepair, dv.StatusOf("CT-0311"));
        Assert.Equal(Equipment.Retired, dv.StatusOf("CT-0400"));
        Assert.Equal("Laptop 16, docked", dv.ByTag("CT-0512")[Equipment.Name]);
        Assert.Equal(2, report.RequestsSent); // one upsert batch, one status batch
    }

    [Fact]
    public async Task Running_it_again_updates_and_sends_no_status_fix_up()
    {
        await new EquipmentImporter(dv).ImportAsync(Sample());
        dv.Requests.Clear();

        var report = await new EquipmentImporter(dv).ImportAsync(Sample());

        Assert.Equal(9, report.Count(RowOutcome.Updated));
        Assert.Equal(1, report.RequestsSent);
        Assert.Equal(9, dv.Rows.Count); // no duplicates: the alternate key found every device
    }

    [Fact]
    public async Task The_nightly_import_does_not_put_a_lent_laptop_back_to_Available()
    {
        await new EquipmentImporter(dv).ImportAsync(Sample());
        dv.DeskSetsStatus("CT-0043", Equipment.OnLoan); // lent in the app (episode 2)

        await new EquipmentImporter(dv).ImportAsync(Sample());

        Assert.Equal(Equipment.OnLoan, dv.StatusOf("CT-0043"));
    }

    [Fact]
    public async Task The_register_still_wins_for_repair_and_retirement()
    {
        await new EquipmentImporter(dv).ImportAsync(Sample());
        dv.DeskSetsStatus("CT-0311", Equipment.Available);

        await new EquipmentImporter(dv).ImportAsync(Sample());

        Assert.Equal(Equipment.InRepair, dv.StatusOf("CT-0311"));
    }

    [Fact]
    public void The_key_goes_in_KeyAttributes_not_in_Attributes()
    {
        var e = EquipmentImporter.ToEntity(Row("CT-0042"));
        Assert.Equal("CT-0042", e.KeyAttributes[Equipment.AssetTag]);
        Assert.False(e.Contains(Equipment.AssetTag));
        Assert.False(e.Contains(Equipment.Status)); // in service: status is the app's business
        Assert.Equal(new DateTime(2025, 3, 14), e[Equipment.PurchaseDate]);
    }

    [Fact]
    public async Task One_bad_row_does_not_sink_the_batch()
    {
        dv.Reject = e => e.KeyAttributes.TryGetValue(Equipment.AssetTag, out var t) && (string)t == "CT-0107" ? "A plug-in rejected this device." : null;

        var report = await new EquipmentImporter(dv).ImportAsync(Sample());

        Assert.Equal(8, report.Count(RowOutcome.Created));
        var failed = report.Results.Single(r => r.Outcome == RowOutcome.Failed);
        Assert.Equal(("CT-0107", "A plug-in rejected this device."), (failed.AssetTag, failed.Message));
        Assert.Equal(8, dv.Rows.Count);
    }

    [Fact]
    public async Task Without_an_active_key_nothing_is_written_and_every_row_says_why()
    {
        var noKey = new FakeDataverse();
        var report = await new EquipmentImporter(noKey).ImportAsync(Sample());

        Assert.All(report.Results, r => Assert.Equal(RowOutcome.Failed, r.Outcome));
        Assert.Contains("not a defined key", report.Results[0].Message);
        Assert.Empty(noKey.Rows);
    }

    [Theory]
    [InlineData(10, 25, 3)]
    [InlineData(100, 25, 1)]
    [InlineData(1, 3, 3)]
    public async Task Rows_are_sent_in_batches(int batchSize, int rows, int expectedUpsertRequests)
    {
        await new EquipmentImporter(dv, batchSize).ImportAsync(Enumerable.Range(1, rows).Select(i => Row($"CT-{i:D4}", "in_repair")).ToList());
        var batches = dv.Requests.OfType<ExecuteMultipleRequest>().ToList();
        Assert.Equal(expectedUpsertRequests, batches.Count);
        Assert.All(batches, b => Assert.True(b.Requests.Count <= batchSize && b.Settings.ContinueOnError && b.Settings.ReturnResponses));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1001)]
    public void Batch_size_must_be_between_1_and_1000(int size) =>
        Assert.Throws<ArgumentOutOfRangeException>(() => new EquipmentImporter(dv, size));

    [Fact]
    public async Task A_failed_status_fix_up_is_reported_on_the_created_row()
    {
        dv.Reject = e => e.Contains(Equipment.Status) && e.KeyAttributes.Count == 0 ? "Status is read-only for this user." : null;

        var report = await new EquipmentImporter(dv).ImportAsync([Row("CT-0900")]);

        var r = report.Results.Single();
        Assert.Equal(RowOutcome.Created, r.Outcome);
        Assert.Equal("created, but status not set: Status is read-only for this user.", r.Message);
    }

    [Fact]
    public async Task An_empty_serial_in_the_register_clears_it_in_Dataverse()
    {
        await new EquipmentImporter(dv).ImportAsync([Row("CT-0901", serial: "SN-OLD")]);
        await new EquipmentImporter(dv).ImportAsync([Row("CT-0901", serial: null)]);
        Assert.Null(dv.ByTag("CT-0901")[Equipment.SerialNumber]);
    }
}
