using System;

namespace Contoso.Pricing
{
    public static class DiscountCalculator
    {
        public static decimal Rate(DealerTier tier)
        {
            switch (tier)
            {
                case DealerTier.Silver: return 0.03m;
                case DealerTier.Gold: return 0.05m;
                default: return 0m;
            }
        }

        public static decimal Apply(decimal total, DealerTier tier)
        {
            if (total < 0) throw new ArgumentOutOfRangeException("total");
            return Math.Round(total * (1m - Rate(tier)), 2);
        }
    }
}
