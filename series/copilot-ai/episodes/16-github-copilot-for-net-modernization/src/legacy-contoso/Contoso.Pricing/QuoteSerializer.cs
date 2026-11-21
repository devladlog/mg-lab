using Newtonsoft.Json;
using Newtonsoft.Json.Converters;
using Newtonsoft.Json.Serialization;

namespace Contoso.Pricing
{
    /// <summary>JSON the order queue already contains: camelCase names, enums as text, nulls left out.</summary>
    public static class QuoteSerializer
    {
        private static readonly JsonSerializerSettings Settings = new JsonSerializerSettings
        {
            ContractResolver = new CamelCasePropertyNamesContractResolver(),
            NullValueHandling = NullValueHandling.Ignore,
            Converters = { new StringEnumConverter() }
        };

        public static string ToJson(Quote quote)
        {
            return JsonConvert.SerializeObject(quote, Formatting.None, Settings);
        }

        public static Quote FromJson(string json)
        {
            return JsonConvert.DeserializeObject<Quote>(json, Settings);
        }
    }
}
