using System;
using System.Configuration;
using System.Web.Mvc;
using Contoso.Pricing;

namespace Contoso.Orders.Web.Controllers
{
    public class QuotesController : Controller
    {
        // GET /Quotes/Price?sku=BIKE-100&quantity=2&tier=Gold
        public ActionResult Price(string sku, int quantity = 1, DealerTier tier = DealerTier.Standard)
        {
            var repository = new PriceListRepository(ConfigurationManager.ConnectionStrings["PriceDb"].ConnectionString);
            var listPrice = repository.GetListPrice(sku);
            if (listPrice == null)
            {
                return HttpNotFound();
            }

            var quote = new Quote
            {
                CustomerId = User.Identity.Name,
                Total = DiscountCalculator.Apply(listPrice.Value * quantity, tier),
                Tier = tier,
                IssuedUtc = DateTime.UtcNow
            };

            Session["lastQuote"] = quote;
            System.Web.HttpContext.Current.Items["quoted"] = true;
            return Content(QuoteSerializer.ToJson(quote), "application/json");
        }
    }
}
