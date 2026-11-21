using OrderIntake.Core;

namespace OrderIntake.Tests;

public class PricingTests
{
    private static readonly ICatalog Catalog = new InMemoryCatalog();
    private static readonly DateTimeOffset At = new(2026, 11, 21, 10, 0, 0, TimeSpan.Zero);

    private static OrderMessage Msg(params OrderLine[] lines) => new("o-1", "C-1001", lines, At);

    [Fact]
    public void Lines_are_priced_from_the_catalogue()
    {
        var p = Pricing.Price(Msg(new OrderLine("CBL-001", 3), new("KEY-010", 1)), Catalog);
        Assert.Equal(14.70m, p.Lines[0].LineTotal);
        Assert.Equal(64.20m, p.Subtotal);
        Assert.Equal(0m, p.Discount);
        Assert.Equal(64.20m, p.Total);
    }

    [Fact]
    public void Five_percent_off_from_500_euros()
    {
        var p = Pricing.Price(Msg(new OrderLine("MON-270", 2), new("KEY-010", 2)), Catalog); // 439.98 + 99.00
        Assert.Equal(538.98m, p.Subtotal);
        Assert.Equal(26.95m, p.Discount);   // 26.949 rounds to 26.95
        Assert.Equal(512.03m, p.Total);
    }

    [Fact]
    public void Exactly_500_gets_the_discount()
    {
        var catalog = new FixedCatalog(250m);
        var p = Pricing.Price(Msg(new OrderLine("ABC-001", 2)), catalog);
        Assert.Equal(25m, p.Discount);
    }

    [Fact]
    public void Just_below_500_does_not()
    {
        var p = Pricing.Price(Msg(new OrderLine("ABC-001", 1)), new FixedCatalog(499.99m));
        Assert.Equal(0m, p.Discount);
    }

    [Fact]
    public void Unknown_sku_throws_so_the_runtime_retries()
    {
        var ex = Assert.Throws<UnknownSkuException>(() => Pricing.Price(Msg(new OrderLine("ZZZ-999", 1)), Catalog));
        Assert.Equal("ZZZ-999", ex.Sku);
    }

    [Fact]
    public void Order_id_and_timestamp_are_kept()
    {
        var p = Pricing.Price(Msg(new OrderLine("DOC-100", 1)), Catalog);
        Assert.Equal("o-1", p.OrderId);
        Assert.Equal(At, p.ReceivedAt);
    }

    private sealed class FixedCatalog(decimal price) : ICatalog
    {
        public decimal? PriceOf(string sku) => price;
    }
}
