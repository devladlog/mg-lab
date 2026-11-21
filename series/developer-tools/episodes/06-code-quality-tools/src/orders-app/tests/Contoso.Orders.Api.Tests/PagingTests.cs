namespace Contoso.Orders.Api.Tests;

public class PagingTests
{
    [Theory]
    [InlineData(null, null, 1, 50)]
    [InlineData(3, 20, 3, 20)]
    [InlineData(1, 500, 1, 100)]
    [InlineData(1, 0, 1, 1)]
    public void Normalize_applies_defaults_and_limits(int? page, int? size, int expectedPage, int expectedSize)
        => Assert.Equal((expectedPage, expectedSize), Paging.Normalize(page, size));

    [Fact]
    public void Normalize_rejects_pages_below_one() => Assert.Null(Paging.Normalize(0, 10));

    [Fact]
    public void Seed_data_is_deterministic()
    {
        var a = OrdersDb.SeedData(5).Select(o => (o.Customer, o.Total, o.Created));
        var b = OrdersDb.SeedData(5).Select(o => (o.Customer, o.Total, o.Created));
        Assert.Equal(a, b);
    }
}
