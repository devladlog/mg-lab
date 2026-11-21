namespace Contoso.Orders.Api;

public static class Discounts
{
    public static decimal Apply(decimal total, string? code)
    {
        if (string.IsNullOrWhiteSpace(code))
        {
            return total;
        }

        return code.ToUpperInvariant() switch
        {
            "WELCOME10" => Math.Round(total * 0.90m, 2),
            "FREESHIP" => Math.Max(total - 5m, 0m),
            _ => throw new ArgumentException($"Unknown discount code '{code}'", nameof(code)),
        };
    }
}
