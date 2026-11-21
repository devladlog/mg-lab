using System.Text.RegularExpressions;

namespace Contoso.PurchaseStatus;

public sealed record PurchaseStatus(string Id, string State, decimal Total, string Currency);

/// <summary>Read model for the status page of the purchase requests from episodes 3, 4 and 7 (fictional data).</summary>
public static partial class StatusStore
{
    [GeneratedRegex("^PR-[0-9]{4,8}$")]
    private static partial Regex IdPattern();

    private static readonly Dictionary<string, PurchaseStatus> Data = new(StringComparer.Ordinal)
    {
        ["PR-1001"] = new("PR-1001", "Approved", 1476m, "EUR"),
        ["PR-1002"] = new("PR-1002", "WaitingForFinance", 7380m, "EUR"),
    };

    public static bool IsValidId(string id) => IdPattern().IsMatch(id);

    public static PurchaseStatus? Find(string id) => Data.GetValueOrDefault(id);
}
