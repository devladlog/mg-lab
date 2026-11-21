using System.Text.Json;

namespace Contoso.Pricing;

/// <summary>What a quick find-and-replace of JsonConvert with JsonSerializer produces. Compiles, passes the happy path, and is wrong.</summary>
public static class QuoteSerializer
{
    public static string ToJson(Quote quote) => JsonSerializer.Serialize(quote);

    public static Quote? FromJson(string json) => JsonSerializer.Deserialize<Quote>(json);
}
