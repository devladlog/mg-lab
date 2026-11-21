namespace Contoso.Bikes.Pricing;

/// <summary>Dealer loyalty pricing for Contoso Bikes quotes.</summary>
public static class DiscountCalculator
{
    /// <summary>Loyalty rate by full years as a dealer: 0 years 0%, 1-2 years 5%, 3+ years 10%.</summary>
    public static decimal LoyaltyRate(int years) => years switch
    {
        < 1 => 0m,
        < 3 => 0.05m,
        _ => 0.10m,
    };

    /// <summary>Price after the loyalty discount, rounded to cents.</summary>
    public static decimal LoyaltyPrice(decimal listPrice, int years)
    {
        var discounted = listPrice * (1m - LoyaltyRate(years));
        return Math.Round(discounted, 2);
    }
}
