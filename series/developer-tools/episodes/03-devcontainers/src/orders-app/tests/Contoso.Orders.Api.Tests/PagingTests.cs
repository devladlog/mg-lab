using Contoso.Orders.Api;

namespace Contoso.Orders.Api.Tests;

public class PagingTests
{
    [Theory]
    [InlineData(null, null, 1, 50)]   // defaults
    [InlineData(3, 20, 3, 20)]
    [InlineData(1, 500, 1, 100)]      // clamped to the maximum
    [InlineData(1, 0, 1, 1)]          // clamped to the minimum
    public void Normalize_applies_defaults_and_limits(int? page, int? size, int expectedPage, int expectedSize)
    {
        var result = Paging.Normalize(page, size);
        Assert.Equal((expectedPage, expectedSize), result);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    public void Normalize_rejects_pages_below_one(int page) => Assert.Null(Paging.Normalize(page, 10));

    [Fact]
    public void Last_page_holds_the_remainder()
    {
        var catalog = OrderCatalog.Seed(237);
        var last = catalog.GetPage(5, 50);
        Assert.Equal(37, last.Items.Count);
        Assert.Equal(5, last.TotalPages);
        Assert.Equal(201, last.Items[0].Id);
    }

    [Fact]
    public void Page_past_the_end_is_empty_not_an_error()
    {
        var page = OrderCatalog.Seed(10).GetPage(3, 50);
        Assert.Empty(page.Items);
        Assert.Equal(10, page.Total);
    }

    [Fact]
    public void Seed_is_deterministic()
    {
        Assert.Equal(OrderCatalog.Seed(20).GetPage(1, 20).Items, OrderCatalog.Seed(20).GetPage(1, 20).Items);
    }
}
