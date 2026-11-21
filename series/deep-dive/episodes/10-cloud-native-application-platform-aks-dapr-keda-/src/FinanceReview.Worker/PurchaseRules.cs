using System.Text.RegularExpressions;

namespace Contoso.FinanceReview;

/// <summary>The rules from episode 7: same threshold, same field limits.</summary>
public static partial class PurchaseRules
{
    public const decimal HighValueThreshold = 5000m;

    private static readonly string[] EventTypes = ["submitted", "approved", "rejected"];
    private static readonly string[] Currencies = ["EUR", "USD", "GBP"];

    [GeneratedRegex("^PR-[0-9]{4,8}$")]
    private static partial Regex RequestIdPattern();

    public static string? Validate(PurchaseEvent? e)
    {
        if (e is null) return "Body is empty.";
        if (!EventTypes.Contains(e.EventType)) return $"eventType '{e.EventType}' is not one of {string.Join('/', EventTypes)}.";
        if (e.PurchaseRequestId is null || !RequestIdPattern().IsMatch(e.PurchaseRequestId)) return "purchaseRequestId must look like PR-1001.";
        if (string.IsNullOrWhiteSpace(e.RequestedBy) || e.RequestedBy.Length > 254) return "requestedBy is missing or too long.";
        if (e.Total < 0.01m || e.Total > 10_000_000m) return "total is out of range.";
        if (!Currencies.Contains(e.Currency)) return $"currency '{e.Currency}' is not one of {string.Join('/', Currencies)}.";
        if (e.Note is { Length: > 500 }) return "note is longer than 500 characters.";
        // The finance-review subscription only receives purchase.high. A smaller total here means a routing mistake.
        if (e.Total < HighValueThreshold) return $"total {e.Total} is below the finance-review threshold {HighValueThreshold}.";
        return null;
    }
}
