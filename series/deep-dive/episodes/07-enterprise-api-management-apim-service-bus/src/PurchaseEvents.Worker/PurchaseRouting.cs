namespace Contoso.PurchaseEvents;

/// <summary>
/// The routing rule the gateway policy applies (apim/policies/purchase-events.policy.xml). A contract test keeps the
/// two in step, so a change in one place without the other fails the build.
/// </summary>
public static class PurchaseRouting
{
    public const decimal HighValueThreshold = 5000m;
    public const string HighLabel = "purchase.high";
    public const string StandardLabel = "purchase.standard";

    public static string LabelFor(decimal total) => total >= HighValueThreshold ? HighLabel : StandardLabel;
}
