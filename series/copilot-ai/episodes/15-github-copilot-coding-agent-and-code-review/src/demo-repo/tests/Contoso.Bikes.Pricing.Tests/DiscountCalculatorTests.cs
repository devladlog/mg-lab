using Contoso.Bikes.Pricing;

namespace Contoso.Bikes.Pricing.Tests;

public class DiscountCalculatorTests
{
    [Theory]
    [InlineData(0, 0.00)]
    [InlineData(1, 0.05)]
    [InlineData(2, 0.05)]
    [InlineData(3, 0.10)]
    [InlineData(12, 0.10)]
    public void LoyaltyRate_follows_the_dealer_years(int years, double expected)
    {
        Assert.Equal((decimal)expected, DiscountCalculator.LoyaltyRate(years));
    }

    [Fact]
    public void LoyaltyPrice_new_dealer_pays_list_price()
    {
        Assert.Equal(1299.00m, DiscountCalculator.LoyaltyPrice(1299.00m, 0));
    }

    [Fact]
    public void LoyaltyPrice_applies_five_percent_after_one_year()
    {
        Assert.Equal(1234.05m, DiscountCalculator.LoyaltyPrice(1299.00m, 1));
    }

    [Fact]
    public void LoyaltyPrice_applies_ten_percent_after_three_years()
    {
        Assert.Equal(1169.10m, DiscountCalculator.LoyaltyPrice(1299.00m, 3));
    }
}
