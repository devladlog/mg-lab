using Xunit;

namespace EquipmentSync.Tests;

public class CsvTests
{
    internal static string SamplePath => Path.Combine(FindEpisodeDir(), "samples", "asset-register.csv");

    internal static string FindEpisodeDir()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "samples", "asset-register.csv"))) dir = dir.Parent;
        return dir?.FullName ?? throw new DirectoryNotFoundException("episode folder with samples/ not found");
    }

    private static AssetRegisterCsv.ParseResult Parse(string text) => AssetRegisterCsv.Parse(new StringReader(text));
    private const string Header = "asset_tag,name,category,serial_number,purchase_date,status\n";

    [Fact]
    public void The_sample_file_has_nine_good_rows_and_three_rejected()
    {
        using var reader = File.OpenText(SamplePath);
        var result = AssetRegisterCsv.Parse(reader);
        Assert.Equal(9, result.Rows.Count);
        Assert.Equal(new[] { (11, "asset tag 'CT-51' is not like CT-0042"), (12, "purchase date '10/11/2026' is not yyyy-MM-dd"), (13, "duplicate of line 9") },
            result.Rejected.Select(r => (r.Line, r.Message!)));
    }

    [Fact]
    public void A_good_row_is_parsed_and_normalised()
    {
        var row = Parse(Header + "ct-0512,\"Laptop 16, docked\",laptop,SN-1,2026-11-10,IN_SERVICE").Rows.Single();
        Assert.Equal(new AssetRow(2, "CT-0512", "Laptop 16, docked", "laptop", "SN-1", new DateOnly(2026, 11, 10), "in_service"), row);
    }

    [Fact]
    public void Empty_serial_and_date_become_null()
    {
        var row = Parse(Header + "CT-0108,Monitor 24,Monitor,,,in_service").Rows.Single();
        Assert.Null(row.SerialNumber);
        Assert.Null(row.PurchaseDate);
    }

    [Theory]
    [InlineData("CT-0001,Desk lamp,Furniture,,,in_service", "unknown category 'Furniture'")]
    [InlineData("CT-0001,,Laptop,,,in_service", "name is required (max 100 characters)")]
    [InlineData("CT-0001,Laptop,Laptop,,,lost", "unknown status 'lost'")]
    [InlineData("CT-0001,Laptop,Laptop,,", "expected 6 fields, found 5")]
    [InlineData("CT/0001,Laptop,Laptop,,,in_service", "asset tag 'CT/0001' is not like CT-0042")] // '/' breaks key upserts (Learn)
    [InlineData("CT-0001,Laptop,Laptop,,2026-13-01,in_service", "purchase date '2026-13-01' is not yyyy-MM-dd")]
    public void Bad_rows_are_rejected_with_a_reason(string line, string reason)
    {
        var result = Parse(Header + line);
        Assert.Empty(result.Rows);
        Assert.Equal(reason, result.Rejected.Single().Message);
    }

    [Fact]
    public void A_wrong_header_stops_the_import()
    {
        var ex = Assert.Throws<FormatException>(() => Parse("tag,name\nCT-0001,x"));
        Assert.Contains("Expected: asset_tag,name,category", ex.Message);
    }

    [Theory]
    [InlineData("plain", "plain")]
    [InlineData("a,b", "\"a,b\"")]
    [InlineData("say \"hi\"", "\"say \"\"hi\"\"\"")]
    public void Quote_round_trips_through_split(string value, string quoted)
    {
        Assert.Equal(quoted, AssetRegisterCsv.Quote(value));
        Assert.Equal(value, AssetRegisterCsv.SplitLine(quoted).Single());
    }
}
