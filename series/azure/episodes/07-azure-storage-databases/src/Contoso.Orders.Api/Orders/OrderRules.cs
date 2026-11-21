using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace Contoso.Orders.Api.Orders;

/// <summary>Same fictional catalogue and rules as episodes 1 and 5.</summary>
public static partial class OrderRules
{
    public const decimal DiscountThreshold = 500m;
    public const decimal DiscountRate = 0.05m;

    public static readonly IReadOnlyDictionary<string, decimal> Catalogue = new Dictionary<string, decimal>
    {
        ["CBL-001"] = 4.90m,    // USB-C cable
        ["DOC-100"] = 129.00m,  // docking station
        ["MON-270"] = 219.99m,  // 27" monitor
        ["KEY-010"] = 49.50m,   // keyboard
    };

    [GeneratedRegex("^[A-Z]{3}-[0-9]{3}$")]
    private static partial Regex SkuPattern();

    /// <summary>Shape errors (400). An empty list means the request is well formed.</summary>
    public static List<string> Validate(CreateOrderRequest? r)
    {
        var errors = new List<string>();
        if (r is null) return ["body is required"];
        if (string.IsNullOrWhiteSpace(r.CustomerId) || r.CustomerId.Length > 64) errors.Add("customerId: 1-64 characters");
        if (r.Lines is null || r.Lines.Count is < 1 or > 20) { errors.Add("lines: 1-20 lines"); return errors; }
        foreach (var l in r.Lines)
        {
            if (l.Sku is null || !SkuPattern().IsMatch(l.Sku)) errors.Add($"sku '{l.Sku}': expected ABC-123");
            if (l.Quantity is < 1 or > 100) errors.Add($"quantity for '{l.Sku}': 1-100");
        }
        if (r.Lines.GroupBy(l => l.Sku).Any(g => g.Count() > 1)) errors.Add("lines: duplicate SKU");
        return errors;
    }

    /// <summary>Hash of the normalised request (customer + lines sorted by SKU).</summary>
    public static string RequestHash(CreateOrderRequest r)
    {
        var canonical = r.CustomerId + "|" + string.Join(";",
            r.Lines!.OrderBy(l => l.Sku, StringComparer.Ordinal).Select(l => $"{l.Sku}x{l.Quantity}"));
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(canonical)));
    }

    public static decimal Round(decimal v) => Math.Round(v, 2, MidpointRounding.AwayFromZero);
}
