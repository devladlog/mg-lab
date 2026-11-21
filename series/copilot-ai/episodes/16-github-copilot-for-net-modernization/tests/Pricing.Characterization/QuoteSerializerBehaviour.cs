using Contoso.Pricing;

namespace Pricing.Characterization;

/// <summary>What the order queue and the web app rely on today. Every test here passes on the legacy sources.</summary>
public class QuoteSerializerBehaviour
{
    [Fact]
    public void Reads_camelCase_names_with_numbers_and_enums_as_text()
    {
        var q = QuoteSerializer.FromJson("{\"customerId\":\"C-1\",\"total\":\"125.50\",\"tier\":\"gold\",\"issuedUtc\":\"2026-11-21T10:00:00Z\"}");
        Assert.Equal("C-1", q.CustomerId);
        Assert.Equal(125.50m, q.Total);
        Assert.Equal(DealerTier.Gold, q.Tier);
        Assert.Equal(new DateTime(2026, 11, 21, 10, 0, 0, DateTimeKind.Utc), q.IssuedUtc);
        Assert.Equal(DateTimeKind.Utc, q.IssuedUtc.Kind);
    }

    [Fact]
    public void Reads_names_in_any_casing()
    {
        var q = QuoteSerializer.FromJson("{\"CUSTOMERID\":\"C-2\",\"Total\":10}");
        Assert.Equal("C-2", q.CustomerId);
        Assert.Equal(10m, q.Total);
    }

    [Fact]
    public void Writes_camelCase_names_enums_as_text_and_leaves_nulls_out()
    {
        var json = QuoteSerializer.ToJson(new Quote { CustomerId = "C-3", Total = 99.9m, Tier = DealerTier.Silver, IssuedUtc = new DateTime(2026, 11, 21, 10, 0, 0, DateTimeKind.Utc) });
        Assert.Equal("{\"customerId\":\"C-3\",\"total\":99.9,\"tier\":\"Silver\",\"issuedUtc\":\"2026-11-21T10:00:00Z\"}", json);
    }

    [Fact]
    public void Round_trip_keeps_every_field()
    {
        var original = new Quote { CustomerId = "C-4", Total = 1234.05m, Tier = DealerTier.Gold, IssuedUtc = new DateTime(2026, 1, 2, 3, 4, 5, DateTimeKind.Utc), Note = "net 30" };
        var back = QuoteSerializer.FromJson(QuoteSerializer.ToJson(original));
        Assert.Equal(original.CustomerId, back.CustomerId);
        Assert.Equal(original.Total, back.Total);
        Assert.Equal(original.Tier, back.Tier);
        Assert.Equal(original.IssuedUtc, back.IssuedUtc);
        Assert.Equal(original.Note, back.Note);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("null")]
    public void Empty_or_null_input_gives_null_not_an_exception(string json)
    {
        Assert.Null(QuoteSerializer.FromJson(json));
    }
}
