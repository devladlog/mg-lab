using System.Text.RegularExpressions;

namespace Contoso.Orders.Api;

public sealed record QuoteLine(string? Sku, int Quantity);
public sealed record QuoteRequest(List<QuoteLine>? Lines);
public sealed record PricedLine(string Sku, int Quantity, decimal UnitPrice, decimal LineTotal);
public sealed record Quote(IReadOnlyList<PricedLine> Lines, decimal Subtotal, decimal Discount, decimal Total);

/// <summary>Episode 1's fictional catalogue and rules (5 % off from 500 EUR).</summary>
public static partial class Pricing
{
    private static readonly Dictionary<string, decimal> Catalogue = new()
    {
        ["CBL-001"] = 4.90m, ["DOC-100"] = 129.00m, ["MON-270"] = 219.99m, ["KEY-010"] = 49.50m,
    };

    [GeneratedRegex("^[A-Z]{3}-[0-9]{3}$")]
    private static partial Regex Sku();

    public static List<string> Validate(QuoteRequest? r)
    {
        if (r?.Lines is null || r.Lines.Count is < 1 or > 20) return ["lines: 1-20 lines"];
        var errors = new List<string>();
        foreach (var l in r.Lines)
        {
            if (l.Sku is null || !Sku().IsMatch(l.Sku)) errors.Add($"sku '{l.Sku}': expected ABC-123");
            if (l.Quantity is < 1 or > 100) errors.Add($"quantity for '{l.Sku}': 1-100");
        }
        if (r.Lines.GroupBy(l => l.Sku).Any(g => g.Count() > 1)) errors.Add("lines: duplicate SKU");
        return errors;
    }

    /// <summary>Null when a SKU isn't in the catalogue.</summary>
    public static Quote? Price(QuoteRequest r)
    {
        if (r.Lines!.Any(l => !Catalogue.ContainsKey(l.Sku!))) return null;
        var lines = r.Lines!.Select(l => new PricedLine(l.Sku!, l.Quantity, Catalogue[l.Sku!], Round(Catalogue[l.Sku!] * l.Quantity))).ToList();
        var subtotal = lines.Sum(l => l.LineTotal);
        var discount = subtotal >= 500m ? Round(subtotal * 0.05m) : 0m;
        return new Quote(lines, subtotal, discount, subtotal - discount);
    }

    private static decimal Round(decimal v) => Math.Round(v, 2, MidpointRounding.AwayFromZero);
}
