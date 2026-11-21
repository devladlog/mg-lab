using System;

namespace Contoso.Pricing
{
    public enum DealerTier
    {
        Standard,
        Silver,
        Gold
    }

    /// <summary>A dealer quote as the order queue stores it.</summary>
    public class Quote
    {
        public string CustomerId { get; set; }
        public decimal Total { get; set; }
        public DealerTier Tier { get; set; }
        public DateTime IssuedUtc { get; set; }
        public string Note { get; set; }
    }
}
