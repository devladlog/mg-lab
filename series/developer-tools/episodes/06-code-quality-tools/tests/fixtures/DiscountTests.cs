namespace Contoso.Orders.Api.Tests;

public class DiscountTests
{
    [Fact]
    public void Codes_change_the_total_and_unknown_codes_are_rejected()
    {
        Assert.Equal(100m, Discounts.Apply(100m, null));
        Assert.Equal(90m, Discounts.Apply(100m, "welcome10"));
        Assert.Equal(0m, Discounts.Apply(3m, "FREESHIP"));
        Assert.Throws<ArgumentException>(() => Discounts.Apply(100m, "NOPE"));
    }
}
