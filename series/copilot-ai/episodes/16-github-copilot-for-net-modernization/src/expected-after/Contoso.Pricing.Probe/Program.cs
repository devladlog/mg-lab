using Contoso.Pricing;

// Lab probe: reads one list price from the price list database.
//   PRICING_CONN="Data Source=...;Initial Catalog=contoso_pricing;User ID=...;Password=..."  (typed off camera)
//   dotnet run -- BIKE-100
var connection = Environment.GetEnvironmentVariable("PRICING_CONN");
if (string.IsNullOrWhiteSpace(connection) || args.Length != 1)
{
    Console.Error.WriteLine("usage: set PRICING_CONN, then: dotnet run -- <sku>");
    return 2;
}

try
{
    var price = new PriceListRepository(connection).GetListPrice(args[0]);
    Console.WriteLine(price is null ? $"{args[0]}: not in the price list" : $"{args[0]}: {price:0.00}");
    return 0;
}
catch (Exception ex)
{
    Console.Error.WriteLine($"{ex.GetType().Name}: {ex.Message}");
    return 1;
}
