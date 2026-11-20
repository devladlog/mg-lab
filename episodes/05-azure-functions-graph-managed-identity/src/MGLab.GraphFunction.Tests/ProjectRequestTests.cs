using System.Text.Json;
using Microsoft.Kiota.Abstractions.Serialization;
using Xunit;

namespace MGLab.GraphFunction.Tests;

public class ProjectRequestTests
{
    [Fact]
    public void Maps_kiota_untyped_values_from_graph()
    {
        var fields = new Dictionary<string, object?>
        {
            ["Title"] = new UntypedString("Vendor invoice OCR"),
            ["Requester"] = new UntypedString("Jordan Lee"),
            ["Department"] = new UntypedString("HR"),
            ["Budget"] = new UntypedDouble(15300),
            ["RequestStatus"] = new UntypedString("Done"),
            ["DueDate"] = new UntypedString("2026-12-07T08:00:00Z"),
        };

        var r = ProjectRequest.FromFields(fields);

        Assert.Equal(new ProjectRequest("Vendor invoice OCR", "Jordan Lee", "HR", 15300m, "Done", new DateOnly(2026, 12, 7)), r);
    }

    [Fact]
    public void Maps_json_elements()
    {
        var json = JsonDocument.Parse("""{"Title":"Leave request flow","Budget":7250,"DueDate":"2026-12-16T00:00:00Z"}""").RootElement;
        var fields = json.EnumerateObject().ToDictionary(p => p.Name, p => (object?)p.Value.Clone());

        var r = ProjectRequest.FromFields(fields);

        Assert.Equal("Leave request flow", r.Title);
        Assert.Equal(7250m, r.Budget);
        Assert.Equal(new DateOnly(2026, 12, 16), r.DueDate);
        Assert.Null(r.Department);
    }

    [Fact]
    public void Missing_fields_are_null_and_title_has_a_fallback()
    {
        var r = ProjectRequest.FromFields(new Dictionary<string, object?> { ["Budget"] = new UntypedNull() });
        Assert.Equal("(untitled)", r.Title);
        Assert.Null(r.Budget);
        Assert.Null(r.DueDate);
    }
}
