using System.Text.Json;
using System.Text.Json.Serialization;

namespace Contoso.Pricing;

/// <summary>JSON the order queue already contains: camelCase names, enums as text, nulls left out.</summary>
public static class QuoteSerializer
{
    // JsonSerializerDefaults.Web = camelCase names, case-insensitive reading, numbers may be read from strings.
    // Those three are what Newtonsoft.Json did by default and what the queue's old messages rely on.
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        Converters = { new JsonStringEnumConverter() }
    };

    public static string ToJson(Quote quote) => JsonSerializer.Serialize(quote, Options);

    public static Quote? FromJson(string json)
    {
        // Newtonsoft returned null for empty input; System.Text.Json throws. Keep the old contract.
        if (string.IsNullOrWhiteSpace(json)) return null;
        return JsonSerializer.Deserialize<Quote>(json, Options);
    }
}
