using NUnit.Framework;

namespace Contoso.Pricing.Tests
{
    [TestFixture]
    public class QuoteSerializerTests
    {
        [Test]
        public void Reads_the_json_the_queue_already_holds()
        {
            var quote = QuoteSerializer.FromJson("{\"customerId\":\"C-1\",\"total\":\"125.50\",\"tier\":\"gold\"}");
            Assert.AreEqual("C-1", quote.CustomerId);
            Assert.AreEqual(125.50m, quote.Total);
            Assert.AreEqual(DealerTier.Gold, quote.Tier);
        }
    }
}
