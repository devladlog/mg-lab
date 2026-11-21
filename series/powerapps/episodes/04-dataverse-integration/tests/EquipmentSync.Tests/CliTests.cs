using Xunit;

namespace EquipmentSync.Tests;

/// <summary>The command line, end to end against the fake: setup, import, a desk change, export.</summary>
public class CliTests
{
    private readonly StringWriter output = new(), error = new();

    private Task<int> Run(FakeDataverse dv, params string[] args) => Cli.RunAsync(args, output, error, () => dv);

    [Fact]
    public async Task Dry_run_prints_the_upserts_without_connecting()
    {
        var code = await Cli.RunAsync(["import", CsvTests.SamplePath, "--dry-run"], output, error, () => throw new Exception("must not connect"));

        Assert.Equal(2, code); // rejected rows -> non-zero, so a scheduler notices
        Assert.Contains("Upsert contoso_equipment(contoso_assettag='CT-0311') contoso_name=Phone, contoso_category=415000002, contoso_serialnumber=SN-PH-0311, contoso_purchasedate=2025-06-30, contoso_status=415000002", output.ToString());
        Assert.Contains("9 rows to upsert in 1 batches of up to 10, 3 rejected.", output.ToString());
        Assert.Contains("line 13 CT-0513: rejected, duplicate of line 9", error.ToString());
    }

    [Fact]
    public async Task Setup_import_and_export_work_together()
    {
        var dv = new FakeDataverse { PollsUntilActive = 1 };
        var dir = Directory.CreateTempSubdirectory("equipmentsync-");
        try
        {
            Assert.Equal(0, await Run(dv, "setup", "--enable-change-tracking"));
            Assert.Equal(2, await Run(dv, "import", CsvTests.SamplePath));
            Assert.Contains("created 9, updated 0, failed 0, rejected 3 (2 ExecuteMultiple requests)", output.ToString());

            var statePath = Path.Combine(dir.FullName, "state.json");
            var first = Path.Combine(dir.FullName, "first.csv");
            Assert.Equal(0, await Run(dv, "export", statePath, first));
            Assert.Equal(10, File.ReadAllLines(first).Length);

            dv.DeskSetsStatus("CT-0043", Equipment.OnLoan);
            var second = Path.Combine(dir.FullName, "second.csv");
            Assert.Equal(0, await Run(dv, "export", statePath, second));
            Assert.Equal(new[] { "asset_tag,status,change", "CT-0043,On loan,new_or_updated" }, File.ReadAllLines(second));
            Assert.Contains("changes: 1 new or updated, 0 deleted (0 unknown), 1 page(s)", output.ToString());
        }
        finally { dir.Delete(recursive: true); }
    }

    [Fact]
    public async Task Setup_without_the_flag_stops_before_enabling_change_tracking()
    {
        var dv = new FakeDataverse { PollsUntilActive = 1 };
        Assert.Equal(1, await Run(dv, "setup"));
        Assert.Contains("--enable-change-tracking", error.ToString());
        Assert.False(dv.ChangeTrackingEnabled);
    }

    [Fact]
    public async Task Unknown_command_prints_usage()
    {
        Assert.Equal(1, await Run(new FakeDataverse(), "sync"));
        Assert.StartsWith("usage: EquipmentSync", error.ToString());
    }
}
