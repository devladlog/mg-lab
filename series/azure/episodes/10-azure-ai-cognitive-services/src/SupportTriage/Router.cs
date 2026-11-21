namespace Contoso.SupportTriage;

/// <summary>Pure routing rules: no service call, fully unit-tested.</summary>
public static class Router
{
    /// <summary>PII categories that must never sit in a ticket: card and bank numbers.</summary>
    private static readonly HashSet<string> Sensitive = new(StringComparer.OrdinalIgnoreCase)
    {
        "CreditCardNumber", "InternationalBankingAccountNumber", "ABARoutingNumber", "USBankAccountNumber",
    };

    public const double EscalateWhenNegativeAtLeast = 0.8;

    public static string Route(string? sentiment, double negativeScore, IEnumerable<string> piiCategories, string? languageIso)
    {
        if (piiCategories.Any(Sensitive.Contains))
            return "security-review";
        if (string.Equals(sentiment, "negative", StringComparison.OrdinalIgnoreCase) && negativeScore >= EscalateWhenNegativeAtLeast)
            return "escalate";
        return languageIso is null or "en" ? "standard" : $"standard-{languageIso}";
    }
}
