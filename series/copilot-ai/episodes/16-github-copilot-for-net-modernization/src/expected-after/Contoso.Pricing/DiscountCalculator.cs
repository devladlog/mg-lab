namespace Contoso.Pricing;

public static class DiscountCalculator
{
    public static decimal Rate(DealerTier tier) => tier switch
    {
        DealerTier.Silver => 0.03m,
        DealerTier.Gold => 0.05m,
        _ => 0m
    };

    public static decimal Apply(decimal total, DealerTier tier)
    {
        if (total < 0) throw new ArgumentOutOfRangeException(nameof(total));
        return Math.Round(total * (1m - Rate(tier)), 2);
    }
}
