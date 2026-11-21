using Contoso.Pricing;

namespace Pricing.Characterization;

public class DiscountAndConnectionBehaviour
{
    [Theory]
    [InlineData(1299.00, DealerTier.Standard, 1299.00)]
    [InlineData(1299.00, DealerTier.Silver, 1260.03)]
    [InlineData(1299.00, DealerTier.Gold, 1234.05)]
    [InlineData(12.25, DealerTier.Gold, 11.64)]   // 11.6375 rounds to 11.64
    public void Apply_gives_the_same_prices(double total, DealerTier tier, double expected)
    {
        Assert.Equal((decimal)expected, DiscountCalculator.Apply((decimal)total, tier));
    }

    [Fact]
    public void Negative_total_is_rejected_with_the_parameter_name()
    {
        var ex = Assert.Throws<ArgumentOutOfRangeException>(() => DiscountCalculator.Apply(-1m, DealerTier.Gold));
        Assert.Equal("total", ex.ParamName);
    }

    [Fact]
    public void Connection_string_keeps_the_same_keys_and_order()
    {
        var cs = ConnectionStrings.Build("10.50.0.30", "contoso_pricing", "pricing_app", "not-a-real-password");
        Assert.Equal("Data Source=10.50.0.30;Initial Catalog=contoso_pricing;User ID=pricing_app;Password=not-a-real-password;Connect Timeout=15", cs);
    }

#if MODERN
    [Fact]
    public void Lab_helper_trusts_the_server_certificate_and_nothing_else_changes()
    {
        var cs = ConnectionStrings.BuildTrustingServerCertificate("10.50.0.30", "contoso_pricing", "pricing_app", "not-a-real-password");
        Assert.EndsWith(";Trust Server Certificate=True", cs);
        Assert.StartsWith("Data Source=10.50.0.30;Initial Catalog=contoso_pricing;", cs);
    }
#endif
}
