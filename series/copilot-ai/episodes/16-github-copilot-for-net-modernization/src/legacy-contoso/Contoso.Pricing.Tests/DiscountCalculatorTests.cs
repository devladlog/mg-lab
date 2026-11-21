using NUnit.Framework;

namespace Contoso.Pricing.Tests
{
    [TestFixture]
    public class DiscountCalculatorTests
    {
        [Test]
        public void Gold_dealers_get_five_percent()
        {
            Assert.AreEqual(1234.05m, DiscountCalculator.Apply(1299.00m, DealerTier.Gold));
        }

        [Test]
        public void Standard_dealers_pay_list_price()
        {
            Assert.AreEqual(1299.00m, DiscountCalculator.Apply(1299.00m, DealerTier.Standard));
        }
    }
}
