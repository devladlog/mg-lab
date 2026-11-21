using Microsoft.PowerFx.Types;
using Xunit;

namespace EquipmentDesk.Canvas.Tests;

public class GalleryTests
{
    private static readonly CanvasSource Source = new();
    private readonly Harness h = new(Source);
    private string Items => Source.Formula("galEquipment", "Items");

    private string[] Tags(string search, bool availableOnly)
    {
        h.SetControl("txtSearch", ("Text", FormulaValue.New(search)));
        h.SetControl("tglAvailableOnly", ("Value", FormulaValue.New(availableOnly)));
        return h.Column((TableValue)h.Eval(Items), "contoso_assettag").ToArray();
    }

    [Fact]
    public void Starts_with_available_devices_only_sorted_by_asset_tag() =>
        Assert.Equal(new[] { "CT-0042", "CT-0107", "CT-0108" }, Tags("", availableOnly: true));

    [Fact]
    public void Toggle_off_shows_every_device() =>
        Assert.Equal(new[] { "CT-0042", "CT-0043", "CT-0107", "CT-0108", "CT-0311", "CT-0400" }, Tags("", availableOnly: false));

    [Fact]
    public void Search_matches_the_start_of_the_asset_tag() =>
        Assert.Equal(new[] { "CT-0107", "CT-0108" }, Tags("CT-01", availableOnly: true));

    [Fact]
    public void Search_matches_the_start_of_the_name_case_insensitively() =>
        Assert.Equal(new[] { "CT-0042", "CT-0043" }, Tags("lap", availableOnly: false));

    [Fact]
    public void Search_does_not_match_the_middle_of_a_word()
    {
        // A prefix search by design: "top" is inside "Laptop" but nothing starts with it. (Dataverse can also delegate
        // "in" and Search on text columns; we chose StartsWith because people type asset tags from the start.)
        Assert.Empty(Tags("top", availableOnly: false));
    }

    [Fact]
    public void Gallery_row_shows_tag_name_category_and_status()
    {
        h.Engine.UpdateVariable("ThisItem", h.Device("CT-0043", "Laptop 14", "Laptop", "OnLoan"));
        Assert.Equal("CT-0043 · Laptop 14", ((StringValue)h.Eval(Source.Formula("lblItemTitle", "Text"))).Value);
        Assert.Equal("Laptop · On loan", ((StringValue)h.Eval(Source.Formula("lblItemDetail", "Text"))).Value);
    }

    [Fact]
    public void Tapping_a_row_navigates_to_the_lend_screen()
    {
        h.Eval(Source.Formula("galEquipment", "OnSelect"));
        Assert.Equal(new[] { "Navigate(LendScreen, Cover)" }, h.Calls);
    }

    [Fact]
    public void Open_source_engine_reads_a_second_predicate_that_starts_with_Column_equals_as_a_named_argument()
    {
        // Filter accepts several predicates, but Power Fx 1.8.1 rejects this one, so Items combines them with &&.
        var check = h.Check("Filter(Equipment, StartsWith(Name, txtSearch.Text), Status = 'Status (Equipment)'.Available)");
        Assert.False(check.IsSuccess);
        Assert.Contains(check.Errors, e => e.Message.Contains("Use the And operator"));
    }
}
